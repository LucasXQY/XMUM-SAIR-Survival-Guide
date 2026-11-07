// Checks for src/forum.js (the discussion area) and its routes in src/worker.js: npm test. No network; the model is a stub.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as fm from "../src/forum.js";
import { handle } from "../src/worker.js";

const NOW = Date.UTC(2026, 10, 7, 8);
const thread = (over = {}) => ({ kind: "thread", board: "study", course: "", title: "EEE308 和 EEE322 哪个先修",
  body: "两门都想选，但时间冲突，学长学姐有建议吗？", confirm: true, ...over });
const reply = (parent, over = {}) => ({ kind: "reply", thread: parent, body: "先修 EEE308，作业少一点。", confirm: true, ...over });

const stub = (decision, extra = {}, calls = []) => ({
  messages: { create: async (req) => { calls.push(req); return { stop_reason: "end_turn",
    content: [{ type: "text", text: JSON.stringify({ decision, board: "study", course: "", reason_zh: "理由", reason_en: "reason", ...extra }) }] }; } },
});
const WORDS = { allow: ["cheat sheet"], zh_profanity: ["傻逼"], en_profanity: ["fuck"], slurs: [], attacks: ["不配当老师"],
                sensitive: [], review: ["骚扰"], suspect: [] };

test("validation: threads and replies, lengths, boards, course codes, confirmation", () => {
  assert.equal(fm.validate(thread()).ok, true);
  assert.equal(fm.validate(thread({ kind: "x" })).ok, false);
  assert.equal(fm.validate(thread({ board: "nope" })).ok, false);
  assert.equal(fm.validate(thread({ board: "" })).ok, true);                         // the model picks the board
  assert.equal(fm.validate(thread({ title: "abc" })).ok, false);
  assert.equal(fm.validate(thread({ body: "太短" })).ok, false);
  assert.equal(fm.validate(thread({ confirm: false })).ok, false);
  assert.equal(fm.validate(thread({ course: "eee 308" }), ["EEE308"]).item.course, "EEE308");
  assert.equal(fm.validate(thread({ course: "MPU1.1" }), ["MPU1.1"]).item.course, "MPU1.1");
  assert.equal(fm.validate(thread({ course: "XYZ999" }), ["EEE308"]).item.course, "");   // unknown codes are dropped, not errors
  assert.equal(fm.validate(reply("abc")).ok, true);
  assert.equal(fm.validate(reply("")).ok, false);
  assert.equal(fm.validate(reply("abc", { body: "x".repeat(2001) })).ok, false);
  assert.equal(fm.validate(thread({ author: "a".repeat(50) })).item.author.length, 30);
  assert.deepEqual(fm.BOARDS, ["freshers", "study", "career", "life", "requests", "other"]);
});

test("keyword lists: the same rules as moderation.py (loose CJK, whole English words, allow list)", () => {
  assert.deepEqual(fm.parseWords("# comment\nFuck  # trailing\n\n傻 逼\n"), ["fuck", "傻 逼"]);
  assert.deepEqual(fm.scanWords("这老师真是不配 当老师！", WORDS).map((h) => h.cat), ["attacks"]);   // spaces and punctuation ignored
  assert.deepEqual(fm.scanWords("FUCK this exam", WORDS).map((h) => h.word), ["fuck"]);
  assert.deepEqual(fm.scanWords("fuckton is not a word here? no: fucktons", WORDS), []);               // whole words only
  assert.deepEqual(fm.scanWords("ＦＵＣＫ", WORDS).map((h) => h.word), ["fuck"]);                      // full-width letters fold
  assert.deepEqual(fm.scanWords("bring a cheat sheet", { ...WORDS, en_profanity: ["cheat"] }), []);   // the allow list wins
  assert.deepEqual(fm.scanWords("anything", null), []);
});

test("moderation: the model decides, a fold-list hit is never published at once, failures hold", async () => {
  const calls = [];
  const v = await fm.moderate(stub("publish", { board: "career", course: "EEE308" }, calls), fm.validate(thread({ board: "" })).item, { codes: ["EEE308"] });
  assert.equal(v.decision, "publish");
  assert.equal(v.board, "career");                                                    // filled in where the poster left it blank
  assert.equal(v.course, "EEE308");
  assert.ok(calls[0].messages[0].content.includes("<post>") && calls[0].model === fm.FORUM_MODEL);
  const own = await fm.moderate(stub("publish", { board: "career" }), fm.validate(thread()).item);
  assert.equal(own.board, "study");                                                   // the poster's own board wins
  const hit = await fm.moderate(stub("publish"), fm.validate(thread()).item, { hits: [{ cat: "zh_profanity", word: "傻逼" }] });
  assert.equal(hit.decision, "hold");
  const soft = await fm.moderate(stub("publish"), fm.validate(thread()).item, { hits: [{ cat: "review", word: "骚扰" }] });
  assert.equal(soft.decision, "publish");                                             // review words are hints only
  assert.equal((await fm.moderate(null, fm.validate(thread()).item)).decision, "hold");
  const boom = { messages: { create: async () => { throw new Error("overloaded"); } } };
  assert.equal((await fm.moderate(boom, fm.validate(thread()).item)).decision, "hold");
  const cut = { messages: { create: async () => ({ stop_reason: "max_tokens", content: [] }) } };
  assert.equal((await fm.moderate(cut, fm.validate(thread()).item)).decision, "hold");
  const odd = await fm.moderate(stub("maybe"), fm.validate(thread()).item);
  assert.equal(odd.decision, "hold");
  const r = await fm.moderate(stub("publish", { board: "life", course: "COM107" }), fm.validate(reply("t1")).item,
                              { thread: { title: "t", board: "study", course: "EEE308" } });
  assert.deepEqual([r.board, r.course], ["study", "EEE308"]);                         // a reply stays on its thread's board
});

async function put(store, item, verdict = "publish", who = {}) {
  const it = fm.validate(item).item;
  const res = await fm.forumApi(store, { op: "reserve", ip: who.ip || "i1", device: who.device || "d1", parent: it.parent }, NOW);
  if (res.status !== 200) return res;
  const m = { decision: verdict, board: it.board || "study", course: it.course, reason_zh: "z", reason_en: "e" };
  return fm.forumApi(store, { op: "post", item: it, verdict: m, ip: who.ip || "i1", device: who.device || "d1" }, NOW);
}

test("store: threads, replies, counts, the original poster's mark, reports, withdrawing, admin", async () => {
  const s = new fm.MemoryForum();
  const t = (await put(s, thread())).data;
  assert.equal(t.status, "live");
  await put(s, reply(t.id), "publish", { device: "d2" });
  await put(s, reply(t.id, { body: "谢谢，那我先修 EEE308。" }));                       // the original poster answers
  await put(s, reply(t.id, { body: "held one" }), "hold", { device: "d3" });
  assert.equal((await put(s, reply("missing"))).status, 404);
  const held = (await put(s, thread({ title: "一个待审的帖子" }), "hold")).data;
  assert.equal(held.status, "pending");
  const list = (await fm.forumApi(s, { op: "list" }, NOW)).data.threads;
  assert.equal(list.length, 1);
  assert.equal(list[0].replies, 2);
  assert.ok(!("device" in list[0]) && !("ip" in list[0]) && !("body" in list[0]));      // nothing that identifies a browser
  const one = (await fm.forumApi(s, { op: "thread", id: t.id }, NOW)).data;
  assert.deepEqual(one.replies.map((r) => r.op), [false, true]);
  assert.ok(!/"(device|ip)"/.test(JSON.stringify(one)));                             // nor in a thread's replies
  assert.equal((await fm.forumApi(s, { op: "thread", id: held.id }, NOW)).status, 404);
  assert.equal((await put(s, reply(held.id))).status, 404);                           // no replies to a thread nobody can see
  // three different browsers report the thread: it goes back to the maintainer
  for (const d of ["r1", "r1", "r2", "r3"]) await fm.forumApi(s, { op: "report", id: t.id, device: d }, NOW);
  assert.equal((await fm.forumApi(s, { op: "list" }, NOW)).data.threads.length, 0);
  const q = (await fm.forumApi(s, { op: "admin_list" }, NOW)).data;
  assert.equal(q.pending.length, 3);
  assert.ok(q.pending.some((p) => p.kind === "reply" && p.thread === "EEE308 和 EEE322 哪个先修"));
  await fm.forumApi(s, { op: "approve", ids: [t.id] }, NOW);
  assert.equal((await fm.forumApi(s, { op: "list" }, NOW)).data.threads.length, 1);
  // only the browser that wrote a post may withdraw it
  assert.equal((await fm.forumApi(s, { op: "withdraw", id: t.id, device: "d2" }, NOW)).status, 404);
  assert.equal((await fm.forumApi(s, { op: "withdraw", id: t.id, device: "d1" }, NOW)).data.withdrawn, true);
  assert.equal((await fm.forumApi(s, { op: "list" }, NOW)).data.threads.length, 0);
});

test("caps: per browser, per network, and the model allowance", async () => {
  const s = new fm.MemoryForum();
  for (let i = 0; i < fm.LIMITS.perDeviceDaily; i++) assert.equal((await put(s, thread())).status, 200);
  assert.deepEqual((await put(s, thread())).data, { reason: "device" });
  const s2 = new fm.MemoryForum();
  const r1 = await fm.forumApi(s2, { op: "reserve", ip: "i", device: "a", modelDaily: 1 }, NOW);
  const r2 = await fm.forumApi(s2, { op: "reserve", ip: "i", device: "b", modelDaily: 1 }, NOW);
  assert.deepEqual([r1.data.model, r2.data.model], [true, false]);                    // past the allowance: no model, so "hold"
});

test("dollar caps: each look reserves first, the real cost settles it, a failed call keeps the reservation", async () => {
  const s = new fm.MemoryForum();
  const day = new Date(NOW).toISOString().slice(0, 10), month = day.slice(0, 7);
  const reserve = (over = {}) => fm.forumApi(s, { op: "reserve", ip: "i", device: crypto.randomUUID(), usdDay: 0.005, usdMonth: 1, ...over }, NOW);
  assert.equal((await reserve()).data.model, true);
  assert.equal((await reserve()).data.model, true);
  assert.equal((await reserve()).data.model, false);                                  // 2 × 0.002 held; a third would pass 0.005
  assert.ok(Math.abs((await s.spent(`d:${day}`)) - 0.004) < 1e-9);
  const it = fm.validate(thread()).item;
  const post = (cost) => fm.forumApi(s, { op: "post", item: it, ip: "i", device: "d", reserved: fm.RESERVE_USD,
    verdict: { decision: "hold", board: "study", course: "", reason_zh: "z", reason_en: "e", cost } }, NOW);
  await post(0.0003);                                                                 // settled: 0.004 - 0.002 + 0.0003
  assert.ok(Math.abs((await s.spent(`d:${day}`)) - 0.0023) < 1e-9);
  assert.ok(Math.abs((await s.spent(`m:${month}`)) - 0.0023) < 1e-9);
  await post(null);                                                                   // cost unknown: the reservation stays
  assert.ok(Math.abs((await s.spent(`d:${day}`)) - 0.0023) < 1e-9);
  assert.equal((await reserve({ usdDay: 1, usdMonth: 0.003 })).data.model, false);    // the month's cap counts too
  // the model's real usage is priced by core.js
  const priced = { messages: { create: async () => ({ stop_reason: "end_turn", model: "claude-haiku-5-5", usage: { input_tokens: 2000, output_tokens: 200 },
    content: [{ type: "text", text: JSON.stringify({ decision: "publish", board: "study", course: "", reason_zh: "z", reason_en: "e" }) }] }) } };
  assert.ok(Math.abs((await fm.moderate(priced, it)).cost - (2000 * 0.1 + 200 * 0.5) / 1e6) < 1e-12);
  assert.equal((await fm.moderate(null, it)).cost, 0);
  assert.equal((await fm.moderate({ messages: { create: async () => { throw new Error("x"); } } }, it)).cost, null);
});

// ---------------------------------------------------------------- the Worker's routes

const ORIGIN = "https://xmum-sair.github.io";
function forumEnv() {
  const store = new fm.MemoryForum();
  return { TURNSTILE_SECRET: "ts", ANTHROPIC_API_KEY: "k", REVIEWS_ADMIN_TOKEN: "admin",
           FORUM: { idFromName: () => "f", get: () => ({ fetch: async (url, init) => {
             const r = await fm.forumApi(store, JSON.parse(init.body));
             return new Response(JSON.stringify(r.data), { status: r.status }); } }) } };
}
function forumDeps(decision = "publish", turnstile = true) {
  return {
    fetch: async (url) => {
      const u = String(url);
      if (u.includes("turnstile")) return { ok: true, json: async () => ({ success: turnstile }) };
      if (u.includes("/moderation/words/")) return { ok: true, text: async () => (u.endsWith("zh_profanity.txt") ? "傻逼\n" : "") };
      return { ok: true, json: async () => ({ courses: [{ code: "EEE308" }], files: [], lecturers: [] }) };
    },
    client: stub(decision),
  };
}
const req = (path, body, origin = ORIGIN) => new Request(`https://helper.example${path}`, {
  method: "POST", headers: { Origin: origin, "Content-Type": "application/json", "CF-Connecting-IP": "1.2.3.4" }, body: JSON.stringify(body) });

test("routes: one human check per hour, then a session; the model decides; lists are public", async () => {
  const e = forumEnv();
  const body = { ...thread(), device: "x" };
  assert.equal((await handle(req("/forum/post", body, "https://evil.example"), e, forumDeps())).status, 403);
  assert.equal((await handle(req("/forum/post", body), e, forumDeps())).status, 401);            // no Turnstile token
  assert.equal((await handle(req("/forum/post", { ...body, turnstile: "t" }), e, forumDeps("publish", false))).status, 401);
  const first = await (await handle(req("/forum/post", { ...body, turnstile: "t" }), e, forumDeps())).json();
  assert.equal(first.status, "live");
  assert.ok(first.session);
  // the next post sends the session instead of a new check
  const second = await (await handle(req("/forum/post", { ...reply(first.id), device: "x", session: first.session }), e, forumDeps())).json();
  assert.equal(second.status, "live");
  const rude = await (await handle(req("/forum/post", { ...reply(first.id, { body: "你个傻 逼" }), device: "x", session: first.session }), e, forumDeps())).json();
  assert.equal(rude.status, "pending");                                                   // the keyword list overrides "publish"
  const bad = await handle(req("/forum/post", { ...body, title: "", session: first.session }), e, forumDeps());
  assert.equal(bad.status, 400);
  const list = await handle(new Request("https://helper.example/forum"), e, forumDeps());
  assert.equal(list.headers.get("Access-Control-Allow-Origin"), "*");
  assert.equal((await list.json()).threads[0].replies, 1);
  const one = await (await handle(new Request(`https://helper.example/forum/thread?id=${first.id}`), e, forumDeps())).json();
  assert.equal(one.replies.length, 1);
  assert.equal((await handle(new Request("https://helper.example/forum/thread"), e, forumDeps())).status, 400);
  // the maintainer's queue
  const admin = (b) => handle(new Request("https://helper.example/admin/api", { method: "POST", body: JSON.stringify(b) }), e, forumDeps());
  assert.equal((await admin({ token: "nope", op: "forum_list" })).status, 401);
  const q = await (await admin({ token: "admin", op: "forum_list" })).json();
  assert.equal(q.pending.length, 1);
  const approved = await (await admin({ token: "admin", op: "forum_approve", ids: [q.pending[0].id] })).json();
  assert.deepEqual(approved.threads, [first.id]);                                         // its thread page is dropped from the cache
  const again = await (await handle(new Request(`https://helper.example/forum/thread?id=${first.id}`), e, forumDeps())).json();
  assert.equal(again.replies.length, 2);
  // withdrawing needs the same browser
  assert.equal((await handle(req("/forum/withdraw", { id: first.id, device: "y" }), e, forumDeps())).status, 404);
  assert.equal((await handle(req("/forum/withdraw", { id: first.id, device: "x" }), e, forumDeps())).status, 200);
});

test("routes: paused or out of allowance, posts wait for the maintainer and the model is not called", async () => {
  const calls = [];
  const deps = { ...forumDeps(), client: stub("publish", {}, calls) };
  const e = { ...forumEnv(), PAUSED: "1" };
  const r = await (await handle(req("/forum/post", { ...thread(), device: "x", turnstile: "t" }), e, deps)).json();
  assert.equal(r.status, "pending");
  const e2 = { ...forumEnv(), FORUM_MODEL_DAILY: "0" };
  const r2 = await (await handle(req("/forum/post", { ...thread(), device: "x", turnstile: "t" }), e2, deps)).json();
  assert.equal(r2.status, "pending");
  const e3 = { ...forumEnv(), FORUM_USD_DAY: "0.001" };                                    // less than one reservation
  const r3 = await (await handle(req("/forum/post", { ...thread(), device: "x", turnstile: "t" }), e3, deps)).json();
  assert.equal(r3.status, "pending");
  assert.equal(calls.length, 0);
});
