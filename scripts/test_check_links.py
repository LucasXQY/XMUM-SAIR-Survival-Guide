"""Checks for scripts/check_links.py. Run from the repo root: python scripts/test_check_links.py (no network)."""
import pathlib, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import check_links as cl


def _site():
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "a").mkdir()
    (d / "index.html").write_text('<a href="/a/">ok</a> <a href="/gone/#x">dead</a> <a href="/static/s.css">css</a>'
                                  ' <a href="https://example.com/x">ext</a> <a href="mailto:x@y">mail</a>', encoding="utf-8")
    (d / "a/index.html").write_text('<a href="/">home</a> <a href="https://example.com/x">ext</a> <a href="https://bad.example/">bad</a>', encoding="utf-8")
    (d / "static").mkdir(); (d / "static/s.css").write_text("", encoding="utf-8")
    return d


def test_internal_links_find_missing_pages():
    assert cl.internal(_site(), "/") == [("index.html", "/gone/#x")]


def test_external_links_are_checked_once_each_and_known_refusals_pass():
    seen = []

    def fetch(url):
        seen.append(url)
        return {"https://example.com/x": 200, "https://bad.example/": 404, "https://github.com/signup": 403}[url]
    hrefs = cl.external_hrefs(_site()) | {"https://github.com/signup"}
    bad = cl.external(hrefs, fetch)
    assert bad == [("https://bad.example/", 404)] and sorted(seen) == sorted(set(seen))   # one request per distinct URL


def test_missing_zips_and_report():
    assert cl.missing_zips({"A_2021-09.zip", "B_2022-04.zip"}, ["A_2021-09.zip"]) == ["B_2022-04.zip"]
    text = cl.report([("index.html", "/gone/")], [("https://bad.example/", 404)], ["B_2022-04.zip"])
    assert "/gone/" in text and "bad.example" in text and "B_2022-04.zip" in text and "|" in text
    assert cl.report([], [], []) == ""


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
