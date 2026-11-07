"""Checks for intake/intake.py. Run from the repo root: python intake/test_intake.py (no network needed)."""
import re, sys, pathlib, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
ROOT = pathlib.Path(__file__).resolve().parents[1]
import intake

# the body GitHub renders from the issue form: "### <title>", blank line, value, blank line
SAMPLE_BODY = """### 专业 | Programme

EEE

### 课程代码 | Course code

com107

### 课程名称 | Course name

Circuits and Devices

### 学期 | Session

2022-04

### 资料类型 | Type

Past-Papers

### 文件 | Files

[final.pdf](https://github.com/user-attachments/files/111/final.pdf)
[bundle.zip](https://github.com/user-attachments/files/112/bundle.zip)
![shot](https://github.com/user-attachments/assets/0f0f0f0f-aaaa-bbbb-cccc-0123456789ab)

### 考核名称 | Assessment（试卷用）

Final

### 老师 | Lecturer

_No response_

### 考核比例 | Assessment weighting

_No response_

### 你修这门课的学期 | Session you took it

_No response_

### 署名方式 | Credit

用下面填的昵称 | The nickname below

### 昵称 | Nickname

Joyce

### 入学年份 | Intake year

2021

### 备注 / 小贴士 | Notes

_No response_

### 确认 | Checklist

- [x] {c0}
- [x] {c1}
- [x] {c2}
- [x] {c3}
"""


def _body(**over):
    b = SAMPLE_BODY.format(c0=intake.CHECKS[0], c1=intake.CHECKS[1], c2=intake.CHECKS[2], c3=intake.CHECKS[3])
    for k, v in over.items():
        b = b.replace(k, v)
    return b


def test_parse_form_fields():
    f = intake.parse_form(_body())
    assert (f.prog, f.code, f.name, f.session, f.type) == ("EEE", "COM107", "Circuits and Devices", "2022-04", "Past-Papers")
    assert f.links == [("final.pdf", "https://github.com/user-attachments/files/111/final.pdf"),
                       ("bundle.zip", "https://github.com/user-attachments/files/112/bundle.zip")]
    assert f.lecturer == "" and f.taken == "2022-04" and f.credit == intake.CREDIT_NICK and f.nickname == "Joyce" and f.intake == "2021"
    assert f.checked == [True, True, True, True]
    assert intake.validate(f) == []


def test_validate_reports_each_problem_bilingually():
    f = intake.parse_form(_body(**{"com107": "TBD_1", "2022-04": "2022-4"}))
    problems = intake.validate(f)
    assert any("Course code" in p and "课程代码" in p for p in problems)
    assert any("Session" in p and "学期" in p for p in problems)
    assert len(problems) == 2, problems


def test_validate_unticked_box_and_missing_nickname():
    body = _body().replace("- [x] " + intake.CHECKS[2], "- [ ] " + intake.CHECKS[2]).replace("Joyce", "_No response_")
    problems = intake.validate(intake.parse_form(body))
    assert any(intake.CHECKS[2] in p and "Unticked" in p for p in problems)
    assert any("Nickname" in p for p in problems)
    assert len(problems) == 2, problems


def test_attachment_links_accepts_only_file_urls():
    links = intake.attachment_links("[a.pdf](https://github.com/user-attachments/files/1/a.pdf) "
                                    "[b.pdf](https://github.com/xmum-sair/xmum-sair.github.io/files/2/b.pdf) "
                                    "[x](https://github.com/user-attachments/assets/abc) "
                                    "[a.pdf](https://github.com/user-attachments/files/1/a.pdf)")
    assert links == [("a.pdf", "https://github.com/user-attachments/files/1/a.pdf"),
                     ("b.pdf", "https://github.com/xmum-sair/xmum-sair.github.io/files/2/b.pdf")]


def test_no_files_message_mentions_images():
    f = intake.parse_form(_body().replace("[final.pdf](https://github.com/user-attachments/files/111/final.pdf)\n"
                                          "[bundle.zip](https://github.com/user-attachments/files/112/bundle.zip)\n", ""))
    assert any("PDF" in p for p in intake.validate(f))


def test_clean_label():
    assert intake.clean_label("COM105 Week 4 Lecture 4 Newton’s Laws of Motion") == "COM105_Week_4_Lecture_4_Newton_s_Laws_of_Motion"
    assert intake.clean_label(" (期末) Final—Set A ") == "Final_Set_A"


def test_target_name_rules():
    f = intake.parse_form(_body()); taken = set()
    assert intake.target_name(f, "final.pdf", 1, taken) == "COM107_202204_Final_Question.pdf"
    f2 = intake.parse_form(_body()); taken = set()
    assert intake.target_name(f2, "set a.PDF", 2, taken) == "COM107_202204_Final_set_a_Question.pdf"
    assert intake.target_name(f2, "set a.pdf", 2, taken) == "COM107_202204_Final_set_a_Question_2.pdf"
    g = intake.parse_form(_body().replace("Past-Papers", "Notes").replace("Final", "_No response_"))
    assert intake.target_name(g, "COM107_202204_Week 1 notes.pdf", 1, set()) == "COM107_202204_Week_1_notes.pdf"


def test_unpack_zip_rules():
    import zipfile
    work = pathlib.Path(tempfile.mkdtemp())
    z = work / "bundle.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a/b.pdf", b"%PDF"); zf.writestr("notes.PDF", b"%PDF"); zf.writestr("../evil.pdf", b"%PDF")
        zf.writestr("__MACOSX/._x.pdf", b"x"); zf.writestr("sub/", b""); zf.writestr("pic.jpg", b"\xff\xd8"); zf.writestr(".hidden.pdf", b"%PDF")
    (work / "final.pdf").write_bytes(b"%PDF")
    ok, bad, origins = intake.unpack([("final.pdf", work / "final.pdf"), ("bundle.zip", z)], work)
    assert [n for n, _ in ok] == ["final.pdf", "b.pdf", "notes.PDF"] and all(p.is_file() for _, p in ok)
    # zip members are named "<zip> › <n>", n counting every non-directory, non-skipped entry (accepted and rejected alike)
    assert {n for n, _ in bad} == {"bundle.zip › 3", "bundle.zip › 4"} and all(" | " in r for _, r in bad)
    assert origins == ["final.pdf", "bundle.zip › 1", "bundle.zip › 2"]
    assert not any("evil" in n or "pic" in n for n, _ in bad)


def test_unpack_limits():
    work = pathlib.Path(tempfile.mkdtemp()); files = []
    for i in range(intake.MAX_FILES + 1):
        p = work / f"f{i}.pdf"; p.write_bytes(b"%PDF"); files.append((p.name, p))
    try:
        intake.unpack(files, work); assert False
    except intake.IntakeLimit as e:
        assert "60" in str(e)


def _pdf(path, text="Question 1: find x.", author="Someone"):
    import fitz
    d = fitz.open(); pg = d.new_page(); pg.insert_text((72, 72), text)
    d.set_metadata({"author": author, "title": "t"}); d.save(path); d.close()


def _docx(path, creator="Someone", body="Student ID: EEE2109300 answer scheme"):
    import zipfile
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("docProps/core.xml", f'<cp:coreProperties xmlns:cp="x" xmlns:dc="y"><dc:creator>{creator}</dc:creator>'
                                        f'<cp:lastModifiedBy>{creator}</cp:lastModifiedBy><dc:title>T</dc:title></cp:coreProperties>')
        z.writestr("docProps/app.xml", "<Properties><Company>ACME</Company></Properties>")
        z.writestr("word/document.xml", f"<w:document><w:p><w:t>{body}</w:t></w:p></w:document>")


def test_clear_metadata_pdf_and_docx():
    import fitz, zipfile
    w = pathlib.Path(tempfile.mkdtemp()); _pdf(w / "a.pdf"); _docx(w / "b.docx")
    assert intake.clear_metadata(w / "a.pdf") == "cleared"
    assert not any(v for k, v in fitz.open(w / "a.pdf").metadata.items() if k not in ("format", "encryption"))
    assert intake.clear_metadata(w / "b.docx") == "cleared"
    core = zipfile.ZipFile(w / "b.docx").read("docProps/core.xml").decode()
    assert "<dc:creator></dc:creator>" in core and "Someone" not in core
    assert "ACME" not in zipfile.ZipFile(w / "b.docx").read("docProps/app.xml").decode()
    (w / "c.doc").write_bytes(b"\xd0\xcf"); assert "manually" in intake.clear_metadata(w / "c.doc")


def test_inspect_file_flags():
    w = pathlib.Path(tempfile.mkdtemp())
    _pdf(w / "clean.pdf", text="Question 1: find x. " * 10, author=""); _docx(w / "bad.docx")
    c = intake.inspect_file(w / "clean.pdf"); b = intake.inspect_file(w / "bad.docx")
    assert c["pages"] == 1 and c["pii"] == [] and c["answers"] == [] and c["low_text"] is False
    assert any("EEE2109300" in m for m in b["pii"]) and any("answer scheme" in m.lower() for m in b["answers"]) and b["meta_empty"] is False
    _pdf(w / "scan.pdf", text="x", author=""); assert intake.inspect_file(w / "scan.pdf")["low_text"] is True


def test_thumbnails_sheet():
    import fitz
    w = pathlib.Path(tempfile.mkdtemp()); _pdf(w / "a.pdf")
    d = fitz.open(); [d.new_page() for _ in range(3)]; d.save(w / "b.pdf"); d.close()     # only its first two pages are shown
    assert intake.thumbnails([w / "a.pdf", w / "b.pdf"], w / "sheet.png") == 3 and (w / "sheet.png").stat().st_size > 1000
    assert intake.thumbnails([], w / "none.png") == 0 and not (w / "none.png").exists()


def _repo_copy():
    import shutil
    tmp = pathlib.Path(tempfile.mkdtemp()) / "repo"
    for rel in ["README.md", "CONTRIBUTORS.md", "CONTRIBUTING.md", "DISCLAIMER.md", "Lecturers.md", "Research-Opportunities.md",
                "EEE/README.md", "AIT/README.md", "ROBO/README.md", "scripts/update_index.py", "EEE/COM107_Circuits_and_Devices/README.md",
                "GE/README.md", "GE/MPU3.1_Introduction_to_the_Constitution_of_Malaysia/README.md"]:
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copy(ROOT / rel, tmp / rel)
    src = ROOT / "EEE/COM107_Circuits_and_Devices/2022-04/Tutorials"
    (tmp / "EEE/COM107_Circuits_and_Devices/2022-04/Tutorials").mkdir(parents=True)
    shutil.copy(next(src.glob("*.pdf")), tmp / "EEE/COM107_Circuits_and_Devices/2022-04/Tutorials/t1.pdf")
    return tmp


def test_credit_name():
    f = intake.parse_form(_body()); assert intake.credit_name(f, "someone") == "Joyce"
    assert intake.credit_name(intake.parse_form(_body().replace(intake.CREDIT_NICK, intake.CREDIT_LOGIN)), "someone") == "[someone](https://github.com/someone)"
    assert intake.credit_name(intake.parse_form(_body().replace(intake.CREDIT_NICK, intake.CREDIT_ANON)), "someone") == "匿名 / anonymous"
    assert intake.credit_name(intake.parse_form(_body().replace("Joyce", "a|b")), "x") == "a\\|b"


def test_update_course_readme_existing_and_new_row():
    text = (ROOT / "EEE/COM107_Circuits_and_Devices/README.md").read_text(encoding="utf-8")
    f = intake.parse_form(_body()); out = intake.update_course_readme(text, f, "Joyce")
    row = next(l for l in out.splitlines() if l.startswith("| [2022-04]"))
    assert "LucasXQY · [nsd-chen](https://github.com/nsd-chen) · Joyce" in row and "[Past-Papers](2022-04/Past-Papers/)" in row and row.count("[Past-Papers](") == 1
    assert intake.update_course_readme(out, f, "Joyce") == out          # idempotent
    g = intake.parse_form(_body().replace("2022-04", "2025-09").replace("_No response_\n\n### 考核比例", "Dr. New\n\n### 考核比例"))
    out2 = intake.update_course_readme(text, g, "Joyce").splitlines()
    i = next(k for k, l in enumerate(out2) if l.startswith("| [2025-09]"))
    assert out2[i - 1].startswith("| [2022-04]") and "| Dr. New |" in out2[i] and "[Past-Papers](2025-09/Past-Papers/)" in out2[i]


def test_update_timeline_and_contributors():
    eee = (ROOT / "EEE/README.md").read_text(encoding="utf-8"); f = intake.parse_form(_body())
    out = intake.update_timeline(eee, f, "Joyce", "COM107_Circuits_and_Devices")
    assert "| 2022-04 | [COM107](COM107_Circuits_and_Devices/) | [Circuits and Devices](COM107_Circuits_and_Devices/) | Joyce |" in out
    assert intake.update_timeline(out, f, "Joyce", "COM107_Circuits_and_Devices") == out
    ait = (ROOT / "AIT/README.md").read_text(encoding="utf-8")
    assert "### 其他同学 | Other contributors" in intake.update_timeline(ait, f, "Joyce", "COM107_Circuits_and_Devices")
    c = (ROOT / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    assert intake.update_contributors(c, f, "Joyce", 2) == c            # Joyce already listed
    out = intake.update_contributors(c, f, "[newbie](https://github.com/newbie)", 2).splitlines()
    i = next(k for k, l in enumerate(out) if l.startswith("| [newbie]"))
    assert "2021 入学（2025 届）" in out[i] and "2 份 COM107 2022-04 Past-Papers" in out[i] and out[i + 1].startswith("| [Name] | 2021")
    assert intake.update_contributors(c, intake.parse_form(_body().replace(intake.CREDIT_NICK, intake.CREDIT_ANON)), "匿名 / anonymous", 2) == c


def test_apply_places_files_and_matches_course_across_programmes():
    tmp = _repo_copy(); w = pathlib.Path(tempfile.mkdtemp()); _pdf(w / "final.pdf")
    f = intake.parse_form(_body().replace("EEE\n", "AIT\n"))         # an EEE course uploaded from the AIT form stays under EEE
    pl = intake.apply(tmp, f, [("final.pdf", w / "final.pdf")], "someone")
    assert pl.course_dir == "EEE/COM107_Circuits_and_Devices" and not list((tmp / "AIT").glob("COM107*"))
    assert pl.placed == [("final.pdf", "EEE/COM107_Circuits_and_Devices/2022-04/Past-Papers/COM107_202204_Final_Question.pdf")]
    assert any("EEE" in n for n in pl.notes) and (tmp / pl.placed[0][1]).is_file()
    assert "| 2022-04 | [COM107](COM107_Circuits_and_Devices/) |" in (tmp / "EEE/README.md").read_text(encoding="utf-8")
    g = intake.parse_form(_body().replace("com107", "EEE999").replace("Circuits and Devices", "New Course"))
    pl2 = intake.apply(tmp, g, [("final.pdf", w / "final.pdf")], "someone")
    assert pl2.created_readme and (tmp / "EEE/EEE999_New_Course/README.md").read_text(encoding="utf-8").startswith("# EEE999 New Course")
    assert "| EEE999 |" in (tmp / "EEE/README.md").read_text(encoding="utf-8")   # index regenerated


def test_shared_courses_live_under_ge():
    """G electives and MPU compulsory courses belong to every programme: they sit under GE/ whatever the form says,
    and the uploader's own programme timeline links to them."""
    assert all(intake.is_shared(c) for c in ("G0191", "GE0227", "MPU3.1", "MPU1.1")) and not intake.is_shared("COM107")
    tmp = _repo_copy(); w = pathlib.Path(tempfile.mkdtemp()); _pdf(w / "final.pdf")
    f = intake.parse_form(_body().replace("EEE\n", "AIT\n").replace("com107", "MPU3.1").replace("Circuits and Devices", "Constitution"))
    pl = intake.apply(tmp, f, [("final.pdf", w / "final.pdf")], "someone")
    assert pl.course_dir == "GE/MPU3.1_Introduction_to_the_Constitution_of_Malaysia" and not list((tmp / "AIT").glob("MPU3.1*"))
    assert not any("already lives" in n for n in pl.notes)
    assert "| 2022-04 | [MPU3.1](../GE/MPU3.1_Introduction_to_the_Constitution_of_Malaysia/) |" in (tmp / "AIT/README.md").read_text(encoding="utf-8")
    ge = (tmp / "GE/README.md").read_text(encoding="utf-8")
    assert "2022-04" in next(l for l in ge.splitlines() if l.startswith("| MPU3.1 |"))   # index rerun, taken-in from the AIT timeline
    g = intake.parse_form(_body().replace("com107", "G0999").replace("Circuits and Devices", "New Elective"))
    pl2 = intake.apply(tmp, g, [("final.pdf", w / "final.pdf")], "someone")
    assert pl2.course_dir == "GE/G0999_New_Elective" and pl2.created_readme and not list((tmp / "EEE").glob("G0999*"))
    assert "| G0999 |" in (tmp / "GE/README.md").read_text(encoding="utf-8")
    eee = (tmp / "EEE/README.md").read_text(encoding="utf-8")
    assert "| 2022-04 | [G0999](../GE/G0999_New_Elective/) |" in eee and "| G0999 |" not in eee


def test_dry_run_end_to_end():
    import subprocess, sys
    tmp = _repo_copy(); w = pathlib.Path(tempfile.mkdtemp()); _pdf(w / "final.pdf"); _docx(w / "sheet.docx")
    form = w / "form.md"; form.write_text(_body().replace("Past-Papers", "Tutorials").replace("Final", "_No response_"), encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "intake/intake.py"), "--dry-run", "--form", str(form), "--files", str(w / "final.pdf"), str(w / "sheet.docx"),
                        "--repo", str(tmp), "--login", "tester", "--issue", "7", "--work", str(w / "work")], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    body = (w / "work/PR_BODY.md").read_text(encoding="utf-8")
    assert "EEE/COM107_Circuits_and_Devices/2022-04/Tutorials/COM107_202204_final.pdf" in body and "COM107_202204_sheet.docx" in body
    assert "EEE2109300" in body and "answer scheme" in body.lower()      # flagged, not blocked
    assert "Closes #7" in body and "python site/build.py" in body
    assert (tmp / "EEE/COM107_Circuits_and_Devices/2022-04/Tutorials/COM107_202204_sheet.docx").is_file()
    b = subprocess.run([sys.executable, str(ROOT / "site/build.py"), "--root", str(tmp), "--out", str(w / "site2")], capture_output=True, text=True, encoding="utf-8")
    assert b.returncode == 0 and "not indexed" not in b.stderr, b.stderr


def test_dry_run_validation_failure_writes_problems():
    import subprocess, sys
    tmp = _repo_copy(); w = pathlib.Path(tempfile.mkdtemp())
    form = w / "form.md"; form.write_text(_body().replace("2022-04", "April 2022"), encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "intake/intake.py"), "--dry-run", "--form", str(form), "--repo", str(tmp), "--work", str(w / "work")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert "Session" in (w / "work/PROBLEMS.md").read_text(encoding="utf-8") and not (w / "work/PR_BODY.md").exists()


def test_issue_form_matches_parser():
    """The form's labels are the parser's keys; they must agree byte for byte."""
    yml = (ROOT / ".github/ISSUE_TEMPLATE/upload.yml").read_text(encoding="utf-8")
    for title in intake.FIELDS.values():
        assert f'label: "{title}"\n' in yml, title
    for s in intake.CHECKS:
        assert f'- label: "{s}"\n' in yml, s
    for opt in intake.PROGS + intake.SUBS + intake.CREDITS:
        assert f'- "{opt}"\n' in yml, opt
    assert "labels: [upload]" in yml
    assert (ROOT / ".github/ISSUE_TEMPLATE/config.yml").read_text(encoding="utf-8").strip() == "blank_issues_enabled: true"


# ---- review fixes

def test_validate_accepts_general_education_codes():
    for code in ("MPU3.1", "MPU1.1", "G0191", "GE0227", "EEE999", "com107"):
        f = intake.parse_form(_body(com107=code))
        assert intake.validate(f) == [], (code, intake.validate(f))
    for code in ("MP.1", "COM1", "MPU3.1.2", "1234"):
        assert any("Course code" in p for p in intake.validate(intake.parse_form(_body(com107=code)))), code


def test_cell_neutralizes_html_and_course_name_too():
    assert intake._cell("<b>x</b> | y\nz") == "&lt;b&gt;x&lt;/b&gt; \\| y z"
    readme = intake.new_course_readme("AIT101", "Intro <b>AI</b>")
    assert "<b>" not in readme and readme.startswith("# AIT101 Intro &lt;b&gt;AI&lt;/b&gt;")


def test_pr_body_keeps_user_text_in_code_spans():
    f = intake.parse_form(_body())
    pl = intake.Placement("EEE/COM107_Circuits_and_Devices", False,
                          [("@someone fixes #3 `x`.pdf", "EEE/COM107_Circuits_and_Devices/2022-04/Past-Papers/COM107_202204_Final_Question.pdf")], [], {})
    body = intake.pr_body(f, pl, [("<img src=x onerror=1>.jpg", "r | r")], {}, {}, (True, []), "abc1234", None, "upload/issue-9", 9)
    assert body.count("@someone") == 1 and re.search(r"`[^`\n]*@someone fixes #3 'x'\.pdf`", body)
    assert "<img" not in body and "Closes #9" in body


def test_unpack_reports_broken_zip_members():
    import zipfile
    work = pathlib.Path(tempfile.mkdtemp()); z = work / "b.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("ok.pdf", b"%PDF ok"); zf.writestr("x.pdf", b"%PDF hello world")
    raw = bytearray(z.read_bytes()); i = raw.find(b"hello world"); raw[i:i + 5] = b"HELLO"; z.write_bytes(bytes(raw))   # bad CRC
    ok, bad, _ = intake.unpack([("b.zip", z)], work)
    assert [n for n, _ in ok] == ["ok.pdf"] and [n for n, _ in bad] == ["b.zip › 2"] and " | " in bad[0][1]


def test_zip_entry_names_with_backslashes():
    """Python's zipfile normalises separators on Windows but not on the Linux runner, so the helpers are tested directly."""
    assert intake._basename("dir\\c.pdf") == "c.pdf" and intake._basename("a/b/c.pdf") == "c.pdf"
    assert intake._skip("__MACOSX\\._c.pdf") and intake._skip("__MACOSX/._c.pdf") and not intake._skip("dir\\c.pdf")
    assert intake._reject_reason("..\\x.pdf", "pdf") and intake._reject_reason("../x.pdf", "pdf")


def test_contributors_dedupe_by_name_cell():
    c = (ROOT / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    f = intake.parse_form(_body(Joyce="Lu").replace("2021", "2023"))
    assert "| Lu | 2023 入学（2027 届）|" in intake.update_contributors(c, f, "Lu", 1)        # "Lu" is inside "LucasXQY" but not a listed name
    g = intake.parse_form(_body().replace(intake.CREDIT_NICK, intake.CREDIT_LOGIN))
    assert intake.update_contributors(c, g, "[LucasXQY](https://github.com/LucasXQY)", 1) == c   # listed as plain LucasXQY


def test_course_readme_order_and_login_variant():
    text = ("# X\n\n| 学期 / Session | 老师 / Lecturer | 考核 / Assessment | 资料来自 / Contributed by | 备注 / Notes |\n|---|---|---|---|---|\n"
            "| [unknown](unknown/) |  |  | LucasXQY | [Notes](unknown/Notes/) |\n"
            "| [2024-09](2024-09/) |  |  | LucasXQY | [Tutorials](2024-09/Tutorials/) |\n"
            "| [2025-04](2025-04/) |  |  | LucasXQY | [Labs](2025-04/Labs/) |\n")
    out = intake.update_course_readme(text, intake.parse_form(_body().replace("2022-04", "2026-04")), "Joyce").splitlines()
    assert out[-1].startswith("| [2026-04]") and out[-2].startswith("| [2025-04]")
    g = intake.parse_form(_body().replace("2022-04", "2024-09"))
    row = next(l for l in intake.update_course_readme(text, g, "[LucasXQY](https://github.com/LucasXQY)").splitlines() if l.startswith("| [2024-09]"))
    assert row.count("LucasXQY") == 1


def test_rejected_lines_capped():
    text = intake.rejected_lines([(f"p{i}.jpg", "no | no") for i in range(100)])
    assert text.count("\n") < 40 and "70" in text


def test_course_dir_name_collapses_separators():
    assert intake.course_dir_name("EEE212", "Signals & Systems") == "EEE212_Signals_Systems"
    assert intake.course_dir_name("MPU3.1", " Intro  to  Law ") == "MPU3.1_Intro_to_Law"


def test_attachment_name_comes_from_url():
    assert intake.attachment_links("[x.pdf](https://github.com/user-attachments/files/1/x.zip)") == [("x.zip", "https://github.com/user-attachments/files/1/x.zip")]
    assert intake.attachment_links("[a](https://github.com/user-attachments/files/2/My%20File.pdf)") == [("My File.pdf", "https://github.com/user-attachments/files/2/My%20File.pdf")]


def test_git_errors_carry_stderr():
    try:
        intake.Git(pathlib.Path(tempfile.mkdtemp())).head(); assert False
    except RuntimeError as e:
        assert "repository" in str(e).lower()


# ---- Claude pre-check (llm/claude_check.py does the call; here: what is sent, caching, limits, the PR section)

VERDICT = {"summary": "期末试卷 | final paper", "answers": "yes", "personal_data": "no", "marking_scheme": "unsure",
           "notes": "第 3 页有手写答案 | handwritten answers on page 3"}


def test_precheck_input_sends_pdfs_whole_and_other_files_as_text():
    import fitz
    w = pathlib.Path(tempfile.mkdtemp()); _pdf(w / "a.pdf"); _docx(w / "b.docx", body="Question 2 only")
    blocks, note = intake.precheck_input(w / "a.pdf")
    assert blocks["type"] == "document" and blocks["source"]["media_type"] == "application/pdf" and note == ""
    long = fitz.open(); [long.new_page() for _ in range(intake.PRECHECK_PAGES + 5)]; long.save(w / "long.pdf"); long.close()
    blocks, note = intake.precheck_input(w / "long.pdf")
    import base64
    assert len(fitz.open(stream=base64.b64decode(blocks["source"]["data"]), filetype="pdf")) == intake.PRECHECK_PAGES
    assert str(intake.PRECHECK_PAGES) in note                                     # the PR says only part was read
    blocks, note = intake.precheck_input(w / "b.docx")
    assert blocks["type"] == "text" and "Question 2 only" in blocks["text"]


def test_precheck_caches_by_file_hash_and_respects_the_limit():
    w = pathlib.Path(tempfile.mkdtemp()); _pdf(w / "a.pdf"); _pdf(w / "b.pdf", text="other")
    files = {"X/a.pdf": w / "a.pdf", "X/b.pdf": w / "b.pdf"}
    asked = []

    def ask(content):
        asked.append(content)
        return dict(VERDICT)
    out = intake.precheck(files, {}, ask=ask, take=lambda files: True)
    assert len(asked) == 2 and {r["status"] for r in out.values()} == {"ok"} and out["X/a.pdf"]["answers"] == "yes"
    cache = {r["sha"]: {k: r[k] for k in VERDICT} for r in out.values()}
    again = intake.precheck(files, cache, ask=ask, take=lambda files: True)             # a rebuild: nothing is sent again
    assert len(asked) == 2 and {r["status"] for r in again.values()} == {"cached"}
    assert {r["status"] for r in intake.precheck(files, {}, ask=ask, take=lambda files: False).values()} == {"limit"}
    assert {r["status"] for r in intake.precheck(files, {}, ask=lambda c: None, take=lambda files: True).values()} == {"error"}
    assert {r["status"] for r in intake.precheck(files, {}).values()} == {"off"}    # no API key


def test_precheck_has_no_file_count_cap_and_asks_for_the_files_it_will_send():
    w = pathlib.Path(tempfile.mkdtemp())
    files = {}
    for i in range(25):
        _pdf(w / f"p{i}.pdf", text=f"page {i}"); files[f"X/p{i}.pdf"] = w / f"p{i}.pdf"
    seen = []
    out = intake.precheck(files, {}, ask=lambda c: dict(VERDICT), take=lambda fs: seen.append(list(fs)) or True)
    assert {r["status"] for r in out.values()} == {"ok"} and len(out) == 25          # no "skipped" any more
    assert len(seen) == 1 and sorted(seen[0]) == sorted(files.values())             # one reservation for the whole upload


def test_precheck_estimate_is_a_base_plus_a_rate_per_page_up_to_forty():
    import fitz
    w = pathlib.Path(tempfile.mkdtemp()); _pdf(w / "one.pdf"); _docx(w / "a.docx")
    long = fitz.open(); [long.new_page() for _ in range(90)]; long.save(w / "long.pdf"); long.close()
    assert round(intake.precheck_estimate([w / "one.pdf"]), 6) == 0.065 and round(intake.precheck_estimate([w / "a.docx"]), 6) == 0.065
    assert round(intake.precheck_estimate([w / "long.pdf"]), 6) == 1.04              # 0.04 + 0.025 x 40
    assert round(intake.precheck_estimate([w / "one.pdf", w / "long.pdf"]), 6) == 1.105 and intake.precheck_estimate([]) == 0


def test_the_prechecker_reserves_by_pages_and_settles_the_difference_once():
    import os
    sys.path.insert(0, str(ROOT / "llm"))
    import claude_check as cc
    w = pathlib.Path(tempfile.mkdtemp()); _pdf(w / "a.pdf")
    calls = []

    class FakeBudget:
        def __init__(self, repo): pass
        def reserve(self, pool, usd): calls.append(("reserve", pool, round(usd, 6))); return usd < 1
        def settle(self, pool, delta): calls.append(("settle", pool, round(delta, 6)))
    real = (cc.Budget, cc.ask, os.environ.get("ANTHROPIC_API_KEY"))
    cc.Budget = FakeBudget
    cc.ask = lambda task, system, content, schema, max_tokens=0, on_cost=None: (on_cost(0.01), dict(VERDICT))[1]
    os.environ["ANTHROPIC_API_KEY"] = "test"
    try:
        ask, take, settle = intake.make_prechecker("r/r")
        assert take([w / "a.pdf"]) and ask([]) is not None
        settle(); settle()                                                            # the second call has nothing left to book
        assert calls == [("reserve", "upload", 0.065), ("settle", "upload", round(0.01 - 0.065, 6))]
        calls.clear(); assert take([w / "a.pdf"] * 20) is False                      # 1.3 USD does not fit; nothing reserved
        settle(); assert calls == [("reserve", "upload", 1.3)]
    finally:
        cc.Budget, cc.ask = real[0], real[1]
        os.environ.pop("ANTHROPIC_API_KEY", None) if real[2] is None else os.environ.__setitem__("ANTHROPIC_API_KEY", real[2])


def test_pr_body_shows_the_precheck_and_carries_its_cache():
    tmp = _repo_copy(); w = pathlib.Path(tempfile.mkdtemp()); _pdf(w / "final.pdf")
    f = intake.parse_form(_body())
    pl = intake.apply(tmp, f, [("final.pdf", w / "final.pdf")], "someone")
    rel = pl.placed[0][1]
    pre = {rel: {"status": "ok", "sha": "s" * 64, **VERDICT}}
    body = intake.pr_body(f, pl, [], {}, {}, (True, []), "abc1234", None, "upload/issue-9", 9, prechecks=pre)
    assert "## Claude 预检 | Claude pre-check" in body and "⚠️" in body and "❓" in body and "handwritten answers on page 3" in body
    assert intake.parse_precheck_cache(body) == {"s" * 64: VERDICT}
    off = intake.pr_body(f, pl, [], {}, {}, (True, []), "abc1234", None, "upload/issue-9", 9,
                         prechecks={rel: {"status": "off", "sha": "t"}})
    assert "未运行" in off and intake.parse_precheck_cache(off) == {}
    assert intake.parse_precheck_cache("no cache here") == {} and intake.parse_precheck_cache("<!-- claude-precheck !!! -->") == {}


class _FakeGH:
    def __init__(self, body, labels=("upload",)):
        self.body, self.labels, self.calls = body, list(labels), []
    def issue(self, n): return {"body": self.body, "title": "t", "state": "open", "login": "alice", "id": 111, "labels": self.labels}
    def comment(self, n, text): self.calls.append(("comment", text))
    def comment_pr(self, n, text): self.calls.append(("comment_pr", text))
    def label(self, n, add=(), remove=()): self.calls.append(("label", tuple(add), tuple(remove)))
    def pr_for(self, branch): return None
    def create_or_edit_pr(self, branch, title, body): self.calls.append(("pr", title, body)); return "https://example/pr/1"


class _FakeGit:
    def __init__(self): self.calls = []
    def reset_branch(self, name): self.calls.append(("reset", name))
    def head(self): return "0123456789abcdef"
    def commit_all(self, message, author): self.calls.append(("commit", message, author))
    def force_push(self, name): self.calls.append(("push", name))


def test_run_issue_glue_with_fakes():
    tmp = _repo_copy(); w = pathlib.Path(tempfile.mkdtemp()); _pdf(w / "paper.pdf")
    real = intake.download
    intake.download = lambda links, work: ([("paper.pdf", w / "paper.pdf")], [("dead.pdf", "下载失败 | download failed: 404")])
    try:
        gh = _FakeGH(_body().replace("EEE\n", "AIT\n").replace("com107", "MPU3.1").replace(intake.CREDIT_NICK, intake.CREDIT_ANON)); git = _FakeGit()
        intake.run_issue(5, tmp, gh, git, "https://run", w / "work")
        assert git.calls[0] == ("reset", "upload/issue-5") and git.calls[-1] == ("push", "upload/issue-5")
        assert git.calls[1][2] == intake.BOT_AUTHOR and "MPU3.1 2022-04 Past-Papers" in git.calls[1][1]
        pr = next(c for c in gh.calls if c[0] == "pr")
        assert "MPU3.1" in pr[1] and "Closes #5" in pr[2] and "GE/MPU3.1_Introduction" in pr[2] and "CONTRIBUTORS.md" in pr[2]
        first = next(c for c in gh.calls if c[0] == "comment")
        assert "https://example/pr/1" in first[1] and "dead.pdf" in first[1]
        assert ("label", ("pr-opened",), ()) in gh.calls and "comment_pr" not in [c[0] for c in gh.calls]
        gh2 = _FakeGH(_body().replace("2022-04", "soon")); git2 = _FakeGit()                    # invalid form
        intake.run_issue(6, tmp, gh2, git2, None, w / "work")
        assert git2.calls == [] and [c[0] for c in gh2.calls] == ["comment", "label"] and "Session" in gh2.calls[0][1]
        gh3 = _FakeGH(_body().replace("2022-04", "soon"), labels=("upload", "needs-info"))        # sweep: already told, stay quiet
        intake.run_issue(6, tmp, gh3, _FakeGit(), None, w / "work", sweep=True)
        assert gh3.calls == []
    finally:
        intake.download = real


def _decide_bits():
    from decide import Decision, Check
    from items import Item
    return Decision, Check, Item


def _mk_items(w, specs):
    Decision, Check, Item = _decide_bits()
    items = {}
    for k, text in specs:
        p = _pdf(w / f"orig_{k}_张三.pdf", text=text) or (w / f"orig_{k}_张三.pdf")
        items[k] = Item(k, f"x{k}.pdf", p, "0" * 64, "pdf", 1, False, [text])
    return items


def _with_course(root, folder):
    import shutil
    (root / "EEE" / folder).mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "EEE" / folder / "README.md", root / "EEE" / folder / "README.md")


def test_apply_decisions_files_each_item_and_registers_each_course():
    Decision, Check, Item = _decide_bits()
    root = _repo_copy(); w = pathlib.Path(tempfile.mkdtemp())
    _with_course(root, "COM103_Electronic_Engineering")
    items = _mk_items(w, [(1, "Q1"), (2, "Lab 2"), (3, "?")])
    f = intake.parse_form(_body())
    ds = [Decision(1, "commit", "COM107", "", "2022-04", "Past-Papers", "Final"),
          Decision(2, "commit", "COM103", "", "unknown", "Labs", "Lab2_Manual"),
          Decision(3, "inbox"), Decision(4, "skip")]
    pl = intake.apply_decisions(root, f, ds, items, "someone", 12)
    paths = dict(pl.placed)
    assert paths[1].endswith("/2022-04/Past-Papers/COM107_202204_Final_Question.pdf")
    assert paths[2].endswith("/unknown/Labs/COM103_unknown_Lab2_Manual.pdf")
    assert pl.inbox == ["_待整理/issue-12/item-3.pdf"] and (root / pl.inbox[0]).exists() and not pl.parked
    assert len(pl.courses) == 2 and "2022-04" in (root / (paths[1].split("/2022-04/")[0] + "/README.md")).read_text(encoding="utf-8")
    assert not any("张三" in str(p) for p in root.rglob("*")) and set(pl.meta) == {paths[1], paths[2], pl.inbox[0]}
    g = intake.parse_form(_body().replace(intake.CREDIT_NICK, intake.CREDIT_LOGIN))
    root2 = _repo_copy(); _with_course(root2, "COM103_Electronic_Engineering")
    intake.apply_decisions(root2, g, ds, items, "newbie", 12)
    assert "1 份 COM107 2022-04 Past-Papers、1 份 COM103 unknown Labs / 1 Past-Papers files for COM107 2022-04, 1 Labs files for COM103 unknown" in (root2 / "CONTRIBUTORS.md").read_text(encoding="utf-8")   # committed files only, every course described


def test_apply_decisions_no_timeline_row_for_unknown_session_of_other_course():
    Decision, Check, Item = _decide_bits()
    root = _repo_copy(); w = pathlib.Path(tempfile.mkdtemp())
    _with_course(root, "COM103_Electronic_Engineering")
    items = _mk_items(w, [(1, "a"), (2, "b")])
    f = intake.parse_form(_body())
    ds = [Decision(1, "commit", "COM107", "", "2022-04", "Past-Papers", "Final"),
          Decision(2, "commit", "COM103", "", "unknown", "Labs", "Lab")]
    intake.apply_decisions(root, f, ds, items, "someone", 1)
    eee = (root / "EEE/README.md").read_text(encoding="utf-8")
    assert "| 2022-04 | [COM107](COM107_Circuits_and_Devices/) |" in eee
    assert not any(l.startswith("| unknown | [COM103]") for l in eee.splitlines())
    # a known session of another course does get a row, with that session as the taken-term
    items2 = _mk_items(w, [(1, "a")])
    intake.apply_decisions(root, f, [Decision(1, "commit", "COM103", "", "2021-09", "Labs", "Lab")], items2, "someone", 2)
    assert "| 2021-09 | [COM103](COM103_Electronic_Engineering/) |" in (root / "EEE/README.md").read_text(encoding="utf-8")


def test_apply_decisions_new_course_needs_a_name_else_parks():
    Decision, Check, Item = _decide_bits()
    root = _repo_copy(); w = pathlib.Path(tempfile.mkdtemp())
    items = _mk_items(w, [(1, "a"), (2, "b"), (3, "c")])
    f = intake.parse_form(_body())
    ds = [Decision(1, "commit", "EEE777", "", "2022-04", "Labs", "Lab"),
          Decision(2, "commit", "EEE888", "Brand New", "2022-04", "Labs", "Lab"),
          Decision(3, "commit", "../../x", "", "2022-04", "Labs", "Lab")]
    pl = intake.apply_decisions(root, f, ds, items, "someone", 7)
    assert [k for k, _ in pl.parked] == [1, 3] and all(" | " in r for _, r in pl.parked)
    assert (root / "_待整理/issue-7/item-1.pdf").exists() and (root / "_待整理/issue-7/item-3.pdf").exists()
    assert not list((root / "EEE").glob("EEE777*")) and not (root / "x").exists()
    assert pl.created_readme and pl.courses == ["EEE/EEE888_Brand_New"] and pl.inbox == []
    assert (root / "EEE/EEE888_Brand_New/README.md").read_text(encoding="utf-8").startswith("# EEE888 Brand New")
    g = intake.parse_form(_body().replace("EEE\n", "AIT\n"))
    pl2 = intake.apply_decisions(root, g, [Decision(1, "commit", "G0777", "New Elective", "2022-04", "Notes", "")], items, "someone", 8)
    assert pl2.courses == ["GE/G0777_New_Elective"]
    assert "| 2022-04 | [G0777](../GE/G0777_New_Elective/) |" in (root / "AIT/README.md").read_text(encoding="utf-8")


def test_apply_decisions_lecturer_weighting_notes_per_course_and_files_override():
    Decision, Check, Item = _decide_bits()
    root = _repo_copy(); w = pathlib.Path(tempfile.mkdtemp())
    _with_course(root, "COM103_Electronic_Engineering")
    items = _mk_items(w, [(1, "a"), (2, "b")])
    red = _pdf(w / "redacted.pdf", text="REDACTED COPY") or w / "redacted.pdf"
    f = intake.parse_form(_body().replace("### 老师 | Lecturer\n\n_No response_", "### 老师 | Lecturer\n\nDr Form").replace(
        "### 备注 / 小贴士 | Notes\n\n_No response_", "### 备注 / 小贴士 | Notes\n\nForm note"))
    ck = Check("none", "none", "none", "", "", [], ["Dr Ai", "Dr Bee"], "Exam 60%")
    ds = [Decision(1, "commit", "COM107", "", "2020-01", "Past-Papers", "Final"),
          Decision(2, "commit", "COM103", "", "2020-01", "Labs", "Lab")]
    intake.apply_decisions(root, f, ds, items, "someone", 3, files={2: red}, checks={2: ck})
    r107 = (root / "EEE/COM107_Circuits_and_Devices/README.md").read_text(encoding="utf-8")
    r103 = (root / "EEE/COM103_Electronic_Engineering/README.md").read_text(encoding="utf-8")
    row107 = next(l for l in r107.splitlines() if "2020-01" in l and l.startswith("|"))
    row103 = next(l for l in r103.splitlines() if "2020-01" in l and l.startswith("|"))
    assert "Dr Form" in row107 and "Form note" in row107 and "Dr Ai, Dr Bee" not in row107
    assert "Dr Ai, Dr Bee" in row103 and "Exam 60%" in row103 and "Form note" not in row103 and "Dr Form" not in row103
    import fitz
    placed = next((root / "EEE/COM103_Electronic_Engineering/2020-01/Labs").glob("*.pdf"))
    assert "REDACTED COPY" in fitz.open(placed)[0].get_text()


def test_apply_decisions_lists_a_course_once_and_single_group_wording_is_unchanged():
    Decision, Check, Item = _decide_bits()
    root = _repo_copy(); w = pathlib.Path(tempfile.mkdtemp())
    items = _mk_items(w, [(1, "a"), (2, "b"), (3, "c")])
    g = intake.parse_form(_body().replace(intake.CREDIT_NICK, intake.CREDIT_LOGIN))
    ds = [Decision(1, "commit", "COM107", "", "2020-01", "Labs", "A"), Decision(2, "commit", "COM107", "", "2020-09", "Labs", "B"),
          Decision(3, "commit", "COM107", "", "2020-09", "Labs", "C")]
    pl = intake.apply_decisions(root, g, ds, items, "newbie", 5)
    assert pl.courses == ["EEE/COM107_Circuits_and_Devices"] and pl.course_dir == pl.courses[0]
    c = (root / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    assert "1 份 COM107 2020-01 Labs、2 份 COM107 2020-09 Labs / " in c
    root2 = _repo_copy()
    intake.apply_decisions(root2, g, [Decision(1, "commit", "COM107", "", "2020-01", "Labs", "A"), Decision(2, "commit", "COM107", "", "2020-01", "Labs", "B")],
                           items, "newbie", 5)
    assert "2 份 COM107 2020-01 Labs / 2 Labs files for COM107 2020-01 |" in (root2 / "CONTRIBUTORS.md").read_text(encoding="utf-8")
    rows = [(1, "COM107", "2022-04", "Labs"), (2, "COM103", "unknown", "Tutorials"), (1, "COM104", "2021-09", "Notes"), (1, "COM105", "2020-01", "Tips")]
    out = intake.update_contributors((ROOT / "CONTRIBUTORS.md").read_text(encoding="utf-8"), g, "zed", 5, rows)
    row = next(l for l in out.splitlines() if l.startswith("| zed"))
    assert "Notes等共 5 份 / " in row and "5 files in all" in row and "COM105" not in row


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
