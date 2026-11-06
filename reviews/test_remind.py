"""Checks for reviews/remind.py. Run from the repo root: python reviews/test_remind.py (no network)."""
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import remind


def test_issue_text_lists_what_waits_and_links_the_admin_page():
    text = remind.issue_text({"total": 40, "unreviewed": 3, "dropped": 1, "by_flag": {"burst": 2, "new_name": 1}}, "https://w.example/admin")
    assert "3" in text and "https://w.example/admin" in text and "一小时内突增" in text and "名单外" in text
    assert "照常计入" in text                                                   # the maintainer knows nothing is on hold
    assert remind.issue_text({"total": 40, "unreviewed": 0, "dropped": 0, "by_flag": {}}, "https://w.example/admin") is None


def test_worker_calls_go_through_the_shared_post():
    """The Worker sits behind Cloudflare, which blocks Python's default client name; export_legacy.post names the client."""
    import export_legacy
    assert remind.post is export_legacy.post


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
