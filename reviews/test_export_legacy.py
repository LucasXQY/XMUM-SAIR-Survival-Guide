"""Checks for reviews/export_legacy.py. Run from the repo root: python reviews/test_export_legacy.py (no network)."""
import json, pathlib, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import export_legacy as ex


def test_votes_from_the_private_repo_layout():
    root = pathlib.Path(tempfile.mkdtemp())
    (root / "votes/COM107").mkdir(parents=True)
    (root / "votes/COM107/chua-ming-yam.json").write_text(json.dumps({
        "code": "COM107", "name": "Chua Ming Yam",
        "votes": {"abc123": {"scores": {"course": 4, "instructor": 5, "difficulty": 3, "work": 2}, "session": "2022-04", "at": "2026-11-05T10:00:00Z"},
                  "def456": {"scores": {"course": 2, "instructor": 3, "difficulty": 4, "work": 5, "learned": 3}, "session": "", "at": "2026-11-05T11:00:00Z"}}}),
        encoding="utf-8")
    votes = ex.legacy_votes(root)
    assert len(votes) == 2 and {v["voter"] for v in votes} == {"abc123", "def456"}
    v = next(v for v in votes if v["voter"] == "abc123")
    assert v == {"code": "COM107", "name": "Chua Ming Yam", "session": "2022-04", "at": "2026-11-05T10:00:00Z",
                 "scores": {"course": 4, "instructor": 5, "difficulty": 3, "work": 2}, "voter": "abc123"}
    assert ex.legacy_votes(pathlib.Path(tempfile.mkdtemp())) == []
    assert [len(c) for c in ex.chunks(list(range(450)), 200)] == [200, 200, 50]


def test_post_names_the_client():
    """Cloudflare answers Python's default client name (Python-urllib) with 403, error 1010, so every call names itself."""
    sent = {}

    class Reply:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"imported": 2}'

    def fake_urlopen(req, timeout=None):
        sent["ua"], sent["body"] = req.get_header("User-agent"), json.loads(req.data)
        return Reply()
    real, ex.urllib.request.urlopen = ex.urllib.request.urlopen, fake_urlopen
    try:
        assert ex.post("https://w.example/admin/api", {"op": "import"}) == {"imported": 2}
    finally:
        ex.urllib.request.urlopen = real
    assert sent["body"] == {"op": "import"} and sent["ua"] and not sent["ua"].startswith("Python-urllib")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
