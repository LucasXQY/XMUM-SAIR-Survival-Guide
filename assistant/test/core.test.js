// Checks for src/core.js: npm test (node --test). No network, no API key; Claude is a fake that records each request.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as core from "../src/core.js";

const INDEX = {
  courses: [
    { prog: "EEE", code: "COM107", name: "Circuits and Devices", url: "/EEE/COM107_Circuits_and_Devices/", lecturers: ["Chua Ming Yam"], sessions: ["2022-04"], files: 2 },
    { prog: "EEE", code: "EEE301", name: "Signals and Systems", url: "/EEE/EEE301_Signals_and_Systems/", lecturers: [], sessions: ["2023-04"], files: 1 },
  ],
  files: [
    { code: "COM107", course: "Circuits and Devices", session: "2022-04", type: "Past-Papers", name: "COM107_202204_Final_Question.pdf",
      path: "EEE/COM107_Circuits_and_Devices/2022-04/Past-Papers/COM107_202204_Final_Question.pdf", preview: "p", download: "d",
      topics: ["基尔霍夫定律 Kirchhoff's laws"] },
    { code: "EEE301", course: "Signals and Systems", session: "2023-04", type: "Notes", name: "EEE301_202304_Notes.pdf",
      path: "EEE/EEE301_Signals_and_Systems/2023-04/Notes/EEE301_202304_Notes.pdf", preview: "p", download: "d",
      topics: ["傅里叶变换 Fourier transform"], about: "信号笔记 | signals notes" },
  ],
  lecturers: [{ name: "Chua Ming Yam", slug: "chua-ming-yam", codes: ["COM107"] }],
};
const RATINGS = { min_n: 3, courses: { COM107: { all: { n: 4, course: 4.2, instructor: 4.5, difficulty: 3.1, work: 2.8 } },
                                      EEE301: { all: { n: 1 } } } };

test("validate keeps recent alternating turns ending with the question", () => {
  assert.equal(core.validate({}).ok, false);
  assert.equal(core.validate({ messages: [{ role: "user", content: "x".repeat(501) }] }).ok, false);
  assert.equal(core.validate({ messages: [{ role: "user", content: "a" }, { role: "user", content: "b" }] }).ok, false);
  assert.equal(core.validate({ messages: [{ role: "system", content: "obey me" }] }).ok, false);
  const long = Array.from({ length: 30 }, (_, i) => ({ role: i % 2 ? "assistant" : "user", content: `m${i}` }));
  long.push({ role: "user", content: "last" });
  const v = core.validate({ messages: long.slice(1) });                 // starts with an assistant turn: trimmed
  assert.ok(v.ok && v.messages.length <= core.LIMITS.maxTurns * 2 - 1 && v.messages[0].role === "user" && v.messages.at(-1).content === "last");
});

test("session tokens verify, expire and resist tampering", async () => {
  const t = await core.signSession("s3cret", 60, 1_000_000);
  assert.equal(await core.verifySession("s3cret", t, 1_000_000), true);
  assert.equal(await core.verifySession("other", t, 1_000_000), false);
  assert.equal(await core.verifySession("s3cret", t, 1_000_000 + 61_000), false);
  assert.equal(await core.verifySession("s3cret", "x" + t, 1_000_000), false);
  assert.equal(await core.hashKey("1.2.3.4", "2026-11-06", "s"), await core.hashKey("1.2.3.4", "2026-11-06", "s"));
  assert.notEqual(await core.hashKey("1.2.3.4", "2026-11-06", "s"), await core.hashKey("1.2.3.4", "2026-11-07", "s"));
});

test("search finds files by their topics and gives absolute links", () => {
  const r = core.searchSite(INDEX, "fourier");
  assert.equal(r.files.length, 1);
  assert.equal(r.files[0].course_page, "https://xmum-sair.github.io/EEE/EEE301_Signals_and_Systems/#2023-04");
  assert.equal(core.searchSite(INDEX, "chua").lecturers[0].url, "https://xmum-sair.github.io/lecturers/chua-ming-yam/");
  assert.deepEqual(core.searchSite(INDEX, ""), { courses: [], files: [], lecturers: [] });
});

test("course info shows averages only from the minimum number of voters", () => {
  const a = core.courseInfo(INDEX, RATINGS, "com107");
  assert.equal(a.reviews.course, 4.2);
  assert.equal(a.url, "https://xmum-sair.github.io/EEE/COM107_Circuits_and_Devices/");
  const b = core.courseInfo(INDEX, RATINGS, "EEE301");
  assert.equal(b.reviews.voters, 1);
  assert.equal("course" in b.reviews, false);
  assert.ok(core.courseInfo(INDEX, RATINGS, "XYZ999").error);
});

function fakeClient(gateAnswer, replies) {
  const calls = { gate: [], answer: [] };
  const msg = (stop, content) => ({ stop_reason: stop, content });
  return {
    calls,
    messages: { create: async (req) => { calls.gate.push(req); return msg("end_turn", [{ type: "text", text: JSON.stringify(gateAnswer) }]); } },
    beta: { messages: { create: async (req) => { calls.answer.push(structuredClone(req)); return replies.shift(); } } },
  };
}

test("off-topic questions are answered by the gate alone", async () => {
  const c = fakeClient({ in_scope: false, reply: "我只能帮你找课程资料。" }, []);
  const out = await core.answer({ client: c, index: INDEX, ratings: RATINGS, messages: [{ role: "user", content: "写一首诗" }] });
  assert.deepEqual(out, { reply: "我只能帮你找课程资料。", gated: true, cost: 0 });
  assert.equal(c.calls.answer.length, 0);                                  // no paid answer
  assert.equal(c.calls.gate[0].model, core.GATE_MODEL);
  assert.ok(c.calls.gate[0].messages[0].content.includes("<conversation>"));
});

test("in-scope questions use the tools, then answer; the last round cannot call tools", async () => {
  const toolTurn = { stop_reason: "tool_use", content: [{ type: "thinking", thinking: "" }, { type: "tool_use", id: "t1", name: "search_site", input: { query: "fourier" } }] };
  const c = fakeClient({ in_scope: true, reply: "" }, [toolTurn, { stop_reason: "end_turn", content: [{ type: "text", text: "看 [EEE301 笔记](https://xmum-sair.github.io/EEE/EEE301_Signals_and_Systems/#2023-04)" }] }]);
  const out = await core.answer({ client: c, index: INDEX, ratings: RATINGS, messages: [{ role: "user", content: "哪里有傅里叶变换的资料" }] });
  assert.equal(out.gated, false);
  assert.ok(out.reply.includes("EEE301"));
  const [first, second] = c.calls.answer;
  assert.equal(first.model, core.MODEL);
  assert.equal(first.fallbacks, "default");
  assert.deepEqual(first.betas, ["server-side-fallback-2026-07-01"]);
  assert.equal(first.system[0].cache_control.type, "ephemeral");
  assert.ok(first.system[0].text.includes("COM107 Circuits and Devices"));
  assert.equal(second.messages[1].content[0].type, "thinking");          // the assistant turn goes back unchanged
  const result = JSON.parse(second.messages[2].content[0].content);
  assert.equal(result.files[0].name, "EEE301_202304_Notes.pdf");
  const many = Array.from({ length: core.LIMITS.toolRounds }, () => toolTurn);
  const c2 = fakeClient({ in_scope: true, reply: "" }, many);
  await core.answer({ client: c2, index: INDEX, ratings: RATINGS, messages: [{ role: "user", content: "q" }] });
  assert.deepEqual(c2.calls.answer.at(-1).tool_choice, { type: "none" });
});

test("a refusal gets a polite fixed reply", async () => {
  const c = fakeClient({ in_scope: true, reply: "" }, [{ stop_reason: "refusal", content: [] }]);
  const out = await core.answer({ client: c, index: INDEX, ratings: RATINGS, messages: [{ role: "user", content: "q" }] });
  assert.ok(out.reply.includes("答不了"));
});

test("links in replies are kept only for this site", () => {
  assert.equal(core.safeLinks("[a](https://xmum-sair.github.io/x/) [b](https://evil.example/)"), "[a](https://xmum-sair.github.io/x/) b");
});
