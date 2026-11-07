"""Claude 的第二意见：给审核机器人和上传机器人用。拿不到可信的答案就返回 None，调用方退回原来的规则。
A second opinion from Claude for the moderation and upload bots. Whenever there is no answer to trust, it returns None
and the caller falls back to its own rules.

- 每类任务每天有调用上限，计数放在 bot-state 分支的 claude-usage.json（用文件的 sha 做乐观写入，并发也不会多算）。
  Each task has a daily call limit; the count lives in claude-usage.json on the bot-state branch (optimistic writes keyed
  on the file's sha, so concurrent runs cannot overspend).
- 同一个文件还按池（pool）记美元：每天、每月各有上限（POOL_CAPS，可用 CLAUDE_USD_<PERIOD>_<POOL> 改）。
  The same file also keeps US dollars per pool, with day and month caps (POOL_CAPS; override with CLAUDE_USD_<PERIOD>_<POOL>).
- 模型可用仓库变量 CLAUDE_MODEL_<TASK> 改；按次数的上限 CLAUDE_DAILY_<TASK>（有默认值时）是美元上限之外的第二道保险。
  The model comes from the repository variable CLAUDE_MODEL_<TASK>; the per-task count limit CLAUDE_DAILY_<TASK> (where one has a default) is a second guard beside the dollar caps.
- 需要 ANTHROPIC_API_KEY；没有、额度用完、出错、Claude 拒答，一律返回 None。
  Needs ANTHROPIC_API_KEY; missing key, exhausted credit, any error or a refusal all give None.
"""
from __future__ import annotations

import base64
import datetime
import json
import os
import subprocess
import sys

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_MODELS = {"moderation": "claude-haiku-5-5", "classify": "claude-haiku-5-5", "topics": "claude-haiku-5-5"}   # maintainer: Haiku for bulk sorting (2026-11-06)
# models that take the server-side refusal fallback ("default" routes a declined request to Anthropic's recommended model)
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
STATE_BRANCH, STATE_FILE = "bot-state", "claude-usage.json"

# USD per million tokens; the Cloudflare Worker reads the same file, so it stays plain JSON
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "prices.json"), encoding="utf-8") as _f:
    PRICES = json.load(_f)


def cost_usd(model: str, usage) -> float:
    """Dollar cost of one call. `usage` is an SDK object or a dict; a missing or None count is 0. An unknown model is
    priced as the dearest known one; a long prompt (input + cache write + cache read over the tier limit) uses the long rates."""
    def n(key: str) -> int:
        v = usage.get(key) if isinstance(usage, dict) else getattr(usage, key, None)
        return v or 0
    inp, out, cw, cr = n("input_tokens"), n("output_tokens"), n("cache_creation_input_tokens"), n("cache_read_input_tokens")
    table = PRICES["usd_per_million"]
    rates = table.get(model) or table[PRICES["unknown_model"]]
    tier = PRICES["long_prompt"].get(model)
    if tier and inp + cw + cr > tier["over_tokens"]:
        rates = tier
    return (inp * rates["input"] + out * rates["output"] + cw * rates["cache_write"] + cr * rates["cache_read"]) / 1_000_000


def model_for(task: str) -> str:
    return os.environ.get(f"CLAUDE_MODEL_{task.upper()}", "").strip() or DEFAULT_MODELS.get(task, DEFAULT_MODEL)


def daily_limit(task: str, default: int) -> int:
    raw = os.environ.get(f"CLAUDE_DAILY_{task.upper()}", "").strip()
    return int(raw) if raw.isdigit() else default


def _gh(*args: str, input: str | None = None) -> str:
    r = subprocess.run(["gh", *args], text=True, capture_output=True, encoding="utf-8", input=input)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}: {(r.stderr or r.stdout).strip()[-500:]}")
    return r.stdout.strip()


class Conflict(RuntimeError):
    """Someone else changed the file since it was read; read again."""


class StateFile:
    """One JSON file on the bot-state branch (an orphan branch: it never touches main or the data branch), read and
    written through the contents API with the file's sha, so a stale write fails instead of overwriting."""

    def __init__(self, repo: str, name: str, gh=_gh):
        self.repo, self.name, self.gh = repo, name, gh

    def read(self) -> tuple[dict, str | None]:
        try:
            d = json.loads(self.gh("api", f"repos/{self.repo}/contents/{self.name}?ref={STATE_BRANCH}"))
        except RuntimeError as e:
            if "404" in str(e):
                return {}, None
            raise
        raw = base64.b64decode(d.get("content") or "").decode("utf-8")
        if not raw and d.get("size"):   # over 1 MB the contents API leaves the content out: fetch it raw
            raw = self.gh("api", "-H", "Accept: application/vnd.github.raw", f"repos/{self.repo}/contents/{self.name}?ref={STATE_BRANCH}")
        return json.loads(raw or "{}"), d["sha"]

    def write(self, data: dict, sha: str | None, message: str) -> None:
        body = {"message": message, "branch": STATE_BRANCH,
                "content": base64.b64encode(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).decode()}
        if sha:
            body["sha"] = sha
        for attempt in range(2):
            try:
                self.gh("api", "-X", "PUT", f"repos/{self.repo}/contents/{self.name}", "--input", "-", input=json.dumps(body))
                return
            except RuntimeError as e:
                if "409" in str(e) or "does not match" in str(e):
                    raise Conflict(str(e))
                if attempt == 0 and ("404" in str(e) or "not found" in str(e).lower()):
                    self._create_branch()
                    continue
                raise

    def _create_branch(self) -> None:
        tree = {"tree": [{"path": "README.md", "mode": "100644", "type": "blob",
                          "content": "机器人状态（Claude 调用计数、知识点索引），勿手改 | Bot state (Claude call counts, topic index); do not edit.\n"}]}
        t = json.loads(self.gh("api", "-X", "POST", f"repos/{self.repo}/git/trees", "--input", "-", input=json.dumps(tree)))["sha"]
        c = json.loads(self.gh("api", "-X", "POST", f"repos/{self.repo}/git/commits", "--input", "-",
                               input=json.dumps({"message": "bot-state: start", "tree": t, "parents": []})))["sha"]
        self.gh("api", "-X", "POST", f"repos/{self.repo}/git/refs", "--input", "-",
                input=json.dumps({"ref": f"refs/heads/{STATE_BRANCH}", "sha": c}))


# which spending pool a task draws on, and the dollar caps per pool (USD); repository variables CLAUDE_USD_<PERIOD>_<POOL> override
TASK_POOLS = {"moderation": "haiku", "classify": "haiku", "topics": "haiku", "sort": "upload", "upload": "upload"}
POOL_CAPS = {"upload": {"day": 15, "month": 60, "run": 8}, "haiku": {"day": 2, "month": 10}}


def pool_of(task: str) -> str:
    return TASK_POOLS.get(task, task)


def usd_cap(pool: str, period: str) -> float:
    """Dollar cap of a pool for "day", "month" or "run"; a bad variable falls back to the default, no cap at all is inf."""
    raw = os.environ.get(f"CLAUDE_USD_{period.upper()}_{pool.upper()}", "").strip()
    try:
        v = float(raw)
        if v >= 0 and v != float("inf"):
            return v
    except ValueError:
        pass
    return float(POOL_CAPS.get(pool, {}).get(period, float("inf")))


def _amount(v) -> float:
    """A stored total: a number, clamped at 0. Anything else means the file cannot be trusted."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        raise ValueError(f"bad amount in usage file: {v!r}")
    return max(0.0, float(v))


def _table(v) -> dict:
    if not isinstance(v, dict):
        raise ValueError("bad table in usage file")
    return {str(k): _amount(x) for k, x in v.items()}


class Budget:
    """What Claude may still cost today: calls per task (today only) and US dollars per pool (today and this month),
    all in one file, so one write changes both. take() and reserve() record the spend only if it fits under every cap;
    anything unexpected counts as no (a broken ledger must not mean unlimited spending). settle() corrects a reservation
    with what the call really cost; it never raises, but a failed settle shuts the ledger for the rest of the run."""

    def __init__(self, repo: str, gh=_gh, today: str | None = None):
        self.file = StateFile(repo, STATE_FILE, gh)
        self.today = today or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        self.month = self.today[:7]
        self.broken = False

    def _load(self) -> tuple[dict, str | None]:
        """The ledger for today; a file from an earlier day or month has those parts cleared, an old-shape file is empty."""
        data, sha = self.file.read()
        if not isinstance(data, dict):
            raise ValueError("usage file is not an object")
        # An older stored day or month is cleared; a LATER one (another run started after midnight) is kept and this
        # run's spend is added on top of it, so a late write never rolls the ledger back or counts less than was spent.
        def kept(stored, mine):
            return stored if isinstance(stored, str) and stored >= mine else None
        day, month = kept(data.get("day"), self.today), kept(data.get("month"), self.month)
        return {"day": day or self.today, "month": month or self.month,
                "calls": _table(data.get("calls", {})) if day else {},
                "usd_day": _table(data.get("usd_day", {})) if day else {},
                "usd_month": _table(data.get("usd_month", {})) if month else {}}, sha

    def _update(self, change) -> bool:
        """Read, let change(ledger) edit it (False = refuse), write with the sha; read again on a Conflict."""
        for _ in range(5):
            ledger, sha = self._load()
            if not change(ledger):
                return False
            try:
                self.file.write(ledger, sha, f"claude usage {self.today}")
                return True
            except Conflict:
                continue                                      # someone else wrote first: read again
        raise Conflict("usage file kept changing")

    def take(self, task: str, n: int, limit: int, usd: float = 0.0) -> bool:
        """Count n calls of the task against limit and reserve usd in its pool, in one write; False if either would exceed."""
        return self._spend(task, pool_of(task), n, limit, usd)

    def _spend(self, task: str, pool: str, n: int, limit: int, usd: float) -> bool:
        if n <= 0 and usd == 0:
            return True
        if self.broken or not usd >= 0:
            return False

        def change(ledger: dict) -> bool:
            if n > 0 and ledger["calls"].get(task, 0) + n > limit:
                print(f"claude ({task}): daily limit {limit} reached", file=sys.stderr)
                return False
            day, month = round(ledger["usd_day"].get(pool, 0) + usd, 6), round(ledger["usd_month"].get(pool, 0) + usd, 6)
            if day > usd_cap(pool, "day") or month > usd_cap(pool, "month"):
                print(f"claude ({task}): dollar cap of pool {pool} reached", file=sys.stderr)
                return False
            if n > 0:
                ledger["calls"][task] = ledger["calls"].get(task, 0) + n
            if usd > 0:
                ledger["usd_day"][pool], ledger["usd_month"][pool] = day, month
            return True
        try:
            return self._update(change)
        except Exception as e:
            print(f"claude ({task}): usage counter unavailable, not calling Claude: {e}", file=sys.stderr)
        return False

    def reserve(self, pool: str, usd: float) -> bool:
        """Set aside usd in the pool before a call; True if it fits under the day and month caps."""
        return self._spend(pool, pool, 0, 0, usd)

    def settle(self, pool: str, delta: float) -> None:
        """Add delta (negative = give back) to the pool's totals, never below 0. Never raises."""
        def change(ledger: dict) -> bool:
            for key in ("usd_day", "usd_month"):
                ledger[key][pool] = max(0.0, round(ledger[key].get(pool, 0) + delta, 6))
            return True
        try:
            if not delta == delta or delta in (float("inf"), float("-inf")):
                raise ValueError(f"bad delta {delta!r}")
            self._update(change)
        except Exception as e:
            self.broken = True
            print(f"claude ({pool}): could not settle {delta} USD, no more calls this run: {e}", file=sys.stderr)

    def spent(self, pool: str) -> tuple[float, float]:
        """(today, this month) dollars in the pool; (inf, inf) if the ledger cannot be read."""
        try:
            ledger, _ = self._load()
            return ledger["usd_day"].get(pool, 0.0), ledger["usd_month"].get(pool, 0.0)
        except Exception as e:
            print(f"claude ({pool}): usage counter unavailable: {e}", file=sys.stderr)
            return float("inf"), float("inf")


def ask(task: str, system: str, content, schema: dict, max_tokens: int = 4000, client=None, model: str | None = None, on_cost=None) -> dict | None:
    """Claude's answer as a dict matching `schema`, or None. `content` is the user turn: a string or content blocks.
    `on_cost(usd)` is called once whenever the API returned a response (answer or not), never when the call raised."""
    try:
        import anthropic
    except ImportError:
        anthropic = None
    if client is None:
        if anthropic is None or not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        client = anthropic.Anthropic(max_retries=2, timeout=180)
    model = model or model_for(task)
    kw = {"model": model, "max_tokens": max_tokens, "system": system,
          "messages": [{"role": "user", "content": content}],
          # a classification: low effort keeps thinking short; the schema makes the answer parseable
          "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}
    try:
        if model in FALLBACK_MODELS:
            r = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)
        else:
            r = client.messages.create(**kw)
    except Exception as e:  # every failure means "no answer"; the caller's rules take over
        if anthropic is not None and isinstance(e, anthropic.RateLimitError):
            why = "rate limited"
        elif anthropic is not None and isinstance(e, anthropic.APIStatusError):
            why = f"HTTP {e.status_code}: {e.message}"
        elif anthropic is not None and isinstance(e, anthropic.APIConnectionError):
            why = "network error"
        else:
            why = f"{type(e).__name__}: {e}"
        print(f"claude ({task}): no answer, {why}", file=sys.stderr)
        return None
    if on_cost:
        on_cost(cost_usd(r.model, r.usage))
    if r.stop_reason != "end_turn":   # refusal (even after the fallback), max_tokens, ...
        print(f"claude ({task}): no answer, stop_reason={r.stop_reason}", file=sys.stderr)
        return None
    text = next((b.text for b in r.content if getattr(b, "type", "") == "text"), "")
    try:
        out = json.loads(text)
    except ValueError:
        print(f"claude ({task}): answer was not JSON", file=sys.stderr)
        return None
    return out if isinstance(out, dict) else None
