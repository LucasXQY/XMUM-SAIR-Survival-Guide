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


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
