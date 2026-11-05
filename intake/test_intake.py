"""Checks for intake/intake.py. Run from the repo root: python intake/test_intake.py (no network needed)."""
import sys, pathlib, tempfile

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
                                    "[b.pdf](https://github.com/LucasXQY/XMUM-SAIR-Survival-Guide/files/2/b.pdf) "
                                    "[x](https://github.com/user-attachments/assets/abc) "
                                    "[a.pdf](https://github.com/user-attachments/files/1/a.pdf)")
    assert links == [("a.pdf", "https://github.com/user-attachments/files/1/a.pdf"),
                     ("b.pdf", "https://github.com/LucasXQY/XMUM-SAIR-Survival-Guide/files/2/b.pdf")]


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
    ok, bad = intake.unpack([("final.pdf", work / "final.pdf"), ("bundle.zip", z)], work)
    assert [n for n, _ in ok] == ["final.pdf", "b.pdf", "notes.PDF"] and all(p.is_file() for _, p in ok)
    assert {n for n, _ in bad} == {"../evil.pdf", "pic.jpg"} and all(" | " in r for _, r in bad)


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
                "EEE/MPU3.1_Introduction_to_the_Constitution_of_Malaysia/README.md"]:
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
    f = intake.parse_form(_body().replace("EEE\n", "AIT\n").replace("com107", "MPU3.1").replace("Circuits and Devices", "Constitution"))
    pl = intake.apply(tmp, f, [("final.pdf", w / "final.pdf")], "someone")
    assert pl.course_dir == "EEE/MPU3.1_Introduction_to_the_Constitution_of_Malaysia" and not list((tmp / "AIT").glob("MPU3.1*"))
    assert pl.placed == [("final.pdf", "EEE/MPU3.1_Introduction_to_the_Constitution_of_Malaysia/2022-04/Past-Papers/MPU3.1_202204_Final_Question.pdf")]
    assert any("EEE" in n for n in pl.notes) and (tmp / pl.placed[0][1]).is_file()
    assert "| 2022-04 | [MPU3.1]" in (tmp / "EEE/README.md").read_text(encoding="utf-8")
    g = intake.parse_form(_body().replace("com107", "EEE999").replace("Circuits and Devices", "New Course"))
    pl2 = intake.apply(tmp, g, [("final.pdf", w / "final.pdf")], "someone")
    assert pl2.created_readme and (tmp / "EEE/EEE999_New_Course/README.md").read_text(encoding="utf-8").startswith("# EEE999 New Course")
    assert "| EEE999 |" in (tmp / "EEE/README.md").read_text(encoding="utf-8")   # index regenerated


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
