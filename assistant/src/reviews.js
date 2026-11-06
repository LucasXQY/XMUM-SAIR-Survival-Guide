// 课程评价（Worker 版）：校验一票、防刷分规则、汇总成和旧 ratings.json 一样的格式。存储接口有两个实现：
// 测试用的 MemoryStore 和 Durable Object 里的 SQL（worker.js）。
// Course reviews on the Worker: checking a vote, the anti-stuffing rules, and the aggregate in the old ratings.json
// shape. The store has two implementations: MemoryStore for tests and the Durable Object's SQL (worker.js).

export const DIMS = ["course", "instructor", "difficulty", "work", "learned", "communication", "access", "recommend"];
export const MAIN = ["course", "instructor", "difficulty", "work"];
export const MIN_N = 3;                       // below this many voters only the count is published
// The address is used for one thing only, the daily hard cap: a whole class can share one campus address, so it never
// makes a vote suspicious (maintainer's rule, 2026-11-06).
export const LIMITS = {
  perIpDaily: 100,     // hard cap per address
  perVoterDaily: 20,   // hard cap per browser
  burstPerHour: 8,     // more votes than this for one course and lecturer within an hour: flagged
};
const CODE_RE = /^[A-Z]{1,4}(?:\d{3,4}|\d\.\d)$/;
const SESSION_RE = /^\d{4}-\d{2}$/;
const TITLE_RE = /^(?:dr|prof|professor|assoc|associate|asst|assistant|puan|encik|en|cik|mr|mrs|ms|ir|ts)\.?\s+/i;
const HOUR = 3600_000;

export function displayName(name) {
  let n = String(name || "").normalize("NFKC").replace(/\s+/g, " ").trim();
  while (TITLE_RE.test(n)) n = n.replace(TITLE_RE, "");
  return n;
}

export function lecturerKey(name) {   // same key as the old GitHub bot (reviews/reviews.py) and the site's lecturer pages
  return displayName(name).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
}

function cleanScores(raw) {
  const out = {};
  for (const d of DIMS) {
    const v = raw ? raw[d] : undefined;
    if (Number.isInteger(v) && v >= 1 && v <= 5) out[d] = v;
  }
  return out;
}

export function validate(body) {
  const b = body || {};
  const code = String(b.code || "").trim().toUpperCase().replace(/\s+/g, "");
  const lecturer = displayName(b.lecturer);
  const session = String(b.session || "").trim();
  const problems = [];
  if (!CODE_RE.test(code)) problems.push("课程代码 | course code");
  if (!lecturer || lecturer.length > 80 || !lecturerKey(lecturer)) problems.push("老师 | lecturer");
  if (session && !SESSION_RE.test(session)) problems.push("学期 | session");
  const scores = cleanScores(b.scores);
  if (MAIN.some((d) => !(d in scores))) problems.push("四个主维度都要打分 | all four main scores");
  if (b.confirm !== true) problems.push("确认 | confirmation");
  if (problems.length) return { ok: false, problems };
  return { ok: true, vote: { code, lecturer, session, scores } };
}

// ctx: { voter, ip, now, site: { codes: Set, pairs: Set("CODE|lecturer-key") } }
export async function decide(store, v, ctx) {
  const day = new Date(ctx.now).toISOString().slice(0, 10);
  if ((await store.count(`ip:${ctx.ip}`, day)) >= LIMITS.perIpDaily) return { action: "reject", reason: "ip" };
  if ((await store.count(`voter:${ctx.voter}`, day)) >= LIMITS.perVoterDaily) return { action: "reject", reason: "voter" };
  const lk = lecturerKey(v.lecturer);
  const prev = await store.getVote(v.code, lk, ctx.voter);
  const flags = [];
  if (!ctx.site.codes.has(v.code) || !ctx.site.pairs.has(`${v.code}|${lk}`)) flags.push("new_name");
  const lastHour = (await store.recent(v.code, lk, ctx.now - HOUR)).filter((x) => x.voter !== ctx.voter);
  if (lastHour.length >= LIMITS.burstPerHour) flags.push("burst");
  await store.putVote({ code: v.code, lecturerKey: lk, name: v.lecturer, voter: ctx.voter, session: v.session, scores: v.scores,
                        ip: ctx.ip, at: ctx.now, flags, status: "ok", reviewed: flags.length === 0, source: "web" });
  await store.bump(`ip:${ctx.ip}`, day);
  await store.bump(`voter:${ctx.voter}`, day);
  return { action: "save", replaced: Boolean(prev), flags };
}

export async function importVotes(store, list) {
  let n = 0;
  for (const raw of list || []) {
    const code = String(raw.code || "").trim().toUpperCase();
    const name = displayName(raw.name || raw.lecturer);
    const scores = cleanScores(raw.scores);
    const at = Date.parse(raw.at) || 0;
    if (!CODE_RE.test(code) || !lecturerKey(name) || !raw.voter || MAIN.some((d) => !(d in scores))) continue;
    n++;
    const voter = `gh:${raw.voter}`, lk = lecturerKey(name);
    const prev = await store.getVote(code, lk, voter);
    if (prev && prev.at >= at) continue;
    await store.putVote({ code, lecturerKey: lk, name, voter, session: String(raw.session || ""), scores, ip: "", at,
                          flags: [], status: "ok", reviewed: true, source: "github" });
  }
  return n;
}

function summary(votes) {
  const entry = { n: votes.length, counts: {} };
  for (const d of DIMS) entry.counts[d] = votes.filter((v) => d in v.scores).length;
  if (votes.length >= MIN_N) {
    for (const d of DIMS) {
      const vals = votes.filter((v) => d in v.scores).map((v) => v.scores[d]);
      entry[d] = vals.length >= MIN_N ? Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 10) / 10 : null;
    }
  }
  return entry;
}

export function aggregate(votes, generated = new Date().toISOString().replace(/\.\d+Z$/, "Z")) {
  const out = { generated, min_n: MIN_N, dims: DIMS, main: MAIN, courses: {} };
  const groups = new Map(), latest = new Map();
  for (const v of votes) {
    if (v.status !== "ok") continue;
    const g = `${v.code}|${v.lecturerKey}`;
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(v);
    if (!latest.has(v.code)) latest.set(v.code, new Map());
    const byVoter = latest.get(v.code);
    if (!byVoter.has(v.voter) || v.at > byVoter.get(v.voter).at) byVoter.set(v.voter, v);
  }
  for (const [g, vs] of [...groups.entries()].sort()) {
    const [code, lk] = g.split("|");
    const entry = summary(vs);
    entry.name = vs.reduce((a, b) => (b.at > a.at ? b : a)).name;
    if (!out.courses[code]) out.courses[code] = { lecturers: {} };
    out.courses[code].lecturers[lk] = entry;
  }
  for (const [code, byVoter] of latest) out.courses[code].all = summary([...byVoter.values()]);
  return out;
}

export class MemoryStore {
  constructor() { this.votes = new Map(); this.counters = new Map(); }
  async getVote(code, lk, voter) { return this.votes.get(`${code}|${lk}|${voter}`); }
  async putVote(v) { this.votes.set(`${v.code}|${v.lecturerKey}|${v.voter}`, { ...v }); }
  async recent(code, lk, since) { return [...this.votes.values()].filter((v) => v.code === code && v.lecturerKey === lk && v.status === "ok" && v.at >= since); }
  async count(key, day) { return this.counters.get(`${key}|${day}`) || 0; }
  bump(key, day) { this.counters.set(`${key}|${day}`, (this.counters.get(`${key}|${day}`) || 0) + 1); }
  async all() { return [...this.votes.values()]; }
}

// ---------------------------------------------------------------- the Durable Object's API (any store)

export const UNCONFIRMED = "待确认的老师 | unconfirmed lecturer";
const keyOf = (v) => `${v.code}|${v.lecturerKey}|${v.voter}`;

// A lecturer or course the site does not list shows only after the maintainer kept one of its votes, so a rude
// "lecturer name" or "course code" never reaches the page; its scores count from the start all the same.
export function publicView(agg, votes, site) {
  const codes = new Set(site.codes || []), pairs = new Set(site.pairs || []);
  const kept = new Set(votes.filter((v) => v.status === "ok" && v.reviewed).map((v) => `${v.code}|${v.lecturerKey}`));
  const keptCodes = new Set([...kept].map((k) => k.split("|")[0]));
  for (const code of Object.keys(agg.courses)) {
    if (!codes.has(code) && !keptCodes.has(code)) { delete agg.courses[code]; continue; }
    for (const [lk, e] of Object.entries(agg.courses[code].lecturers)) {
      if (!pairs.has(`${code}|${lk}`) && !kept.has(`${code}|${lk}`)) e.name = UNCONFIRMED;
    }
  }
  return agg;
}

const strip = (v) => ({ key: keyOf(v), code: v.code, lecturer: v.name, session: v.session, scores: v.scores, flags: v.flags,
                        at: new Date(v.at).toISOString(), ip: (v.ip || "").slice(0, 8), voter: (v.voter || "").slice(0, 10) });

// msg: { op, site: {codes, pairs}, ... } → { status, data }
export async function reviewsApi(store, msg, now = Date.now()) {
  const site = { codes: new Set(msg.site?.codes || []), pairs: new Set(msg.site?.pairs || []) };
  const all = () => store.all();
  switch (msg.op) {
    case "vote": {
      const v = validate(msg.body);
      if (!v.ok) return { status: 400, data: { problems: v.problems } };
      const d = await decide(store, v.vote, { voter: msg.voter, ip: msg.ip, now, site });
      if (d.action === "reject") return { status: 429, data: { reason: d.reason } };
      const agg = publicView(aggregate(await all()), await all(), msg.site || {});
      return { status: 200, data: { replaced: d.replaced, course: agg.courses[v.vote.code] || null } };
    }
    case "ratings": {
      const votes = await all();
      return { status: 200, data: publicView(aggregate(votes), votes, msg.site || {}) };
    }
    case "list": {
      const votes = (await all()).filter((v) => v.status === "ok" && !v.reviewed).sort((a, b) => b.at - a.at);
      return { status: 200, data: { votes: votes.map(strip) } };
    }
    case "keep":
    case "drop": {
      const keys = new Set(msg.keys || []);
      let n = 0;
      for (const v of await all()) {
        if (!keys.has(keyOf(v))) continue;
        await store.putVote({ ...v, reviewed: true, status: msg.op === "drop" ? "rejected" : v.status });
        n++;
      }
      return { status: 200, data: { changed: n } };
    }
    case "import":
      return { status: 200, data: { imported: await importVotes(store, msg.votes) } };
    case "lecturers": {
      const seen = new Map();
      for (const v of await all()) {
        if (v.status !== "ok" || !v.reviewed) continue;
        const k = `${v.code}|${v.lecturerKey}|${v.session}`;
        if (!seen.has(k)) seen.set(k, { code: v.code, name: v.name, session: v.session || "unknown" });
      }
      return { status: 200, data: { lecturers: [...seen.values()] } };
    }
    case "summary": {
      const votes = await all();
      const open = votes.filter((v) => v.status === "ok" && !v.reviewed);
      const byFlag = {};
      for (const v of open) for (const f of v.flags || []) byFlag[f] = (byFlag[f] || 0) + 1;
      return { status: 200, data: { total: votes.length, unreviewed: open.length, dropped: votes.filter((v) => v.status === "rejected").length, by_flag: byFlag } };
    }
    default:
      return { status: 400, data: { error: "unknown op" } };
  }
}
