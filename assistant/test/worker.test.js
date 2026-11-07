// Checks for src/worker.js request handling with fakes for Turnstile, the limiter and Claude: npm test.
import { test, mock } from "node:test";
import assert from "node:assert/strict";
import { handle, Limiter, RESERVE_USD } from "../src/worker.js";
import { signSession, costUsd, answer } from "../src/core.js";

const ORIGIN = "https://xmum-sair.github.io";

class MemoryStorage {   // the slice of the Durable Object storage API the limiter uses
  constructor() { this.m = new Map(); }
  async get(k) { return this.m.get(k); }
  async put(k, v) { if (typeof k === "object") for (const [a, b] of Object.entries(k)) this.m.set(a, b); else this.m.set(k, v); }
  async list() { return new Map(this.m); }
  async delete(keys) { if (keys.length > 128) throw new Error("delete takes at most 128 keys"); for (const k of keys) this.m.delete(k); }
}

function env(overrides = {}) {
  const limiter = new Limiter({ storage: new MemoryStorage() });
  return { TURNSTILE_SECRET: "ts", ANTHROPIC_API_KEY: "k", PER_VISITOR_DAILY: "2", GLOBAL_DAILY: "3",
           LIMITER: { idFromName: () => "id", get: () => ({ fetch: (url, init) => limiter.fetch(new Request(url, init)) }) }, ...overrides };
}

const INDEX = { courses: [], files: [], lecturers: [] };
function deps(turnstileOk = true) {
  return {
    fetch: async (url) => ({ ok: true, json: async () => (String(url).includes("turnstile") ? { success: turnstileOk } : INDEX) }),
    client: {
      messages: { create: async () => ({ stop_reason: "end_turn", content: [{ type: "text", text: '{"in_scope": true, "reply": ""}' }] }) },
      beta: { messages: { create: async () => ({ stop_reason: "end_turn", content: [{ type: "text", text: "你好" }] }) } },
    },
  };
}

const ask = (body, origin = ORIGIN) => new Request("https://helper.example/chat", {
  method: "POST", headers: { Origin: origin, "Content-Type": "application/json", "CF-Connecting-IP": "1.2.3.4" }, body: JSON.stringify(body) });
const Q = { messages: [{ role: "user", content: "COM107 有试卷吗" }] };

test("only the site may call it, and bad requests stop early", async () => {
  assert.equal((await handle(ask(Q, "https://evil.example"), env(), deps())).status, 403);
  assert.equal((await handle(ask({ messages: [] }), env(), deps())).status, 400);
  assert.equal((await handle(ask(Q), env({ PAUSED: "1" }), deps())).status, 503);
});

test("the first question needs the human check; then a session token carries on", async () => {
  const e = env();
  assert.equal((await handle(ask(Q), e, deps())).status, 401);
  assert.equal((await handle(ask({ ...Q, turnstile: "bad" }), e, deps(false))).status, 401);
  const ok = await handle(ask({ ...Q, turnstile: "good" }), e, deps());
  const data = await ok.json();
  assert.equal(ok.status, 200);
  assert.equal(data.reply, "你好");
  assert.equal(ok.headers.get("Access-Control-Allow-Origin"), ORIGIN);
  const again = await handle(ask({ ...Q, session: data.session }), e, deps());
  assert.equal(again.status, 200);
});

test("daily caps stop a visitor, then the whole site", async () => {
  const e = env();
  const session = await signSession("ts|session");
  assert.equal((await handle(ask({ ...Q, session }), e, deps())).status, 200);
  assert.equal((await handle(ask({ ...Q, session }), e, deps())).status, 200);
  const third = await handle(ask({ ...Q, session }), e, deps());
  assert.equal(third.status, 429);
  assert.equal((await third.json()).message.includes("你今天"), true);
  const other = new Request("https://helper.example/chat", { method: "POST", headers: { Origin: ORIGIN, "CF-Connecting-IP": "5.6.7.8" },
                                                              body: JSON.stringify({ ...Q, session }) });
  assert.equal((await handle(other, e, deps())).status, 200);                   // the site's third question of the day
  const fourth = new Request(other.url, { method: "POST", headers: { Origin: ORIGIN, "CF-Connecting-IP": "9.9.9.9" }, body: JSON.stringify({ ...Q, session }) });
  assert.equal((await (await handle(fourth, e, deps())).json()).message.includes("总次数"), true);
});

test("dollar caps stop the helper for the day, then the month", async (t) => {
  t.after(() => mock.timers.reset());
  mock.timers.enable({ apis: ["Date"], now: Date.parse("2026-11-06T10:00:00Z") });
  const e = env({ PER_VISITOR_DAILY: "99", GLOBAL_DAILY: "99", HELPER_USD_DAY: "2", HELPER_USD_MONTH: "3" });
  const d = deps();
  d.client.beta.messages.create = async () => ({ stop_reason: "end_turn", content: [{ type: "text", text: "你好" }],
                                                 usage: { input_tokens: 300_000, output_tokens: 0 } });   // opus: $1.20 an answer
  const status = async () => (await handle(ask({ ...Q, session: await signSession("ts|session") }), e, d)).status;
  assert.equal(await status(), 200);
  assert.equal(await status(), 200);          // 1.2 spent < 2 before the call
  const third = await handle(ask({ ...Q, session: await signSession("ts|session") }), e, d);
  assert.equal(third.status, 429);
  const data = await third.json();
  assert.equal(data.error, "limit");
  assert.ok(data.message.includes("额度"));
  mock.timers.setTime(Date.parse("2026-11-07T10:00:00Z"));
  assert.equal(await status(), 200);          // month so far 2.4, +0.25 reserve <= 3
  assert.equal(await status(), 429);          // 3.6 + 0.25 > 3
});

const queue = (l) => { if (l.queued) return l; l.queued = true; let tail = Promise.resolve();   // a Durable Object handles one request at a time
  const f = l.fetch.bind(l); l.fetch = (req) => (tail = tail.then(() => f(req))); return l; };
const take = (l, o) => queue(l).fetch(new Request("https://limiter/take", { method: "POST", body: JSON.stringify({
  op: "take", visitor: "v", day: "2026-11-06", month: "2026-11", perVisitor: 99, global: 99, usdDay: 2, usdMonth: 60, ...o }) })).then((r) => r.json());
const spend = (l, o) => queue(l).fetch(new Request("https://limiter/spend", { method: "POST", body: JSON.stringify({ op: "spend", ...o }) })).then((r) => r.json());

test("each take reserves a fixed amount, so parallel questions cannot all slip under the cap", async () => {
  const st = new MemoryStorage(), l = new Limiter({ storage: st });
  const r = await Promise.all(Array.from({ length: 9 }, () => take(l, { usdDay: 2 })));
  assert.equal(r.filter((x) => x.ok).length, 8);                       // 8 x 0.25 = 2, a ninth would pass the cap
  assert.equal(r.find((x) => !x.ok).reason, "budget");
  assert.equal(st.m.get("s:2026-11-06"), 8 * RESERVE_USD);
  await spend(l, { day: "2026-11-06", month: "2026-11", usd: 0.05 });  // settle one: 0.05 replaces its 0.25
  assert.equal(Math.round(st.m.get("s:2026-11-06") * 100), 180);
});

test("a late spend never rolls the limiter back; it counts in the current day and month", async () => {
  const st = new MemoryStorage(), l = new Limiter({ storage: st });
  await take(l, { day: "2026-11-30", month: "2026-11" });                // A takes just before midnight
  await take(l, { day: "2026-12-01", month: "2026-12" });                // B takes after it: rolls forward
  await spend(l, { day: "2026-11-30", month: "2026-11", usd: 1.25 });    // A's late spend: +1.00 over its reservation
  assert.equal(st.m.get("day"), "2026-12-01");
  assert.equal(st.m.get("g:2026-12-01"), 1);
  assert.equal(st.m.get("s:2026-12-01"), 1.25);                          // B's reservation + A's extra 1.00
  assert.equal(st.m.get("m:2026-12"), 1.25);
  assert.equal(st.m.has("s:2026-11-30"), false);
  assert.equal(st.m.has("m:2026-11"), false);
  await take(l, { day: "2026-12-01", month: "2026-12" });                // same month, next day keeps the month key
  await take(l, { day: "2026-12-02", month: "2026-12" });
  assert.equal(st.m.get("m:2026-12"), 1.25 + 2 * RESERVE_USD);
  await take(l, { day: "2026-12-01", month: "2026-12", visitor: "late" });   // an older day lands in the current one
  assert.equal(st.m.get("g:2026-12-02"), 2);
});

test("a new day clears hundreds of old keys within the storage delete limit", async () => {
  const st = new MemoryStorage(), l = new Limiter({ storage: st });
  await st.put("day", "2026-11-05");
  for (let i = 0; i < 300; i++) await st.put(`u:2026-11-05:v${i}`, 1);
  assert.equal((await take(l, {})).ok, true);
  assert.equal([...st.m.keys()].some((k) => k.includes("2026-11-05")), false);
});

test("the cost is priced for the model that answered", async () => {
  const c = deps().client;
  c.beta.messages.create = async () => ({ stop_reason: "end_turn", content: [{ type: "text", text: "x" }],
                                          model: "claude-fable-5-1", usage: { input_tokens: 100_000 } });   // fable $1.00, opus would be $0.40
  const out = await answer({ client: c, index: INDEX, ratings: {}, messages: [{ role: "user", content: "q" }] });
  assert.equal(out.cost, costUsd("claude-fable-5-1", { input_tokens: 100_000 }));
  assert.equal(out.cost, 1);
});

// ---- course reviews on the same Worker

import { reviewsApi, MemoryStore } from "../src/reviews.js";

function reviewsEnv(overrides = {}) {
  const store = new MemoryStore();
  const reviews = { fetch: async (url, init) => {
    const r = await reviewsApi(store, JSON.parse(init.body));
    return new Response(JSON.stringify(r.data), { status: r.status });
  } };
  return { ...env(), REVIEWS_ADMIN_TOKEN: "letmein", REVIEWS: { idFromName: () => "id", get: () => reviews }, ...overrides };
}
const SEARCH = { courses: [{ code: "COM107", name: "Circuits and Devices", url: "/EEE/COM107/" }], files: [],
                 lecturers: [{ name: "Chua Ming Yam", slug: "chua-ming-yam", codes: ["COM107"] }] };
function reviewDeps(turnstileOk = true) {
  return { ...deps(turnstileOk), fetch: async (url) => ({ ok: true, json: async () => (String(url).includes("turnstile") ? { success: turnstileOk } : SEARCH) }) };
}
const VOTE = { code: "COM107", lecturer: "Chua Ming Yam", session: "2022-04", confirm: true, device: "dev-1",
               scores: { course: 4, instructor: 5, difficulty: 3, work: 2 } };
const post = (path, body, origin = ORIGIN) => new Request(`https://helper.example${path}`, {
  method: "POST", headers: { Origin: origin, "Content-Type": "application/json", "CF-Connecting-IP": "1.2.3.4" }, body: JSON.stringify(body) });

test("every vote needs its own human check; no GitHub account involved", async () => {
  const e = reviewsEnv();
  assert.equal((await handle(post("/vote", VOTE), e, reviewDeps())).status, 401);
  assert.equal((await handle(post("/vote", { ...VOTE, turnstile: "bad" }), e, reviewDeps(false))).status, 401);
  const ok = await handle(post("/vote", { ...VOTE, turnstile: "good" }), e, reviewDeps());
  assert.equal(ok.status, 200);
  assert.equal((await ok.json()).course.all.n, 1);
  assert.equal((await handle(post("/vote", { ...VOTE, turnstile: "good" }, "https://evil.example"), e, reviewDeps())).status, 403);
});

test("ratings are public and the admin API needs the token", async () => {
  const e = reviewsEnv();
  await handle(post("/vote", { ...VOTE, turnstile: "good" }), e, reviewDeps());
  const r = await handle(new Request("https://helper.example/ratings", { headers: { Origin: "https://anywhere.example" } }), e, reviewDeps());
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("Access-Control-Allow-Origin"), "*");
  assert.equal((await r.json()).courses.COM107.all.n, 1);
  const admin = (body) => handle(new Request("https://helper.example/admin/api", { method: "POST", body: JSON.stringify(body) }), e, reviewDeps());
  assert.equal((await admin({ token: "nope", op: "summary" })).status, 401);
  const s = await admin({ token: "letmein", op: "summary" });
  assert.equal(s.status, 200);
  assert.equal((await s.json()).total, 1);
  const page = await handle(new Request("https://helper.example/admin"), e, reviewDeps());
  assert.equal(page.status, 200);
  assert.ok((await page.text()).includes("/admin/api"));
});
