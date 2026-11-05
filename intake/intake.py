"""上传通道机器人：把一个「上传资料」Issue 变成一个待审核的 PR。
Upload-channel bot: turns an "upload material" issue into a pull request for review.

设计见 intake/DESIGN.md；测试 python intake/test_intake.py。
Design in intake/DESIGN.md; tests: python intake/test_intake.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PROGS = ("EEE", "AIT", "ROBO")
SUBS = ("Past-Papers", "Syllabus", "Assignments", "Labs", "Tutorials",
        "Handbooks", "Notes", "Exam-Review", "Tips")
CODE_RE = re.compile(r"^[A-Z]{1,4}\d{3,4}(\.\d)?$")
SESSION_RE = re.compile(r"^\d{4}-\d{2}$")

# form field titles are the parse keys; .github/ISSUE_TEMPLATE/upload.yml must use them byte for byte
FIELDS = {
    "prog": "专业 | Programme",
    "code": "课程代码 | Course code",
    "name": "课程名称 | Course name",
    "session": "学期 | Session",
    "type": "资料类型 | Type",
    "files": "文件 | Files",
    "assessment": "考核名称 | Assessment（试卷用）",
    "lecturer": "老师 | Lecturer",
    "weighting": "考核比例 | Assessment weighting",
    "taken": "你修这门课的学期 | Session you took it",
    "credit": "署名方式 | Credit",
    "nickname": "昵称 | Nickname",
    "intake": "入学年份 | Intake year",
    "notes": "备注 / 小贴士 | Notes",
    "checklist": "确认 | Checklist",
}
CREDIT_LOGIN = "用我的 GitHub 用户名 | My GitHub username"
CREDIT_NICK = "用下面填的昵称 | The nickname below"
CREDIT_ANON = "匿名 | Anonymous"
CREDITS = (CREDIT_LOGIN, CREDIT_NICK, CREDIT_ANON)
CHECKS = (
    "没有答案、评分标准、参考解答 | No answers, marking schemes or model solutions",
    "没有学生姓名、学号、签名，没有老师的私人联系方式和 Moodle 密钥 | No student names, IDs or signatures; no lecturers' private contacts or Moodle keys",
    "这门课是我自己修的，或我有权分享这些文件 | I took this course myself, or I have the right to share these files",
    "我已读 DISCLAIMER，同意这些文件免费公开、非商业使用 | I have read the DISCLAIMER and agree to these files being public, free and non-commercial",
)

NO_RESPONSE = "_No response_"
HEADING_RE = re.compile(r"^### (.*?)\s*$", re.M)
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^\s)]+)\)")
# the two attachment URL shapes GitHub produces for files (images live under user-attachments/assets and are not taken)
ATTACH_RE = re.compile(r"^https://github\.com/(?:user-attachments/files|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/files)/\d+/[^/\s]+$")


@dataclass
class Form:
    prog: str = ""
    code: str = ""
    name: str = ""
    session: str = ""
    type: str = ""
    links: list[tuple[str, str]] = field(default_factory=list)
    assessment: str = ""
    lecturer: str = ""
    weighting: str = ""
    taken: str = ""
    credit: str = ""
    nickname: str = ""
    intake: str = ""
    notes: str = ""
    checked: list[bool] = field(default_factory=lambda: [False] * len(CHECKS))


def _clean(value: str) -> str:
    value = value.strip()
    return "" if value == NO_RESPONSE else value


def parse_form(body: str) -> Form:
    """Split the GitHub-rendered issue body on `### <title>` headings; unknown headings are ignored."""
    body = body.replace("\r\n", "\n")
    sections: dict[str, str] = {}
    parts = HEADING_RE.split(body)  # [preamble, title1, text1, title2, text2, ...]
    for title, text in zip(parts[1::2], parts[2::2]):
        sections[title.strip()] = text
    by_key = {k: _clean(sections.get(t, "")) for k, t in FIELDS.items()}
    checklist = sections.get(FIELDS["checklist"], "")
    checked = [bool(re.search(r"^\s*- \[[xX]\] " + re.escape(s) + r"\s*$", checklist, re.M)) for s in CHECKS]
    f = Form(prog=by_key["prog"], code=by_key["code"].upper(), name=by_key["name"], session=by_key["session"],
             type=by_key["type"], links=attachment_links(sections.get(FIELDS["files"], "")),
             assessment=by_key["assessment"], lecturer=by_key["lecturer"], weighting=by_key["weighting"],
             taken=by_key["taken"], credit=by_key["credit"], nickname=by_key["nickname"],
             intake=by_key["intake"], notes=by_key["notes"], checked=checked)
    if not f.taken:
        f.taken = f.session
    return f


def attachment_links(text: str) -> list[tuple[str, str]]:
    """(display name, url) for every markdown link to a GitHub file attachment; duplicates dropped, order kept."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, url in MD_LINK_RE.findall(text):
        if ATTACH_RE.match(url) and url not in seen:
            seen.add(url)
            out.append((name.strip() or url.rsplit("/", 1)[-1], url))
    return out


def _short(value: str) -> str:
    value = value.replace("\n", " ")
    return value if len(value) <= 40 else value[:37] + "..."


def validate(f: Form) -> list[str]:
    """Bilingual problem lines; empty when the form can be processed."""
    p: list[str] = []
    if f.prog not in PROGS:
        p.append(f"{FIELDS['prog']}：只能是 {' / '.join(PROGS)} | must be one of {' / '.join(PROGS)}")
    if not CODE_RE.match(f.code):
        p.append(f"{FIELDS['code']}：应像 COM107、EEE212、MPU3.1 这样，现在是「{_short(f.code)}」 "
                 f"| should look like COM107, EEE212 or MPU3.1; got \"{_short(f.code)}\"")
    if not SESSION_RE.match(f.session):
        p.append(f"{FIELDS['session']}：格式是 YYYY-MM，如 2022-04，现在是「{_short(f.session)}」 "
                 f"| must be YYYY-MM, e.g. 2022-04; got \"{_short(f.session)}\"")
    if f.taken != f.session and not SESSION_RE.match(f.taken):
        p.append(f"{FIELDS['taken']}：格式是 YYYY-MM，如 2022-04，现在是「{_short(f.taken)}」 "
                 f"| must be YYYY-MM, e.g. 2022-04; got \"{_short(f.taken)}\"")
    if f.type not in SUBS:
        p.append(f"{FIELDS['type']}：只能是 {' / '.join(SUBS)} 之一 | must be one of {' / '.join(SUBS)}")
    if not f.links:
        p.append(f"{FIELDS['files']}：没找到附件。把文件拖进「文件」框再提交；照片请先合成一个 PDF，单独的图片不收 "
                 f"| no attachment found. Drag the files into the Files box; photos must be combined into one PDF, "
                 f"images on their own are not accepted")
    if f.credit not in CREDITS:
        p.append(f"{FIELDS['credit']}：请从三个选项里选一个 | pick one of the three options")
    if f.credit == CREDIT_NICK and not f.nickname:
        p.append(f"{FIELDS['nickname']}：选了「用昵称」就要填昵称 | you chose the nickname option, so a nickname is required")
    for sentence, ok in zip(CHECKS, f.checked):
        if not ok:
            p.append(f"未勾选 | Unticked: {sentence}")
    return p
