// Checks for src/reviews.js (course reviews on the Worker): npm test. No network; the store is the in-memory one.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as rv from "../src/reviews.js";

const SITE = { codes: new Set(["COM107", "EEE308"]), pairs: new Set(["COM107|chua-ming-yam"]) };
const MAIN4 = { course: 4, instructor: 5, difficulty: 3, work: 2 };
const vote = (over = {}) => ({ code: "com107", lecturer: "Dr. Chua Ming Yam", session: "2022-04", scores: { ...MAIN4 }, confirm: true, ...over });

test("names and keys match the old GitHub bot, so old and new votes land together", () => {
  assert.equal(rv.lecturerKey("Dr. Chua Ming Yam"), "chua-ming-yam");
  assert.equal(rv.lecturerKey("Prof. Ng Zi Neng"), "ng-zi-neng");
  assert.equal(rv.displayName("Puan  Maryani   Ahmad"), "Maryani Ahmad");
});

test("validation needs a course, a lecturer, the four main scores and the confirmation", () => {
  assert.equal(rv.validate(vote()).ok, true);
  assert.equal(rv.validate(vote()).vote.code, "COM107");
  assert.equal(rv.validate(vote({ code: "not a code" })).ok, false);
  assert.equal(rv.validate(vote({ lecturer: "" })).ok, false);
  assert.equal(rv.validate(vote({ lecturer: "x".repeat(81) })).ok, false);
  assert.equal(rv.validate(vote({ scores: { course: 4 } })).ok, false);
  assert.equal(rv.validate(vote({ scores: { ...MAIN4, work: 6 } })).ok, false);
  assert.equal(rv.validate(vote({ confirm: false })).ok, false);
  assert.equal(rv.validate(vote({ session: "Nov 2021" })).ok, false);
  const extras = rv.validate(vote({ session: "", scores: { ...MAIN4, learned: 4, nonsense: 3 } }));
  assert.deepEqual(extras.vote.scores, { ...MAIN4, learned: 4 });            // unknown dimensions are dropped
  assert.equal(extras.vote.session, "");
});

test("one vote per browser per course and lecturer: a second one replaces the first", async () => {
  const store = new rv.MemoryStore();
  const ctx = { voter: "web:a", ip: "ip1", now: 1_000_000, site: SITE };
  const first = await rv.decide(store, rv.validate(vote()).vote, ctx);
  assert.deepEqual([first.action, first.replaced, first.flags], ["save", false, []]);
  const again = await rv.decide(store, rv.validate(vote({ scores: { ...MAIN4, course: 1 } })).vote, { ...ctx, now: 2_000_000 });
  assert.equal(again.replaced, true);
  assert.equal(store.votes.size, 1);
  assert.equal([...store.votes.values()][0].scores.course, 1);
});

test("a shared campus address is never suspicious: it only has the daily cap (maintainer, 2026-11-06)", async () => {
  const store = new rv.MemoryStore();
  const base = { ip: "campus", now: 1_000_000, site: SITE };
  for (let i = 0; i < 12; i++) {                                            // twelve classmates on the same WiFi, different scores
    const s = { course: 1 + (i % 5), instructor: 1 + ((i + 1) % 5), difficulty: 1 + ((i + 2) % 5), work: 1 + (i % 3) };
    const d = await rv.decide(store, rv.validate(vote({ scores: s })).vote, { ...base, voter: `web:s${i}`, now: base.now + i * 600_000 });
    assert.equal(d.action, "save");
    assert.deepEqual(d.flags, [], `student ${i}`);
  }
  const copy = await rv.decide(store, rv.validate(vote()).vote, { ...base, voter: "web:x1", now: 90_000_000 });
  const copy2 = await rv.decide(store, rv.validate(vote()).vote, { ...base, voter: "web:x2", now: 90_000_100 });
  assert.deepEqual([copy.flags, copy2.flags], [[], []]);                    // same address, same scores: still not flagged
  assert.equal(rv.LIMITS.perIpDaily, 100);
});

test("bursts, new lecturers and unknown courses are flagged but still counted", async () => {
  const store = new rv.MemoryStore();
  let last;
  for (let i = 0; i < 10; i++) {
    const s = { course: 1 + (i % 5), instructor: 1 + ((i + 2) % 5), difficulty: 3, work: 1 + (i % 4) };
    last = await rv.decide(store, rv.validate(vote({ scores: s })).vote, { voter: `web:b${i}`, ip: `ip${i}`, now: 1_000_000 + i * 1000, site: SITE });
  }
  assert.ok(last.flags.includes("burst") && last.action === "save");
  const newName = await rv.decide(store, rv.validate(vote({ lecturer: "Someone New" })).vote, { voter: "web:n", ip: "ipn", now: 5e9, site: SITE });
  assert.deepEqual(newName.flags, ["new_name"]);
  const unknown = await rv.decide(store, rv.validate(vote({ code: "EEE222" })).vote, { voter: "web:u", ip: "ipu", now: 5e9, site: SITE });
  assert.ok(unknown.flags.includes("new_name"));
});

test("hard daily caps: 100 per address, 20 per browser", async () => {
  const store = new rv.MemoryStore();
  const day = "2026-11-06";
  for (let i = 0; i < rv.LIMITS.perIpDaily; i++) store.bump("ip:busy", day);
  const d = await rv.decide(store, rv.validate(vote()).vote, { voter: "web:z", ip: "busy", now: Date.parse(day + "T05:00:00Z"), site: SITE });
  assert.deepEqual([d.action, d.reason], ["reject", "ip"]);
  for (let i = 0; i < rv.LIMITS.perVoterDaily; i++) store.bump("voter:web:y", day);
  const e = await rv.decide(store, rv.validate(vote()).vote, { voter: "web:y", ip: "quiet", now: Date.parse(day + "T05:00:00Z"), site: SITE });
  assert.deepEqual([e.action, e.reason], ["reject", "voter"]);
});

test("the aggregate matches the old ratings.json: averages from 3 voters, one vote per person for the course", () => {
  const votes = [
    { code: "COM107", lecturerKey: "chua-ming-yam", name: "Chua Ming Yam", voter: "a", at: 1, scores: { ...MAIN4, course: 2 }, status: "ok" },
    { code: "COM107", lecturerKey: "chua-ming-yam", name: "Chua Ming Yam", voter: "b", at: 2, scores: { ...MAIN4 }, status: "ok" },
    { code: "COM107", lecturerKey: "chua-ming-yam", name: "Chua Ming Yam", voter: "c", at: 3, scores: { ...MAIN4 }, status: "ok" },
    { code: "COM107", lecturerKey: "someone-else", name: "Someone Else", voter: "a", at: 0, scores: { ...MAIN4 }, status: "ok" },
    { code: "COM107", lecturerKey: "someone-else", name: "Someone Else", voter: "d", at: 4, scores: { ...MAIN4 }, status: "ok" },
    { code: "COM107", lecturerKey: "chua-ming-yam", name: "Chua Ming Yam", voter: "z", at: 5, scores: { ...MAIN4, course: 1 }, status: "rejected" },
  ];
  const agg = rv.aggregate(votes, "2026-11-06T00:00:00Z");
  assert.deepEqual([agg.min_n, agg.main, agg.dims.length], [3, ["course", "instructor", "difficulty", "work"], 8]);
  const chua = agg.courses.COM107.lecturers["chua-ming-yam"];
  assert.deepEqual([chua.n, chua.course, chua.instructor, chua.communication, chua.counts.course, chua.name], [3, 3.3, 5, null, 3, "Chua Ming Yam"]);
  const other = agg.courses.COM107.lecturers["someone-else"];
  assert.equal(other.n, 2);
  assert.equal("course" in other, false);                                   // below 3 voters: count only
  assert.equal(agg.courses.COM107.all.n, 4);                                // a, b, c, d: the rejected vote is out
  assert.equal(agg.courses.COM107.all.course, 3.5);                         // a's latest vote (2) counts once
});

test("imported GitHub votes keep their anonymous ids and the newer vote wins", async () => {
  const store = new rv.MemoryStore();
  const n = await rv.importVotes(store, [
    { code: "COM107", name: "Chua Ming Yam", voter: "abc", at: "2026-11-05T10:00:00Z", session: "2022-04", scores: MAIN4 },
    { code: "COM107", name: "Chua Ming Yam", voter: "abc", at: "2026-11-05T09:00:00Z", session: "2022-04", scores: { ...MAIN4, course: 1 } },
    { code: "bad code", name: "X", voter: "q", at: "2026-11-05T09:00:00Z", scores: MAIN4 },
  ]);
  assert.equal(n, 2);
  const v = [...store.votes.values()];
  assert.deepEqual([v.length, v[0].voter, v[0].scores.course, v[0].source, v[0].reviewed], [1, "gh:abc", 4, "github", true]);
});

// ---- the Durable Object's API (store-agnostic, so it runs here on the memory store)

const CATALOG = { codes: ["COM107", "EEE308"], pairs: ["COM107|chua-ming-yam"] };
const call = (store, msg, now = 1_000_000) => rv.reviewsApi(store, { site: CATALOG, ...msg }, now);

test("a vote returns the course's new numbers; public ratings hide unconfirmed names until kept", async () => {
  const store = new rv.MemoryStore();
  const ok = await call(store, { op: "vote", voter: "web:a", ip: "ip1", body: vote() });
  assert.equal(ok.status, 200);
  assert.equal(ok.data.course.all.n, 1);
  assert.equal(ok.data.flagged, undefined);                                   // the voter is not told about flags
  await call(store, { op: "vote", voter: "web:b", ip: "ip2", body: vote({ lecturer: "Rude Name" }) });
  await call(store, { op: "vote", voter: "web:c", ip: "ip3", body: vote({ code: "FAKE101" }) });
  let pub = (await call(store, { op: "ratings" })).data;
  assert.equal(pub.courses.COM107.lecturers["rude-name"].name, rv.UNCONFIRMED);
  assert.equal(pub.courses.COM107.all.n, 2);                                  // counted all the same
  assert.equal("FAKE101" in pub.courses, false);                              // an unknown course stays out of sight
  const queue = (await call(store, { op: "list" })).data.votes;
  assert.equal(queue.length, 2);
  await call(store, { op: "keep", keys: queue.filter((q) => q.code === "COM107").map((q) => q.key) });
  pub = (await call(store, { op: "ratings" })).data;
  assert.equal(pub.courses.COM107.lecturers["rude-name"].name, "Rude Name");   // kept: the real name shows
});

test("dropping takes a vote out of the numbers; summary and lecturers serve the weekly bots", async () => {
  const store = new rv.MemoryStore();
  await call(store, { op: "vote", voter: "web:a", ip: "ip1", body: vote() });
  await call(store, { op: "vote", voter: "web:b", ip: "ip2", body: vote({ lecturer: "New Person", session: "2025-09" }) });
  let s = (await call(store, { op: "summary" })).data;
  assert.deepEqual([s.total, s.unreviewed, s.by_flag.new_name], [2, 1, 1]);
  assert.deepEqual((await call(store, { op: "lecturers" })).data.lecturers, [{ code: "COM107", name: "Chua Ming Yam", session: "2022-04" }]);
  const [q] = (await call(store, { op: "list" })).data.votes;
  await call(store, { op: "keep", keys: [q.key] });
  assert.equal((await call(store, { op: "lecturers" })).data.lecturers.length, 2);  // kept names go to the lecturer PR
  await call(store, { op: "drop", keys: [q.key] });
  const pub = (await call(store, { op: "ratings" })).data;
  assert.equal(pub.courses.COM107.all.n, 1);
  s = (await call(store, { op: "summary" })).data;
  assert.deepEqual([s.total, s.unreviewed, s.dropped], [2, 0, 1]);
  const bad = await call(store, { op: "vote", voter: "web:c", ip: "ip3", body: vote({ confirm: false }) });
  assert.equal(bad.status, 400);
  assert.ok(bad.data.problems.length > 0);
});
