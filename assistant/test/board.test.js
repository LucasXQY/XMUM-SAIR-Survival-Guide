// Checks for src/board.js (opportunity wall and experience posts): npm test. No network; the model is a stub.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as bd from "../src/board.js";

const opp = (over = {}) => ({ kind: "opp", cat: "intern", title: "Summer intern at ACME Robotics",
  body: "Three-month paid internship in Kuala Lumpur, ROS and Python. Apply with a CV through the link.",
  fields: { org: "ACME", deadline: "2026-12-01", link: "https://acme.example/jobs/1" }, confirm: true, ...over });

const stub = (decision, category = "intern", calls = []) => ({
  messages: { create: async (req) => { calls.push(req); return { stop_reason: "end_turn",
    content: [{ type: "text", text: JSON.stringify({ decision, category, reason_zh: "理由", reason_en: "reason" }) }] }; } },
});
const post = (store, body, client, over = {}) => bd.boardApi(store, { op: "post", body, device: "d1", ip: "i1", ...over }, Date.UTC(2026, 10, 7), client);

test("validation: kind, category, lengths, dates, links, referral needs a code or link, confirmation", () => {
  assert.equal(bd.validate(opp()).ok, true);
  assert.equal(bd.validate(opp({ kind: "x" })).ok, false);
  assert.equal(bd.validate(opp({ cat: "life" })).ok, false);                 // a story category on an opportunity
  assert.equal(bd.validate(opp({ kind: "story", cat: "life" })).ok, true);
  assert.equal(bd.validate(opp({ title: "abc" })).ok, false);
  assert.equal(bd.validate(opp({ body: "too short" })).ok, false);
  assert.equal(bd.validate(opp({ fields: { deadline: "next week" } })).ok, false);
  assert.equal(bd.validate(opp({ fields: { link: "javascript:alert(1)" } })).ok, false);
  assert.equal(bd.validate(opp({ cat: "referral", fields: {} })).ok, false);
  assert.equal(bd.validate(opp({ cat: "referral", fields: { code: "NTA1b2" } })).ok, true);
  assert.equal(bd.validate(opp({ confirm: false })).ok, false);
  assert.deepEqual(Object.keys(bd.validate(opp({ fields: { org: "A", junk: "x" } })).post.fields), ["org"]);
  const zh = bd.validate(opp({ body: "怎么找到的：学院群里看到的招聘，投了简历。面试两轮。" })).post.body;
  assert.equal(zh, "怎么找到的：学院群里看到的招聘，投了简历。面试两轮。");   // Chinese full-width punctuation is kept
});

test("publish goes live and shows in the list; hold and reject do not", async () => {
  const store = new bd.MemoryBoard();
  const a = await post(store, opp(), stub("publish"));
  assert.equal(a.status, 200);
  assert.equal(a.data.status, "live");
  assert.equal(a.data.post.title, "Summer intern at ACME Robotics");
  assert.equal((await post(store, opp(), stub("hold"))).data.status, "pending");
  const r = await post(store, opp(), stub("reject"));
  assert.equal(r.data.status, "rejected");
  assert.equal(r.data.reason_zh, "理由");
  const list = await bd.boardApi(store, { op: "list" });
  assert.equal(list.data.posts.length, 1);
  assert.equal("ip" in list.data.posts[0], false);                          // hashes never leave through the public list
  assert.equal("device" in list.data.posts[0], false);
});

test("a model failure or no model holds the post, never publishes it", async () => {
  const store = new bd.MemoryBoard();
  const broken = { messages: { create: async () => { throw new Error("down"); } } };
  assert.equal((await post(store, opp(), broken)).data.status, "pending");
  assert.equal((await post(store, opp(), null)).data.status, "pending");
  const cut = { messages: { create: async () => ({ stop_reason: "max_tokens", content: [] }) } };
  assert.equal((await post(store, opp(), cut)).data.status, "pending");
});

test("the model may fix the category, only to an allowed one; the post text goes in as data", async () => {
  const store = new bd.MemoryBoard();
  const calls = [];
  const a = await post(store, opp(), stub("publish", "job", calls));
  assert.equal(a.data.post.cat, "job");
  const b = await post(store, opp(), stub("publish", "life"));               // not an opportunity category: keep the poster's
  assert.equal(b.data.post.cat, "intern");
  assert.match(calls[0].messages[0].content, /<post>[\s\S]*ACME[\s\S]*<\/post>/);
  assert.equal(calls[0].model, bd.MOD_MODEL);
});

test("a verdict passed in by the Worker is used without calling a model", async () => {
  const store = new bd.MemoryBoard();
  const verdict = { decision: "publish", category: "intern", reason_zh: "好", reason_en: "ok" };
  const r = await post(store, opp(), { messages: { create: async () => { throw new Error("must not be called"); } } }, { verdict });
  assert.equal(r.data.status, "live");
});

test("daily caps per browser and per network", async () => {
  const store = new bd.MemoryBoard();
  for (let i = 0; i < bd.LIMITS.perDeviceDaily; i++) assert.equal((await post(store, opp(), stub("publish"))).status, 200);
  const r = await post(store, opp(), stub("publish"));
  assert.equal(r.status, 429);
  assert.equal(r.data.reason, "device");
  const other = await post(store, opp(), stub("publish"), { device: "d2" });  // another browser on the same network still posts
  assert.equal(other.status, 200);
});

test("three reports from different browsers hide a post; one browser counts once; approve brings it back", async () => {
  const store = new bd.MemoryBoard();
  const { data } = await post(store, opp(), stub("publish"));
  const rep = (device) => bd.boardApi(store, { op: "report", id: data.id, device });
  assert.equal((await rep("a")).data.counted, true);
  assert.equal((await rep("a")).data.counted, false);
  await rep("b");
  assert.equal((await rep("c")).data.hidden, true);
  assert.equal((await bd.boardApi(store, { op: "list" })).data.posts.length, 0);
  const q = await bd.boardApi(store, { op: "admin_list" });
  assert.equal(q.data.pending.length, 1);
  await bd.boardApi(store, { op: "approve", ids: [data.id] });
  assert.equal((await bd.boardApi(store, { op: "list" })).data.posts.length, 1);
  await bd.boardApi(store, { op: "remove", ids: [data.id] });
  assert.equal((await bd.boardApi(store, { op: "list" })).data.posts.length, 0);
});
