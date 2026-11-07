"""Claude 的第二意见：给审核机器人和上传机器人用。拿不到可信的答案就返回 None，调用方退回原来的规则。
A second opinion from Claude for the moderation and upload bots. Whenever there is no answer to trust, it returns None
and the caller falls back to its own rules.

- 每类任务每天有调用上限，计数放在 bot-state 分支的 claude-usage.json（用文件的 sha 做乐观写入，并发也不会多算）。
  Each task has a daily call limit; the count lives in claude-usage.json on the bot-state branch (optimistic writes keyed
  on the file's sha, so concurrent runs cannot overspend).
- 模型和上限都可以用仓库变量改：CLAUDE_MODEL_<TASK>、CLAUDE_DAILY_<TASK>（TASK = MODERATION / UPLOAD）。
  Model and limit per task come from repository variables CLAUDE_MODEL_<TASK> and CLAUDE_DAILY_<TASK>.
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


class Budget:
    """Today's call count per task. take() says whether n more calls fit under the limit and records them if so;
    anything unexpected counts as no (a broken counter must not mean unlimited calls)."""

    def __init__(self, repo: str, gh=_gh, today: str | None = None):
        self.file = StateFile(repo, STATE_FILE, gh)
        self.today = today or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    def take(self, task: str, n: int, limit: int) -> bool:
        if n <= 0:
            return True
        try:
            for _ in range(5):
                data, sha = self.file.read()
                day = dict(data.get(self.today, {}))
                if day.get(task, 0) + n > limit:
                    print(f"claude ({task}): daily limit {limit} reached", file=sys.stderr)
                    return False
                day[task] = day.get(task, 0) + n
                try:
                    self.file.write({self.today: day}, sha, f"claude usage {self.today}")   # only today is kept: tiny file
                    return True
                except Conflict:
                    continue                                  # someone else wrote first: read again
        except Exception as e:
            print(f"claude ({task}): usage counter unavailable, not calling Claude: {e}", file=sys.stderr)
        return False


def ask(task: str, system: str, content, schema: dict, max_tokens: int = 4000, client=None, model: str | None = None) -> dict | None:
    """Claude's answer as a dict matching `schema`, or None. `content` is the user turn: a string or content blocks."""
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
