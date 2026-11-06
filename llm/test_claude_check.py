"""Checks for llm/claude_check.py. Run from the repo root: python llm/test_claude_check.py (no network, no SDK needed)."""
import base64, json, pathlib, sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import claude_check as cc

SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["ok", "hide"]}},
          "required": ["verdict"], "additionalProperties": False}


class FakeStore:
    """Stands in for the GitHub contents API on the bot-state branch."""

    def __init__(self, branch=False, conflicts=0):
        self.branch, self.file, self.sha, self.conflicts, self.calls = branch, None, None, conflicts, []

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
            raise RuntimeError("gh: is at x but expected y (HTTP 409)")
        if body.get("sha") != self.sha:
            raise RuntimeError("gh: sha mismatch (HTTP 409)")
        self.file, self.sha = base64.b64decode(body["content"]).decode(), (self.sha or "") + "1"
        return "{}"


def test_budget_counts_per_task_per_day_and_stops_at_the_limit():
    store = FakeStore()
    b = cc.Budget("o/r", gh=store.gh, today="2026-11-06")
    assert b.take("moderation", 1, limit=2) and b.take("moderation", 1, limit=2)
    assert not b.take("moderation", 1, limit=2)                      # third call of the day is refused
    assert b.take("upload", 3, limit=5) and not b.take("upload", 3, limit=5)
    assert json.loads(store.file) == {"2026-11-06": {"moderation": 2, "upload": 3}} and store.branch   # branch created on first use
    tomorrow = cc.Budget("o/r", gh=store.gh, today="2026-11-07")
    assert tomorrow.take("moderation", 1, limit=2) and json.loads(store.file) == {"2026-11-07": {"moderation": 1}}


def test_budget_retries_a_conflicting_write_and_fails_closed():
    store = FakeStore(branch=True, conflicts=1)
    store.file, store.sha = json.dumps({"2026-11-06": {"moderation": 1}}), "s"
    assert cc.Budget("o/r", gh=store.gh, today="2026-11-06").take("moderation", 1, limit=5)
    assert json.loads(store.file)["2026-11-06"]["moderation"] == 2
    def broken(*args, input=None):
        raise RuntimeError("gh: Bad credentials (HTTP 401)")
    assert not cc.Budget("o/r", gh=broken, today="2026-11-06").take("moderation", 1, limit=5)   # unsure → no Claude


class FakeClient:
    def __init__(self, text='{"verdict": "hide"}', stop="end_turn", error=None):
        self.kw, self.path = None, None
        def create(path):
            def f(**kw):
                self.kw, self.path = kw, path
                if error:
                    raise error
                return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="thinking", thinking=""),
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


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
