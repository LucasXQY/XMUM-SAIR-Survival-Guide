// 小帮手的 Cloudflare Worker：只收本站的请求，第一次提问做一次人机验证（Turnstile），每人每天、全站每天都有次数上限，
// 然后交给 core.js 回答。API key 只在这里（Worker secret），网页里没有。
// The helper's Cloudflare Worker: accepts requests from the site only, asks for one human check (Turnstile) per session,
// caps questions per visitor and per day, then lets core.js answer. The API key lives here (a Worker secret), never in the page.
import Anthropic from "@anthropic-ai/sdk";
import { SITE, validate, signSession, verifySession, hashKey, answer } from "./core.js";

const RATINGS_URL = "https://raw.githubusercontent.com/xmum-sair/xmum-sair.github.io/data/ratings.json";
const MAX_BODY = 20000;
let cached = { at: 0, index: null, ratings: null };

export async function siteData(fetcher = fetch, now = Date.now()) {   // the site's own search index and ratings, kept 10 minutes
  if (cached.index && now - cached.at < 600_000) return cached;
  const [index, ratings] = await Promise.all([
    fetcher(SITE + "search.json").then((r) => r.json()),
    fetcher(RATINGS_URL).then((r) => (r.ok ? r.json() : {})).catch(() => ({})),
  ]);
  cached = { at: now, index, ratings };
  return cached;
}

function headers(origin) {
  return { "Content-Type": "application/json; charset=utf-8", "Access-Control-Allow-Origin": origin,
           "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type", "Vary": "Origin" };
}

const json = (data, status, origin) => new Response(JSON.stringify(data), { status, headers: headers(origin) });
const say = (zh, en) => `${zh} | ${en}`;

export async function handle(request, env, deps = {}) {
  const allowed = (env.ALLOWED_ORIGINS || SITE.replace(/\/$/, "")).split(",").map((s) => s.trim());
  const origin = request.headers.get("Origin") || "";
  if (!allowed.includes(origin)) return new Response("forbidden", { status: 403 });
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: headers(origin) });
  if (request.method !== "POST" || new URL(request.url).pathname !== "/chat") return json({ error: "not found" }, 404, origin);
  if (env.PAUSED === "1") return json({ error: say("小帮手暂停中，过一阵再来。", "The helper is paused for now.") }, 503, origin);

  const raw = await request.text();
  if (raw.length > MAX_BODY) return json({ error: "too large" }, 413, origin);
  let body;
  try { body = JSON.parse(raw); } catch { return json({ error: "bad json" }, 400, origin); }
  const v = validate(body);
  if (!v.ok) return json({ error: v.error }, 400, origin);

  // one human check per session; then a signed session token for an hour
  const secret = `${env.TURNSTILE_SECRET}|session`;
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  let session = body.session;
  if (!(await verifySession(secret, session))) {
    if (!body.turnstile) return json({ error: "verify", message: say("先完成人机验证。", "Please complete the human check first.") }, 401, origin);
    const check = await (deps.fetch || fetch)("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST", body: new URLSearchParams({ secret: env.TURNSTILE_SECRET, response: body.turnstile, remoteip: ip }),
    }).then((r) => r.json()).catch(() => ({ success: false }));
    if (!check.success) return json({ error: "verify", message: say("人机验证没通过，请重试。", "The human check failed; please try again.") }, 401, origin);
    session = await signSession(secret);
  }

  // daily caps: per visitor (a hash of the address, never the address itself) and for the whole site
  const day = new Date().toISOString().slice(0, 10);
  const stub = env.LIMITER.get(env.LIMITER.idFromName("global"));
  const take = await stub.fetch("https://limiter/take", { method: "POST", body: JSON.stringify({
    visitor: await hashKey(ip, day, env.TURNSTILE_SECRET), day,
    perVisitor: Number(env.PER_VISITOR_DAILY || 15), global: Number(env.GLOBAL_DAILY || 150) }) }).then((r) => r.json());
  if (!take.ok) {
    const msg = take.reason === "visitor" ? say("你今天的提问次数用完了，明天再来。", "You have used today's questions; come back tomorrow.")
                                          : say("小帮手今天的总次数用完了，明天再来。", "The helper has used today's questions; come back tomorrow.");
    return json({ error: "limit", message: msg, session }, 429, origin);
  }

  try {
    const { index, ratings } = await siteData(deps.fetch || fetch);
    const client = deps.client || new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, maxRetries: 1, timeout: 60_000 });
    const out = await answer({ client, index, ratings, messages: v.messages });
    return json({ reply: out.reply, session }, 200, origin);
  } catch (e) {
    console.log("answer failed:", e && e.message);
    return json({ error: "failed", message: say("小帮手暂时出错，稍后再试。", "The helper hit an error; try again later."), session }, 502, origin);
  }
}

export default { fetch: (request, env) => handle(request, env) };

// One Durable Object counts every question: strongly consistent, and it stores only today's counts.
export class Limiter {
  constructor(ctx) { this.ctx = ctx; }

  async fetch(request) {
    const { visitor, day, perVisitor, global } = await request.json();
    const g = (await this.ctx.storage.get(`g:${day}`)) || 0;
    const u = (await this.ctx.storage.get(`u:${day}:${visitor}`)) || 0;
    if (g >= global) return Response.json({ ok: false, reason: "global" });
    if (u >= perVisitor) return Response.json({ ok: false, reason: "visitor" });
    await this.ctx.storage.put({ [`g:${day}`]: g + 1, [`u:${day}:${visitor}`]: u + 1 });
    if ((await this.ctx.storage.get("day")) !== day) {        // a new day: drop yesterday's counts
      const old = await this.ctx.storage.list();
      await this.ctx.storage.delete([...old.keys()].filter((k) => k !== "day" && !k.includes(`:${day}`)));
      await this.ctx.storage.put("day", day);
    }
    return Response.json({ ok: true, used: g + 1 });
  }
}
