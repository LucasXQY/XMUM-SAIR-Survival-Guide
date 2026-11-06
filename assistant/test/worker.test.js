// Checks for src/worker.js request handling with fakes for Turnstile, the limiter and Claude: npm test.
import { test } from "node:test";
import assert from "node:assert/strict";
import { handle, Limiter } from "../src/worker.js";
import { signSession } from "../src/core.js";

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
