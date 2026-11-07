"""Checks for llm/claude_check.py. Run from the repo root: python llm/test_claude_check.py (no network, no SDK needed)."""
import base64, json, os, pathlib, sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import claude_check as cc

SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["ok", "hide"]}},
          "required": ["verdict"], "additionalProperties": False}


class FakeStore:
    """Stands in for the GitHub contents API on the bot-state branch."""

    def __init__(self, branch=False, conflicts=0):
        self.branch, self.data, self.sha, self.conflicts, self.calls, self.writes = branch, None, None, conflicts, [], 0

    @property
    def file(self):                                           # the stored text; `data` is the same file parsed
        return None if self.data is None else json.dumps(self.data)

    @file.setter
    def file(self, text):
        self.data = None if text is None else json.loads(text)

    def gh(self, *args, input=None):
        self.calls.append(args)
        path = next(a for a in args if a.startswith("repos/"))
        if "/git/" in path:                                   # creating the orphan branch: tree, commit, ref
            if path.endswith("/git/refs"):
                self.branch = True
            return json.dumps({"sha": "abc"})
        if "-X" not in args:                                  # read
            if not self.branch or self.file is None:
                raise RuntimeError("gh: Not Found (HTTP 404)")
            return json.dumps({"content": base64.b64encode(self.file.encode()).decode(), "sha": self.sha})
        if not self.branch:                                   # write to a branch that does not exist yet
            raise RuntimeError("gh: Branch bot-state not found (HTTP 404)")
        body = json.loads(input)
        if self.conflicts:
            self.conflicts -= 1
            self.sha = (self.sha or "") + "x"                 # someone else wrote in between
            if self.data is None:
                self.data = {}
            raise RuntimeError("gh: is at x but expected y (HTTP 409)")
        if body.get("sha") != self.sha:
            raise RuntimeError("gh: sha mismatch (HTTP 409)")
        self.file, self.sha = base64.b64decode(body["content"]).decode(), (self.sha or "") + "1"
        self.writes += 1
        return "{}"


def test_budget_counts_per_task_per_day_and_stops_at_the_limit():
    store = FakeStore()
    b = cc.Budget("o/r", gh=store.gh, today="2026-11-06")
    assert b.take("moderation", 1, limit=2) and b.take("moderation", 1, limit=2)
    assert not b.take("moderation", 1, limit=2)                      # third call of the day is refused
    assert b.take("upload", 3, limit=5) and not b.take("upload", 3, limit=5)
    assert store.data["calls"] == {"moderation": 2, "upload": 3} and store.branch   # branch created on first use
    tomorrow = cc.Budget("o/r", gh=store.gh, today="2026-11-07")
    assert tomorrow.take("moderation", 1, limit=2) and store.data["calls"] == {"moderation": 1}   # a new day clears the counts


def test_budget_retries_a_conflicting_write_and_fails_closed():
    store = FakeStore(branch=True, conflicts=1)
    store.file, store.sha = json.dumps({"day": "2026-11-06", "calls": {"moderation": 1}}), "s"
    assert cc.Budget("o/r", gh=store.gh, today="2026-11-06").take("moderation", 1, limit=5)
    assert store.data["calls"]["moderation"] == 2
    def broken(*args, input=None):
        raise RuntimeError("gh: Bad credentials (HTTP 401)")
    assert not cc.Budget("o/r", gh=broken, today="2026-11-06").take("moderation", 1, limit=5)   # unsure → no Claude


def test_budget_reserves_dollars_per_pool_for_the_day_and_month():
    store = FakeStore(branch=True)
    b = cc.Budget("o/r", gh=store.gh, today="2026-11-06")
    assert b.reserve("upload", 10) and not b.reserve("upload", 6)          # day cap 15
    b.settle("upload", -4)
    assert b.reserve("upload", 6) and b.spent("upload") == (12, 12)
    b2 = cc.Budget("o/r", gh=store.gh, today="2026-11-07")
    assert b2.spent("upload") == (0, 12) and b2.reserve("upload", 15)
    store.data["usd_month"]["upload"] = 59
    assert not cc.Budget("o/r", gh=store.gh, today="2026-11-08").reserve("upload", 2)
    assert cc.Budget("o/r", gh=store.gh, today="2026-12-01").reserve("upload", 2)


def test_take_counts_calls_and_reserves_dollars_in_one_write():
    store = FakeStore(branch=True)
    b = cc.Budget("o/r", gh=store.gh, today="2026-11-06")
    assert b.take("moderation", 1, 100, usd=0.002) and store.writes == 1
    assert store.data["calls"]["moderation"] == 1 and store.data["usd_day"]["haiku"] == 0.002
    assert not b.take("moderation", 1, 1, usd=0.002)                       # count cap still applies


def test_settle_retries_conflicts_and_never_raises():
    store = FakeStore(branch=True, conflicts=2)
    b = cc.Budget("o/r", gh=store.gh, today="2026-11-06")
    b.settle("upload", 1.5)
    assert store.data["usd_day"]["upload"] == 1.5
    broken = cc.Budget("o/r", gh=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")), today="2026-11-06")
    broken.settle("upload", 1.0)                                            # logs, no exception
    assert not broken.reserve("upload", 0.01)                               # fails closed


def test_failed_settle_blocks_later_reserves_even_if_the_ledger_reads_again():
    store = FakeStore(branch=True, conflicts=99)                            # every write conflicts: settle gives up
    b = cc.Budget("o/r", gh=store.gh, today="2026-11-06")
    b.settle("upload", 5)
    store.conflicts = 0
    assert not b.reserve("upload", 1) and not b.take("upload", 1, 10, usd=1)


def test_old_usage_file_reads_as_empty_and_caps_come_from_variables():
    store = FakeStore(branch=True); store.data = {"2026-11-06": {"topics": 551}}
    assert cc.Budget("o/r", gh=store.gh, today="2026-11-06").spent("haiku") == (0, 0)
    os.environ["CLAUDE_USD_DAY_UPLOAD"] = "20"
    try:
        assert cc.usd_cap("upload", "day") == 20 and cc.usd_cap("upload", "run") == 8 and cc.usd_cap("helper", "day") == float("inf")
    finally:
        del os.environ["CLAUDE_USD_DAY_UPLOAD"]
    assert cc.pool_of("topics") == "haiku" and cc.pool_of("sort") == "upload"


def test_ledger_totals_stay_exact_and_never_negative():
    store = FakeStore(branch=True)
    b = cc.Budget("o/r", gh=store.gh, today="2026-11-06")
    for _ in range(10):
        assert b.reserve("haiku", 0.1)
    assert b.reserve("haiku", 1.0) and b.spent("haiku")[0] == 2.0 and not b.reserve("haiku", 0.000001)   # exactly the cap fits
    b.settle("haiku", -50)
    assert b.spent("haiku") == (0, 0)                                      # never below 0


def test_a_run_that_started_before_midnight_never_rolls_the_ledger_back():
    store = FakeStore(branch=True)
    late = cc.Budget("o/r", gh=store.gh, today="2026-11-30")
    assert late.reserve("upload", 5)
    assert cc.Budget("o/r", gh=store.gh, today="2026-12-01").reserve("upload", 7)
    late.settle("upload", 1)                                               # the old run settles after the new month began
    assert cc.Budget("o/r", gh=store.gh, today="2026-12-01").spent("upload") == (8, 8)
    assert late.reserve("upload", 6) and cc.Budget("o/r", gh=store.gh, today="2026-12-01").spent("upload") == (14, 14)
    assert not late.reserve("upload", 2)                                   # caps are checked against the newer day's totals


class FakeClient:
    def __init__(self, text='{"verdict": "hide"}', stop="end_turn", error=None, usage=None):
        self.kw, self.path = None, None
        def create(path):
            def f(**kw):
                self.kw, self.path = kw, path
                if error:
                    raise error
                return SimpleNamespace(stop_reason=stop, model=kw["model"], usage=usage or {"input_tokens": 10, "output_tokens": 5}, content=[SimpleNamespace(type="thinking", thinking=""),
                                                                  SimpleNamespace(type="text", text=text)])
            return f
        self.messages = SimpleNamespace(create=create("messages"))
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=create("beta")))


def test_ask_returns_json_with_schema_low_effort_and_refusal_fallback():
    c = FakeClient()
    assert cc.ask("moderation", "sys", [{"type": "text", "text": "hi"}], SCHEMA, client=c, model="claude-opus-5-5") == {"verdict": "hide"}
    assert c.path == "beta" and c.kw["betas"] == ["server-side-fallback-2026-07-01"] and c.kw["fallbacks"] == "default"
    assert c.kw["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}}
    assert c.kw["model"] == "claude-opus-5-5" and c.kw["system"] == "sys" and c.kw["messages"][0]["role"] == "user"
    h = FakeClient()
    assert cc.ask("moderation", "sys", "hi", SCHEMA, client=h, model="claude-haiku-5-5") == {"verdict": "hide"}
    assert h.path == "messages" and "fallbacks" not in h.kw                   # Haiku has no server-side fallback


def test_the_upload_check_runs_at_medium_effort_with_a_long_timeout():         # final review, fold-in 12
    for task, model, effort, timeout in (("upload", "claude-opus-5-5", "medium", 600), ("sort", "claude-haiku-5-5", "low", None),
                                         ("moderation", "claude-haiku-5-5", "low", None), ("topics", "claude-opus-5-5", "low", None)):
        c = FakeClient()
        assert cc.ask(task, "sys", "hi", SCHEMA, client=c, model=model) == {"verdict": "hide"}
        assert c.kw["output_config"] == {"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}}, task
        assert c.kw.get("timeout") == timeout and ("timeout" in c.kw) == (timeout is not None), task


def test_ask_reports_the_cost_even_when_there_is_no_answer():
    seen = []
    cc.ask("moderation", "sys", "hi", SCHEMA, client=FakeClient(usage={"input_tokens": 1000, "output_tokens": 100}), on_cost=seen.append)
    cc.ask("moderation", "sys", "hi", SCHEMA, client=FakeClient(stop="refusal", usage={"input_tokens": 1000}), on_cost=seen.append)
    assert len(seen) == 2 and round(seen[0], 6) == round(cc.cost_usd("claude-haiku-5-5", {"input_tokens": 1000, "output_tokens": 100}), 6)
    cc.ask("moderation", "sys", "hi", SCHEMA, client=FakeClient(error=RuntimeError("down")), on_cost=seen.append)
    assert len(seen) == 2                                                   # no response, no cost


def test_ask_gives_none_whenever_the_answer_cannot_be_trusted():
    assert cc.ask("moderation", "sys", "hi", SCHEMA, client=FakeClient(stop="refusal")) is None
    assert cc.ask("moderation", "sys", "hi", SCHEMA, client=FakeClient(stop="max_tokens")) is None
    assert cc.ask("moderation", "sys", "hi", SCHEMA, client=FakeClient(text="not json")) is None
    assert cc.ask("moderation", "sys", "hi", SCHEMA, client=FakeClient(error=RuntimeError("credit balance too low"))) is None
    import os
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        assert cc.ask("moderation", "sys", "hi", SCHEMA) is None             # no key: callers fall back to their rules
    finally:
        if saved is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved


def test_model_and_limit_come_from_repository_variables():
    import os
    os.environ["CLAUDE_MODEL_UPLOAD"] = "claude-haiku-5-5"
    os.environ["CLAUDE_DAILY_UPLOAD"] = "7"
    try:
        assert cc.model_for("upload") == "claude-haiku-5-5" and cc.model_for("moderation") == "claude-haiku-5-5"   # maintainer: Haiku for moderation
        os.environ.pop("CLAUDE_MODEL_UPLOAD"); assert cc.model_for("upload") == "claude-opus-5-5"; os.environ["CLAUDE_MODEL_UPLOAD"] = "x"
        assert cc.daily_limit("upload", 30) == 7 and cc.daily_limit("moderation", 100) == 100
        os.environ["CLAUDE_DAILY_UPLOAD"] = "lots"
        assert cc.daily_limit("upload", 30) == 30
    finally:
        os.environ.pop("CLAUDE_MODEL_UPLOAD"); os.environ.pop("CLAUDE_DAILY_UPLOAD")


def test_cost_usd_uses_the_price_table():
    u = {"input_tokens": 1_000_000, "output_tokens": 100_000}
    assert round(cc.cost_usd("claude-opus-5-5", u), 4) == 6.0
    assert round(cc.cost_usd("claude-haiku-5-5", {"input_tokens": 50_000, "output_tokens": 1000}), 6) == 0.0055
    assert round(cc.cost_usd("claude-haiku-5-5", {"input_tokens": 200_000, "output_tokens": 1000}), 6) == 0.1025
    assert round(cc.cost_usd("claude-opus-5-5", {"cache_read_input_tokens": 1_000_000}), 4) == 0.2
    assert cc.cost_usd("claude-new-thing", u) == cc.cost_usd("claude-fable-5-1", u)


def test_the_worker_reads_the_same_price_table():
    js = (pathlib.Path(__file__).parent.parent / "assistant/src/core.js").read_text(encoding="utf-8")
    assert '"../../llm/prices.json"' in js


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
