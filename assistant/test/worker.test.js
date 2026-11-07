// Checks for src/worker.js request handling with fakes for Turnstile, the limiter and Claude: npm test.
import { test, mock } from "node:test";
import assert from "node:assert/strict";
import { handle, Limiter } from "../src/worker.js";
import { signSession, costUsd } from "../src/core.js";

const ORIGIN = "https://xmum-sair.github.io";

class MemoryStorage {   // the slice of the Durable Object storage API the limiter uses
  constructor() { this.m = new Map(); }
  async get(k) { return this.m.get(k); }
  async put(k, v) { if (typeof k === "object") for (const [a, b] of Object.entries(k)) this.m.set(a, b); else this.m.set(k, v); }
  async list() { return new Map(this.m); }
  async delete(keys) { for (const k of keys) this.m.delete(k); }
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
  assert.equal(await status(), 200);          // month so far 2.4 < 3
  assert.equal(await status(), 429);          // 3.6 >= 3
});

test("costUsd matches the shared price table", () => {
  assert.equal(costUsd("claude-opus-5-5", { input_tokens: 1_000_000, output_tokens: 100_000 }), 6);
  assert.equal(costUsd("claude-mystery", { input_tokens: 1_000_000 }), costUsd("claude-fable-5-1", { input_tokens: 1_000_000 }));
  assert.equal(costUsd("claude-opus-5-5", { input_tokens: null, cache_read_input_tokens: 1_000_000 }), 0.2);
  assert.equal(costUsd("claude-opus-5-5", undefined), 0);
  assert.equal(costUsd("claude-haiku-5-5", { input_tokens: 200_000, output_tokens: 1000 }), 0.1025);
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
