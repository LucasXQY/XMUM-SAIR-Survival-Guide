// XMUM SAIR 生存指南的 Cloudflare Worker，两件事：
// 1. 小帮手（/chat）：只收本站请求，每次会话第一次提问做一次人机验证，每人每天、全站每天有次数上限，由 core.js 回答。
// 2. 课程评价（/vote、/ratings、/admin）：不用登录；每一票都要过人机验证；同一 IP 每天最多 100 票、同一浏览器每天最多 20 票；
//    突增和名单外的老师或课程照常计入但标记待审（reviews.js）。票存在 Durable Object 的 SQLite 里。
// 3. 机会墙与经验帖（/board、/board/post、/board/report）：不用登录，每帖一次人机验证，Haiku 初审（board.js）。
// 4. 讨论区（/forum、/forum/thread、/forum/post、/forum/report、/forum/withdraw）：不用登录，关键词表加 Haiku 审核（forum.js）。
// API key 和口令只在 Worker secret 里，网页里没有。
// The site's Cloudflare Worker: (1) the helper at /chat, (2) course reviews at /vote, /ratings and /admin: no login,
// a human check on every vote, daily caps per address and per browser, suspicious votes counted but flagged for the
// maintainer. Votes live in a Durable Object's SQLite. (3) the opportunity wall and experience posts at /board: no
// login, a human check per post, a first look by Haiku (board.js). (4) the discussion area at /forum: no login, keyword
// lists and Haiku check every thread and reply (forum.js). Keys and the admin token are Worker secrets only.
import Anthropic from "@anthropic-ai/sdk";
import { SITE, validate, signSession, verifySession, hashKey, answer } from "./core.js";
import { reviewsApi } from "./reviews.js";
import { ADMIN_HTML } from "./admin.js";
import { boardApi, validate as validateBoard, moderate } from "./board.js";
import { forumGet, forumPost, forumAdmin, isForumAdmin } from "./forum.js";

const MAX_BODY = 20000;
let cached = { at: 0, index: null, catalog: null, fetcher: null };

export async function siteData(fetcher = fetch, now = Date.now()) {   // the site's search index and course/lecturer list, kept 10 minutes
  if (cached.index && cached.fetcher === fetcher && now - cached.at < 600_000) return cached;
  const index = await fetcher(SITE + "search.json").then((r) => r.json());
  const catalog = { codes: (index.courses || []).map((c) => c.code),
                    pairs: (index.lecturers || []).flatMap((l) => (l.codes || []).map((code) => `${code}|${l.slug}`)) };
  cached = { at: now, index, catalog, fetcher };
  return cached;
}

function headers(origin) {
  return { "Content-Type": "application/json; charset=utf-8", "Access-Control-Allow-Origin": origin,
           "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type", "Vary": "Origin" };
}

const json = (data, status, origin) => new Response(JSON.stringify(data), { status, headers: headers(origin) });
const say = (zh, en) => `${zh} | ${en}`;

async function reviews(env, msg) {
  const stub = env.REVIEWS.get(env.REVIEWS.idFromName("reviews"));
  const r = await stub.fetch("https://reviews/api", { method: "POST", body: JSON.stringify(msg) });
  return { status: r.status, data: await r.json() };
}

async function turnstileOk(env, token, ip, fetcher) {
  if (!token) return false;
  const r = await fetcher("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST", body: new URLSearchParams({ secret: env.TURNSTILE_SECRET, response: token, remoteip: ip }),
  }).then((x) => x.json()).catch(() => ({ success: false }));
  return r.success === true;
}

async function sameSecret(a, b) {   // compare without leaking the length or position of a difference
  const enc = new TextEncoder();
  const [x, y] = await Promise.all([a, b].map((s) => crypto.subtle.digest("SHA-256", enc.encode(String(s || "")))));
  const u = new Uint8Array(x), v = new Uint8Array(y);
  let d = 0;
  for (let i = 0; i < u.length; i++) d |= u[i] ^ v[i];
  return d === 0 && Boolean(b);
}

async function board(env, msg) {
  const stub = env.BOARD.get(env.BOARD.idFromName("board"));
  const r = await stub.fetch("https://board/api", { method: "POST", body: JSON.stringify(msg) });
  return { status: r.status, data: await r.json() };
}

const boardKey = (request) => new Request(new URL("/board", request.url).toString());

async function forgetBoard(request) {   // after a new live post, a hidden one or an admin change, the next load reads fresh posts
  if (typeof caches !== "undefined") await caches.default.delete(boardKey(request));
}

async function boardListRoute(request, env) {
  const cache = typeof caches !== "undefined" ? caches.default : null;
  const key = boardKey(request);
  const hit = cache && (await cache.match(key));
  if (hit) return hit;
  const r = await board(env, { op: "list" });
  const res = new Response(JSON.stringify(r.data), { status: r.status, headers: {
    "Content-Type": "application/json; charset=utf-8", "Access-Control-Allow-Origin": "*", "Cache-Control": "public, max-age=60" } });
  if (cache && r.status === 200) await cache.put(key, res.clone());
  return res;
}

async function boardPostRoute(body, request, env, deps, origin, path) {
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const salt = `${env.TURNSTILE_SECRET}|board`;
  const device = await hashKey("device", String(body.device || "").slice(0, 100) || crypto.randomUUID(), salt);
  if (path === "/board/report") {
    const r = await board(env, { op: "report", id: body.id, device });
    if (r.data.hidden) await forgetBoard(request);
    return json(r.data, r.status, origin);
  }
  if (!(await turnstileOk(env, body.turnstile, ip, deps.fetch || fetch))) {
    return json({ error: "verify", message: say("请先完成人机验证。", "Please complete the human check.") }, 401, origin);
  }
  // the model is asked here in the Worker; its verdict goes to the Durable Object with the post. Invalid posts skip it.
  const v = validateBoard(body);
  let verdict = null;
  if (v.ok) {
    const client = env.PAUSED === "1" ? null : (deps.client || new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, maxRetries: 1, timeout: 30_000 }));
    verdict = await moderate(client, v.post);
  }
  const r = await board(env, { op: "post", body, device, ip: await hashKey("ip", ip, salt), verdict });
  if (r.status === 429) {
    const msg = r.data.reason === "ip"
      ? say("这个网络今天发帖次数已到上限，明天再来。", "This network has reached today's posting limit; please come back tomorrow.")
      : say("你今天发得太多了，明天再来。", "You have posted a lot today; please come back tomorrow.");
    return json({ error: "limit", message: msg }, 429, origin);
  }
  if (r.status === 400) return json({ error: "invalid", message: say(`还差：${r.data.problems.join("、")}`, "Some fields need fixing."), problems: r.data.problems }, 400, origin);
  if (r.status === 200 && r.data.status === "live") await forgetBoard(request);
  return json(r.data, r.status, origin);
}

const ratingsKey = (request) => new Request(new URL("/ratings", request.url).toString());

async function forgetRatings(request) {   // after a vote or a keep/drop, the next page load reads fresh numbers
  if (typeof caches !== "undefined") await caches.default.delete(ratingsKey(request));
}

async function ratingsRoute(request, env, deps) {
  const cache = typeof caches !== "undefined" ? caches.default : null;
  const key = ratingsKey(request);
  const hit = cache && (await cache.match(key));
  if (hit) return hit;
  const { catalog } = await siteData(deps.fetch || fetch);
  const r = await reviews(env, { op: "ratings", site: catalog });
  const res = new Response(JSON.stringify(r.data), { status: r.status, headers: {
    "Content-Type": "application/json; charset=utf-8", "Access-Control-Allow-Origin": "*", "Cache-Control": "public, max-age=60" } });
  if (cache && r.status === 200) await cache.put(key, res.clone());
  return res;
}

async function adminRoute(request, env, deps) {
  let body;
  try { body = JSON.parse(await request.text()); } catch { return new Response("bad json", { status: 400 }); }
  if (!(await sameSecret(body.token, env.REVIEWS_ADMIN_TOKEN))) return new Response(JSON.stringify({ error: "token" }), { status: 401 });
  if (isForumAdmin(body.op)) return forumAdmin(request, env, body);
  const boardOps = { board_list: "admin_list", board_approve: "approve", board_remove: "remove" };
  if (boardOps[body.op]) {
    const r = await board(env, { op: boardOps[body.op], ids: body.ids });
    if (body.op !== "board_list") await forgetBoard(request);
    return new Response(JSON.stringify(r.data), { status: r.status, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" } });
  }
  const ops = new Set(["list", "keep", "drop", "summary", "lecturers", "import"]);
  if (!ops.has(body.op)) return new Response(JSON.stringify({ error: "unknown op" }), { status: 400 });
  const { catalog } = await siteData(deps.fetch || fetch);
  const r = await reviews(env, { op: body.op, keys: body.keys, votes: body.votes, site: catalog });
  if (["keep", "drop", "import"].includes(body.op)) await forgetRatings(request);
  return new Response(JSON.stringify(r.data), { status: r.status, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" } });
}

async function voteRoute(body, request, env, deps, origin) {
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  if (!(await turnstileOk(env, body.turnstile, ip, deps.fetch || fetch))) {
    return json({ error: "verify", message: say("请先完成人机验证。", "Please complete the human check.") }, 401, origin);
  }
  const salt = `${env.TURNSTILE_SECRET}|reviews`;
  const { catalog } = await siteData(deps.fetch || fetch);
  const r = await reviews(env, {
    op: "vote", body, site: catalog,
    ip: await hashKey("ip", ip, salt),                                     // addresses and browsers only as salted hashes
    voter: `web:${await hashKey("device", String(body.device || "").slice(0, 100) || crypto.randomUUID(), salt)}`,
  });
  if (r.status === 429) {
    const msg = r.data.reason === "ip"
      ? say("这个网络今天的评价次数已到上限，明天再来。", "This network has reached today's limit; please come back tomorrow.")
      : say("你今天评价得太多了，明天再来。", "You have rated a lot today; please come back tomorrow.");
    return json({ error: "limit", message: msg }, 429, origin);
  }
  if (r.status === 200) await forgetRatings(request);
  if (r.status === 400) return json({ error: "invalid", message: say(`还差：${r.data.problems.join("、")}`, "Some fields are missing."), problems: r.data.problems }, 400, origin);
  return json(r.data, r.status, origin);
}

async function chatRoute(body, request, env, deps, origin) {
  if (env.PAUSED === "1") return json({ error: say("小帮手暂停中，过一阵再来。", "The helper is paused for now.") }, 503, origin);
  const v = validate(body);
  if (!v.ok) return json({ error: v.error }, 400, origin);
  // one human check per session; then a signed session token for an hour
  const secret = `${env.TURNSTILE_SECRET}|session`;
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  let session = body.session;
  if (!(await verifySession(secret, session))) {
    if (!body.turnstile) return json({ error: "verify", message: say("先完成人机验证。", "Please complete the human check first.") }, 401, origin);
    if (!(await turnstileOk(env, body.turnstile, ip, deps.fetch || fetch))) {
      return json({ error: "verify", message: say("人机验证没通过，请重试。", "The human check failed; please try again.") }, 401, origin);
    }
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
    const { index, catalog } = await siteData(deps.fetch || fetch);
    const ratings = env.REVIEWS ? (await reviews(env, { op: "ratings", site: catalog })).data : {};
    const client = deps.client || new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, maxRetries: 1, timeout: 60_000 });
    const out = await answer({ client, index, ratings, messages: v.messages });
    return json({ reply: out.reply, session }, 200, origin);
  } catch (e) {
    console.log("answer failed:", e && e.message);
    return json({ error: "failed", message: say("小帮手暂时出错，稍后再试。", "The helper hit an error; try again later."), session }, 502, origin);
  }
}

export async function handle(request, env, deps = {}) {
  const path = new URL(request.url).pathname;
  // public or token-protected routes
  if (path === "/ratings" && request.method === "GET") return ratingsRoute(request, env, deps);
  if (path === "/board" && request.method === "GET") return boardListRoute(request, env);
  if ((path === "/forum" || path === "/forum/thread") && request.method === "GET") return forumGet(request, env, path);
  if (path === "/admin" && request.method === "GET") {
    return new Response(ADMIN_HTML, { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store",
                                                 "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer" } });
  }
  if (path === "/admin/api" && request.method === "POST") return adminRoute(request, env, deps);
  // the rest only for the site's own pages
  const allowed = (env.ALLOWED_ORIGINS || SITE.replace(/\/$/, "")).split(",").map((s) => s.trim());
  const origin = request.headers.get("Origin") || "";
  if (!allowed.includes(origin)) return new Response("forbidden", { status: 403 });
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: headers(origin) });
  const routes = ["/chat", "/vote", "/board/post", "/board/report", "/forum/post", "/forum/report", "/forum/withdraw"];
  if (request.method !== "POST" || !routes.includes(path)) return json({ error: "not found" }, 404, origin);
  const raw = await request.text();
  if (raw.length > MAX_BODY) return json({ error: "too large" }, 413, origin);
  let body;
  try { body = JSON.parse(raw); } catch { return json({ error: "bad json" }, 400, origin); }
  if (path.startsWith("/board/")) return boardPostRoute(body, request, env, deps, origin, path);
  if (path.startsWith("/forum/")) {
    const client = () => deps.client || new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, maxRetries: 1, timeout: 30_000 });
    return forumPost(body, request, env, deps, origin, path, { json, turnstileOk, siteData, client });
  }
  return path === "/vote" ? voteRoute(body, request, env, deps, origin) : chatRoute(body, request, env, deps, origin);
}

export default { fetch: (request, env) => handle(request, env) };
export { Forum } from "./forum.js";   // the discussion area's Durable Object

// One Durable Object counts every helper question: strongly consistent, and it stores only today's counts.
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

// The course reviews: one Durable Object, its votes in SQLite (rows: one per browser or GitHub voter, course and lecturer).
export class SqlStore {
  constructor(sql) {
    this.sql = sql;
    sql.exec(`CREATE TABLE IF NOT EXISTS votes (code TEXT NOT NULL, lk TEXT NOT NULL, voter TEXT NOT NULL, name TEXT, session TEXT,
              scores TEXT, ip TEXT, at INTEGER, flags TEXT, status TEXT, reviewed INTEGER, source TEXT, PRIMARY KEY (code, lk, voter))`);
    sql.exec("CREATE TABLE IF NOT EXISTS counters (k TEXT PRIMARY KEY, n INTEGER NOT NULL)");
  }

  static row(r) {
    return r && { code: r.code, lecturerKey: r.lk, voter: r.voter, name: r.name, session: r.session, scores: JSON.parse(r.scores || "{}"),
                  ip: r.ip, at: r.at, flags: JSON.parse(r.flags || "[]"), status: r.status, reviewed: r.reviewed === 1, source: r.source };
  }

  async getVote(code, lk, voter) { return SqlStore.row(this.sql.exec("SELECT * FROM votes WHERE code = ? AND lk = ? AND voter = ?", code, lk, voter).toArray()[0]); }

  async putVote(v) {
    this.sql.exec("INSERT OR REPLACE INTO votes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", v.code, v.lecturerKey, v.voter, v.name, v.session || "",
                  JSON.stringify(v.scores), v.ip || "", v.at, JSON.stringify(v.flags || []), v.status, v.reviewed ? 1 : 0, v.source);
  }

  async recent(code, lk, since) {
    return this.sql.exec("SELECT * FROM votes WHERE code = ? AND lk = ? AND status = 'ok' AND at >= ?", code, lk, since).toArray().map(SqlStore.row);
  }

  async count(key, day) { return this.sql.exec("SELECT n FROM counters WHERE k = ?", `${key}|${day}`).toArray()[0]?.n || 0; }

  async bump(key, day) {
    this.sql.exec("INSERT INTO counters (k, n) VALUES (?, 1) ON CONFLICT (k) DO UPDATE SET n = n + 1", `${key}|${day}`);
    this.sql.exec("DELETE FROM counters WHERE k NOT LIKE ?", `%|${day}`);   // only today's counters are kept
  }

  async all() { return this.sql.exec("SELECT * FROM votes").toArray().map(SqlStore.row); }
}

export class Reviews {
  constructor(ctx) { this.store = new SqlStore(ctx.storage.sql); }

  async fetch(request) {
    const r = await reviewsApi(this.store, await request.json());
    return new Response(JSON.stringify(r.data), { status: r.status, headers: { "Content-Type": "application/json" } });
  }
}

// The opportunity wall and experience posts: one Durable Object, posts, reports and today's counters in SQLite.
export class BoardStore {
  constructor(sql) {
    this.sql = sql;
    sql.exec(`CREATE TABLE IF NOT EXISTS posts (id TEXT PRIMARY KEY, kind TEXT, cat TEXT, title TEXT, body TEXT, fields TEXT, author TEXT,
              at INTEGER, status TEXT, reason TEXT, reports INTEGER, ip TEXT, device TEXT)`);
    sql.exec("CREATE TABLE IF NOT EXISTS counters (k TEXT PRIMARY KEY, n INTEGER NOT NULL)");
    sql.exec("CREATE TABLE IF NOT EXISTS reports (id TEXT NOT NULL, device TEXT NOT NULL, PRIMARY KEY (id, device))");
  }

  static row(r) { return r && { ...r, fields: JSON.parse(r.fields || "{}") }; }

  async get(id) { return BoardStore.row(this.sql.exec("SELECT * FROM posts WHERE id = ?", id).toArray()[0]); }

  async put(p) {
    this.sql.exec("INSERT OR REPLACE INTO posts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", p.id, p.kind, p.cat, p.title, p.body,
                  JSON.stringify(p.fields || {}), p.author || "", p.at, p.status, p.reason || "", p.reports || 0, p.ip || "", p.device || "");
  }

  async all() { return this.sql.exec("SELECT * FROM posts").toArray().map(BoardStore.row); }

  async count(key, day) { return this.sql.exec("SELECT n FROM counters WHERE k = ?", `${key}|${day}`).toArray()[0]?.n || 0; }

  async bump(key, day) {
    this.sql.exec("INSERT INTO counters (k, n) VALUES (?, 1) ON CONFLICT (k) DO UPDATE SET n = n + 1", `${key}|${day}`);
    this.sql.exec("DELETE FROM counters WHERE k NOT LIKE ?", `%|${day}`);
  }

  async report(id, device) {
    if (this.sql.exec("SELECT 1 FROM reports WHERE id = ? AND device = ?", id, device).toArray().length) return false;
    this.sql.exec("INSERT INTO reports VALUES (?, ?)", id, device);
    return true;
  }
}

export class Board {
  constructor(ctx) { this.store = new BoardStore(ctx.storage.sql); }

  async fetch(request) {
    const r = await boardApi(this.store, await request.json());
    return new Response(JSON.stringify(r.data), { status: r.status, headers: { "Content-Type": "application/json" } });
  }
}
