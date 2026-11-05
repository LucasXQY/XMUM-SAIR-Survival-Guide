"""Checks for site/build.py. Run from the repo root: python site/test_build.py"""
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
ROOT = pathlib.Path(__file__).resolve().parents[1]
import build


def test_parse_taken():
    t = build.parse_taken("| 2022-04 | [COM107](COM107_Circuits_and_Devices/) | x |\n"
                          "| 2022-02 | [COM107](COM107_Circuits_and_Devices/) | x |\n"
                          "| 2022-04 | COM999 | x |\n")
    assert t["COM107"] == ["2022-02", "2022-04"] and t["COM999"] == ["2022-04"]


def test_parse_lecturers_link_and_plain():
    md = ("# X\n\n| 学期 / Session | 老师 / Lecturer | 考核 | 来自 | 备注 |\n|---|---|---|---|---|\n"
          "| [2022-04](2022-04/) | Chua Ming Yam |  | L | n |\n"
          "| 2025-04 | Dr. A |  | J | n |\n"
          "| 2026-09 |  |  | J | n |\n")
    assert build.parse_lecturers(md) == {"2022-04": "Chua Ming Yam", "2025-04": "Dr. A"}


def test_scan_real_repo():
    courses = build.scan(ROOT)
    assert len(courses) == 58 and {c.prog for c in courses} == {"EEE"}
    c = next(c for c in courses if c.code == "COM107")
    assert c.name == "Circuits and Devices" and c.path == "EEE/COM107_Circuits_and_Devices"
    assert list(c.sessions) == ["2022-04"]
    assert list(c.sessions["2022-04"]) == ["Past-Papers", "Tutorials", "Handbooks"]
    assert len(c.sessions["2022-04"]["Tutorials"]) == 5
    assert c.taken_in == ["2022-04"] and c.lecturers["2022-04"] == "Chua Ming Yam"
    files = build.all_files(courses)
    assert len(files) == 482 and all((ROOT / f.path).is_file() for f in files)
    com110 = next(c for c in courses if c.code == "COM110")
    assert list(com110.sessions) == ["2026-09", "2025-04"]


P = "/XMUM-SAIR-Survival-Guide/"


def _site():
    return build.Site(ROOT, P)


def test_slugify_github_style():
    assert build.slugify("欢迎上传 | What to upload", "-") == "欢迎上传--what-to-upload"
    assert build.slugify("修课时间表 | Course timeline", "-") == "修课时间表--course-timeline"


def test_rewrite_link_rules():
    s = _site()
    assert build.rewrite_link(s, "CONTRIBUTING.md", "README.md") == P + "contributing/"
    assert build.rewrite_link(s, "../CONTRIBUTING.md#署名--credit", "EEE/README.md") == P + "contributing/#署名--credit"
    assert build.rewrite_link(s, "COM107_Circuits_and_Devices/", "EEE/README.md") == P + "EEE/COM107_Circuits_and_Devices/"
    assert build.rewrite_link(s, "../EEE/README.md", "AIT/README.md") == P + "EEE/"
    assert build.rewrite_link(s, "2022-04/Tutorials/", "EEE/COM107_Circuits_and_Devices/README.md") == P + "EEE/COM107_Circuits_and_Devices/#2022-04"
    assert build.rewrite_link(s, "../COM108_Engineering_Mathematics_I/", "EEE/COM110_Engineering_Mathematics_I/README.md") == P + "EEE/COM108_Engineering_Mathematics_I/"
    assert build.rewrite_link(s, "scripts/update_index.py", "README.md") == build.GH + "/blob/main/scripts/update_index.py"
    assert build.rewrite_link(s, "https://github.com/nsd-chen", "EEE/README.md") == "https://github.com/nsd-chen"
    assert build.rewrite_link(s, "#top", "README.md") == "#top"
    assert build.rewrite_link(s, "../EEE999_X/", "EEE/COM107_Circuits_and_Devices/README.md") == build.GH + "/blob/main/EEE/EEE999_X"


def test_render_md_rewrites_hrefs_and_ids():
    s = _site()
    html = build.render_md(s, "## 欢迎上传 | What to upload\n\nSee [rules](../CONTRIBUTING.md) and [x](../EEE/README.md).\n", "AIT/README.md")
    assert 'id="欢迎上传--what-to-upload"' in html
    assert 'href="/XMUM-SAIR-Survival-Guide/contributing/"' in html and 'href="/XMUM-SAIR-Survival-Guide/EEE/"' in html
    table = build.render_md(s, "| a | b |\n|---|---|\n| 1 | 2 |\n", "README.md")
    assert '<div class="table-wrap"><table>' in table and "</table></div>" in table


def test_contributing_toc_anchors_resolve():
    import re
    s = _site()
    html = build.render_md(s, (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8"), "CONTRIBUTING.md")
    ids = set(re.findall(r'id="([^"]+)"', html))
    for frag in re.findall(r'href="#([^"]+)"', html):
        assert frag in ids, frag


import json
import re
import tempfile


def _build(prefix=P):
    out = pathlib.Path(tempfile.mkdtemp()) / "_site"
    return build.build(ROOT, out, prefix), out


def test_build_writes_every_page():
    site, out = _build()
    for p in ["index.html", "404.html", "about/index.html", "disclaimer/index.html", "qa/index.html",
              "contributing/index.html", "contributors/index.html", "lecturers/index.html", "research/index.html",
              "EEE/index.html", "AIT/index.html", "ROBO/index.html", "EEE/COM107_Circuits_and_Devices/index.html",
              "search.json", "static/style.css", "static/search.js"]:
        assert (out / p).is_file(), p
    assert len(site.courses) == len(list(out.glob("*/*_*/index.html"))) == 58


def test_course_page_contents():
    _, out = _build()
    html = (out / "EEE/COM107_Circuits_and_Devices/index.html").read_text(encoding="utf-8")
    assert 'data-strict="1"' in html and 'data-term="COM107 Circuits and Devices"' in html
    assert 'data-category-id="DIC_kwDOQ_iF5s4DKajf"' in html and 'data-repo-id="R_kgDOQ_iF5g"' in html
    assert 'id="2022-04"' in html and "Chua Ming Yam" in html
    assert build.GH + "/blob/main/EEE/COM107_Circuits_and_Devices/2022-04/Tutorials/" in html
    assert build.RAW + "/EEE/COM107_Circuits_and_Devices/2022-04/Tutorials/" in html
    assert "请勿张贴答案" in html and "Student-run, not affiliated with XMUM" in html and "Ciallo～ (∠・ < )⌒☆" in html


def test_prog_and_qa_pages():
    _, out = _build()
    eee = (out / "EEE/index.html").read_text(encoding="utf-8")
    assert "<!-- COURSE-INDEX -->" not in eee
    assert len(set(re.findall(r'href="/XMUM-SAIR-Survival-Guide/EEE/[^"/]+_[^"/]+/"', eee))) == 58
    assert "暂无课程" in (out / "AIT/index.html").read_text(encoding="utf-8")
    qa = (out / "qa/index.html").read_text(encoding="utf-8")
    assert 'data-category-id="DIC_kwDOQ_iF5s4DKaje"' in qa and 'data-term="综合问答 | General Q&amp;A"' in qa


def test_search_index():
    _, out = _build()
    idx = json.loads((out / "search.json").read_text(encoding="utf-8"))
    assert len(idx["courses"]) == 58 and len(idx["files"]) == 482
    f = next(f for f in idx["files"] if f["code"] == "COM107" and f["type"] == "Tutorials")
    assert f["preview"].startswith(build.GH + "/blob/main/") and f["download"].startswith(build.RAW + "/")
    assert (ROOT / f["path"]).is_file()
    assert any(f["preview"] is None for f in idx["files"] if f["name"].endswith(".docx"))
    c = next(c for c in idx["courses"] if c["code"] == "COM107")
    assert c["lecturers"] == ["Chua Ming Yam"] and c["url"] == P + "EEE/COM107_Circuits_and_Devices/"


def test_root_prefix_preview():
    _, out = _build("/")
    html = (out / "EEE/index.html").read_text(encoding="utf-8")
    assert 'href="/EEE/COM107_Circuits_and_Devices/"' in html and 'data-base="/"' in html
    assert "/XMUM-SAIR-Survival-Guide/" not in html


def test_check_passes_on_real_repo():
    site, out = _build()
    build.check(site, out)          # must not raise
    assert build.stragglers(site) == []


def test_stragglers_reports_misplaced_file():
    import shutil, subprocess
    tmp = pathlib.Path(tempfile.mkdtemp()) / "repo"
    for p in ["README.md", "DISCLAIMER.md", "CONTRIBUTING.md", "CONTRIBUTORS.md", "Lecturers.md",
              "Research-Opportunities.md", "EEE/README.md", "AIT/README.md", "ROBO/README.md",
              "EEE/COM107_Circuits_and_Devices/README.md"]:
        (tmp / p).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / p, tmp / p)
    (tmp / "EEE/COM107_Circuits_and_Devices/2024-9/Notes").mkdir(parents=True)
    (tmp / "EEE/COM107_Circuits_and_Devices/2024-9/Notes/x.pdf").write_bytes(b"%PDF")
    (tmp / "EEE/COM107_Circuits_and_Devices/stray.pdf").write_bytes(b"%PDF")
    subprocess.run(["git", "init", "-q"], cwd=tmp, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp, check=True, capture_output=True)
    site = build.Site(tmp, "/")
    assert build.all_files(site.courses) == []
    assert sorted(build.stragglers(site)) == ["EEE/COM107_Circuits_and_Devices/2024-9/Notes/x.pdf",
                                             "EEE/COM107_Circuits_and_Devices/stray.pdf"]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
