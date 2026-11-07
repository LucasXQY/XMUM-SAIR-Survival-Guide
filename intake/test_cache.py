"""Checks for intake/cache.py. Run from the repo root: python intake/test_cache.py (no network, no SDK needed)."""
import base64, copy, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import cache
import claude_check as cc


class FakeStore:
    """Stands in for the GitHub contents API on the bot-state branch: many paths, with PUT and DELETE."""

    def __init__(self, branch=False, conflicts=0):
        self.branch, self.conflicts, self.files, self.calls = branch, conflicts, {}, []   # path -> (data, sha)
        self.on_conflict = None

    @property
    def paths(self):
        return sorted(self.files)

    def gh(self, *args, input=None):
        self.calls.append(args)
        url = next(a for a in args if a.startswith("repos/"))
        if "/git/" in url:
            if url.endswith("/git/refs"):
                self.branch = True
            return json.dumps({"sha": "abc"})
        path = url.split("/contents/", 1)[1].split("?")[0]
        method = args[args.index("-X") + 1] if "-X" in args else "GET"
        if method == "GET":
            if not self.branch or path not in self.files:
                raise RuntimeError("gh: Not Found (HTTP 404)")
            data, sha = self.files[path]
            return json.dumps({"content": base64.b64encode(json.dumps(data).encode()).decode(), "sha": sha})
        if not self.branch:
            raise RuntimeError("gh: Branch bot-state not found (HTTP 404)")
        body = json.loads(input)
        if method == "DELETE":
            if path not in self.files:
                raise RuntimeError("gh: Not Found (HTTP 404)")
            if body.get("sha") != self.files[path][1]:
                raise RuntimeError("gh: sha mismatch (HTTP 409)")
            del self.files[path]
            return "{}"
        if self.conflicts:
            self.conflicts -= 1
            if self.on_conflict:
                self.on_conflict(self)
            raise RuntimeError("gh: is at x but expected y (HTTP 409)")
        cur = self.files.get(path)
        if body.get("sha") != (cur[1] if cur else None):
            raise RuntimeError("gh: sha mismatch (HTTP 409)")
        self.files[path] = (json.loads(base64.b64decode(body["content"])), (cur[1] if cur else "") + "1")
        return "{}"


def other_writer(store):
    path = "intake-cache/issue-7.json"
    data, sha = store.files[path]
    data = dict(data, overrides=dict(data.get("overrides", {}), theirs={"keep": True}))
    store.files[path] = (data, sha + "x")


def test_scrub_keeps_positions_and_drops_personal_text():
    data = {"check": {"abc": {"summary": "Cover shows EEE2109300", "notes": "", "redactions": [{"page": 1, "kind": "text", "text": "EEE2109300", "rects": [[1, 2, 3, 4]]}]}}}
    clean = cache.scrub(data)
    assert "EEE2109300" not in json.dumps(clean) and clean["check"]["abc"]["redactions"] == [{"page": 1, "kind": "text", "rects": [[1, 2, 3, 4]]}]


def test_scrub_blanks_pii_notes_everywhere_and_does_not_mutate():
    data = {"sort": {"s1": {"note": "mail me at a.b@gmail.com", "label": "Final"}},
            "check": {"s1": {"summary": "fine exam", "notes": "student id on page 2",
                             "redactions": [{"page": 2, "kind": "box", "box": [1, 2, 3, 4], "what": "id", "text": "ABC1234567"}]}},
            "verify": {"s1": {"notes": ["x"], "summary": "call 13812345678"}}, "spent_usd": 0.5, "extra": {"k": [1]}}
    before = copy.deepcopy(data)
    clean = cache.scrub(data)
    assert data == before
    assert clean["sort"]["s1"] == {"note": "", "label": "Final"}
    assert clean["check"]["s1"]["summary"] == "fine exam" and clean["check"]["s1"]["notes"] == ""
    assert clean["check"]["s1"]["redactions"] == [{"page": 2, "kind": "box", "box": [1, 2, 3, 4], "what": "id"}]
    assert clean["verify"]["s1"]["notes"] == ["x"] and clean["verify"]["s1"]["summary"] == ""
    assert clean["spent_usd"] == 0.5 and clean["extra"] == {"k": [1]}
    clean["extra"]["k"].append(2)
    assert data["extra"]["k"] == [1]


def test_cache_round_trip_on_bot_state():
    store = FakeStore(branch=True); c = cache.IntakeCache("o/r", 7, gh=store.gh)
    c.save({"items": [{"k": 1, "sha": "s", "source": "a.pdf"}], "overrides": {"s": {"kind": "skip"}}})
    assert c.load()["overrides"] == {"s": {"kind": "skip"}} and store.paths == ["intake-cache/issue-7.json"]


def test_load_of_a_missing_cache_is_empty():
    assert cache.IntakeCache("o/r", 7, gh=FakeStore(branch=True).gh).load() == {}


def test_save_scrubs_what_it_writes():
    store = FakeStore(branch=True)
    cache.IntakeCache("o/r", 7, gh=store.gh).save({"check": {"s": {"redactions": [{"page": 1, "kind": "text", "text": "EEE2109300", "rects": []}]}}})
    assert "EEE2109300" not in json.dumps(store.files)


def test_save_retries_once_on_conflict_and_keeps_both_overrides():
    store = FakeStore(branch=True)
    c = cache.IntakeCache("o/r", 7, gh=store.gh)
    c.save({"overrides": {"mine": {"skip": True}}})
    store.conflicts, store.on_conflict = 1, other_writer
    c.save({"overrides": {"mine": {"skip": True, "approved_by": "z"}, "new": {"keep": True}}, "spent_usd": 1})
    data = store.files["intake-cache/issue-7.json"][0]
    assert data["overrides"] == {"mine": {"skip": True, "approved_by": "z"}, "new": {"keep": True}, "theirs": {"keep": True}}
    assert data["spent_usd"] == 1


def test_a_second_conflict_propagates():
    store = FakeStore(branch=True)
    c = cache.IntakeCache("o/r", 7, gh=store.gh)
    c.save({"overrides": {}})
    store.conflicts, store.on_conflict = 2, other_writer
    try:
        c.save({"overrides": {}})
    except cc.Conflict:
        return
    raise AssertionError("expected Conflict")


def test_delete_removes_the_file_and_a_missing_file_is_fine():
    store = FakeStore(branch=True)
    c = cache.IntakeCache("o/r", 7, gh=store.gh)
    c.delete()                                    # nothing there
    c.save({"items": []})
    c.delete()
    assert store.paths == [] and c.load() == {}
    cache.IntakeCache("o/r", 7, gh=FakeStore().gh).delete()    # no bot-state branch at all


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
