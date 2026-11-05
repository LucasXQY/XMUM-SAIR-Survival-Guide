"""上传通道机器人：把一个「上传资料」Issue 变成一个待审核的 PR。
Upload-channel bot: turns an "upload material" issue into a pull request for review.

设计见 intake/DESIGN.md；测试 python intake/test_intake.py。
Design in intake/DESIGN.md; tests: python intake/test_intake.py.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import sys
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

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


# ---------------------------------------------------------------- files: names, unpacking, limits

ALLOWED = {"pdf", "docx", "pptx", "xlsx", "doc", "ppt", "xls", "txt", "md", "csv"}
MAX_FILES = 60
MAX_BYTES = 300 * 2**20


class IntakeLimit(Exception):
    """Too many files or too many bytes after unpacking; the whole submission is refused."""


def clean_label(stem: str) -> str:
    """Keep [A-Za-z0-9._-]; everything else becomes `_`; runs collapsed; `_` and `.` trimmed at both ends."""
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9._-]", "_", stem)).strip("_.")


def _split_ext(name: str) -> tuple[str, str]:
    stem, dot, ext = name.rpartition(".")
    return (stem, ext.lower()) if dot and stem else (name, "")


def target_name(f: Form, original: str, n_files: int, taken: set[str]) -> str:
    """<CODE>_<YYYYMM>_<Label>.<ext> per CONTRIBUTING; Past-Papers with an assessment get `_Question`."""
    stem, ext = _split_ext(original)
    prefix = f"{f.code}_{f.session.replace('-', '')}_"
    label = clean_label(stem)
    if label.startswith(prefix):
        label = label[len(prefix):]
    if f.type == "Past-Papers" and f.assessment:
        assessment = clean_label(f.assessment.replace(" ", ""))  # "Test 1" -> "Test1"
        label = f"{assessment}_Question" if n_files == 1 else f"{assessment}_{label}_Question"
    label = label or "file"
    base = prefix + label
    name, n = f"{base}.{ext}", 1
    while name in taken:
        n += 1
        name = f"{base}_{n}.{ext}"
    taken.add(name)
    return name


def _reject_reason(name: str, ext: str) -> str | None:
    parts = re.split(r"[\/]", name)
    if ".." in parts or ".." in parts[-1]:
        return "文件名含 ..，不收 | name contains .., refused"
    if ext == "zip":
        return "zip 里的 zip 不解包，请把文件直接放进一个 zip | nested zip not unpacked, put the files in one zip"
    if ext not in ALLOWED:
        return (f"不收 .{ext or '?'} 文件，只收 {' '.join(sorted(ALLOWED))}；照片请合成一个 PDF "
                f"| .{ext or '?'} files are not accepted, only {' '.join(sorted(ALLOWED))}; combine photos into one PDF")
    return None


def _skip(name: str) -> bool:
    """Entries nobody meant to upload: directories, macOS resource forks, dotfiles."""
    parts = re.split(r"[\/]", name)
    return not parts[-1] or "__MACOSX" in parts or parts[-1].startswith(".")


def unpack(downloads: list[tuple[str, Path]], work: Path) -> tuple[list[tuple[str, Path]], list[tuple[str, str]]]:
    """Expand zips, apply the whitelist and the limits. Returns (accepted (name, path), rejected (name, reason))."""
    ok: list[tuple[str, Path]] = []
    bad: list[tuple[str, str]] = []
    total = 0

    def accept(name: str, path: Path) -> None:
        nonlocal total
        total += path.stat().st_size
        ok.append((name, path))
        if len(ok) > MAX_FILES:
            raise IntakeLimit(f"文件超过 {MAX_FILES} 份，请分几次提交 | more than {MAX_FILES} files, please split the submission")
        if total > MAX_BYTES:
            raise IntakeLimit(f"解包后超过 {MAX_BYTES // 2**20} MB，请分几次提交 | more than {MAX_BYTES // 2**20} MB after unpacking, please split the submission")

    for i, (name, path) in enumerate(downloads):
        base = re.split(r"[\/]", name)[-1]
        stem, ext = _split_ext(base)
        if ext == "zip":
            out = work / "unzipped" / str(i)
            out.mkdir(parents=True, exist_ok=True)
            try:
                zf = zipfile.ZipFile(path)
            except zipfile.BadZipFile:
                bad.append((name, "不是有效的 zip | not a valid zip file"))
                continue
            with zf:
                for info in zf.infolist():
                    if info.is_dir() or _skip(info.filename):
                        continue
                    inner = re.split(r"[\/]", info.filename)[-1]
                    reason = _reject_reason(info.filename, _split_ext(inner)[1])
                    if reason:
                        bad.append((info.filename, reason))
                        continue
                    if info.file_size > MAX_BYTES:
                        raise IntakeLimit(f"zip 里有单个文件超过 {MAX_BYTES // 2**20} MB | a file inside the zip exceeds {MAX_BYTES // 2**20} MB")
                    dest = out / inner
                    k = 1
                    while dest.exists():  # same basename in two folders of the zip
                        k += 1
                        dest = out / f"{k}_{inner}"
                    with zf.open(info) as src, open(dest, "wb") as dst:
                        dst.write(src.read())
                    accept(inner, dest)
            continue
        if _skip(base):
            continue
        reason = _reject_reason(name, ext)
        if reason:
            bad.append((name, reason))
        else:
            accept(base, path)
    return ok, bad


# ---------------------------------------------------------------- metadata, content checks, thumbnails

OFFICE = {"docx", "pptx", "xlsx"}
LEGACY = {"doc", "ppt", "xls"}
CORE_TAGS = ("dc:creator", "cp:lastModifiedBy", "dc:title", "dc:subject", "cp:keywords", "dc:description")
APP_TAGS = ("Company", "Manager")
PDF_META_KEYS_IGNORED = ("format", "encryption")  # PyMuPDF always reports these; they carry no personal data

PII_RE = re.compile(
    r"\b[A-Z]{3}\d{7,10}\b"                                  # student id
    r"|student\s*(?:id|no)\b"
    r"|[\w.+-]+@(?!xmu\.edu\.my\b)[\w-]+(?:\.[\w-]+)+"       # any email except the university's
    r"|\b(?:\+?6?01\d[- ]?\d{7,8}|1[3-9]\d{9})\b"            # Malaysian / Chinese mobile numbers
    r"|enrolment key|passcode|password|zoom|meeting id|wechat|whatsapp",
    re.I)
ANS_RE = re.compile(r"marking scheme|answer scheme|model answer|suggested answer|solution|answer key|答案|评分标准|参考解答", re.I)
OFFICE_TEXT_RE = re.compile(r"<(?:w:t|a:t|t)(?:\s[^>]*)?>([^<]*)</(?:w:t|a:t|t)>")


def _blank_tags(xml: bytes, tags: tuple[str, ...]) -> bytes:
    pat = re.compile(rb"<(" + b"|".join(t.encode() for t in tags) + rb")(\s[^>]*)?>.*?</\1>", re.S)
    return pat.sub(lambda m: b"<" + m.group(1) + (m.group(2) or b"") + b"></" + m.group(1) + b">", xml)


def clear_metadata(path: Path) -> str:
    """Strip author-like metadata in place. Returns a short status for the report."""
    ext = _split_ext(path.name)[1]
    tmp = path.with_name(path.name + ".tmp")
    if ext == "pdf":
        try:
            import fitz
            doc = fitz.open(path)
            doc.set_metadata({})
            doc.del_xml_metadata()
            doc.save(tmp, garbage=3, deflate=True)
            doc.close()
        except Exception as e:  # corrupt or encrypted PDF: keep the file, tell the maintainer
            tmp.unlink(missing_ok=True)
            return f"PDF 打不开，请手动检查 | PDF could not be processed, check manually ({type(e).__name__})"
        os.replace(tmp, path)
        return "cleared"
    if ext in OFFICE:
        try:
            with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w") as dst:
                for info in src.infolist():
                    data = src.read(info)
                    if info.filename == "docProps/core.xml":
                        data = _blank_tags(data, CORE_TAGS)
                    elif info.filename == "docProps/app.xml":
                        data = _blank_tags(data, APP_TAGS)
                    dst.writestr(info, data, compress_type=info.compress_type)
        except zipfile.BadZipFile:
            tmp.unlink(missing_ok=True)
            return "不是有效的 Office 文件，请手动检查 | not a valid Office file, check manually"
        os.replace(tmp, path)
        return "cleared"
    if ext in LEGACY:
        return "旧格式，请手动检查 | legacy format, check manually"
    return "n/a"


def _matches(rx: re.Pattern, text: str, limit: int = 10) -> list[str]:
    out: list[str] = []
    for m in rx.finditer(text):
        hit = m.group(0).strip()
        if hit and hit not in out:
            out.append(hit)
            if len(out) >= limit:
                break
    return out


def inspect_file(path: Path) -> dict:
    """What the maintainer wants to know per file; nothing here blocks the PR."""
    ext = _split_ext(path.name)[1]
    info = {"size": path.stat().st_size, "pages": None, "meta_empty": True, "pii": [], "answers": [], "low_text": False}
    text = ""
    if ext == "pdf":
        try:
            import fitz
            with fitz.open(path) as doc:
                info["pages"] = len(doc)
                info["meta_empty"] = not any(v for k, v in doc.metadata.items() if k not in PDF_META_KEYS_IGNORED)
                text = "\n".join(page.get_text() for page in doc)
                info["low_text"] = len(doc) > 0 and len(text.strip()) / len(doc) < 50
        except Exception:
            info["meta_empty"] = False  # unreadable: make the maintainer look
    elif ext in OFFICE:
        try:
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                if "docProps/core.xml" in names:
                    core = zf.read("docProps/core.xml")
                    info["meta_empty"] = not any(m.group(1).strip() for m in re.finditer(
                        rb"<(?:dc:creator|cp:lastModifiedBy)(?:\s[^>]*)?>(.*?)</", core, re.S))
                text = "\n".join(" ".join(OFFICE_TEXT_RE.findall(zf.read(n).decode("utf-8", "ignore")))
                                 for n in names if n.endswith(".xml"))
        except zipfile.BadZipFile:
            info["meta_empty"] = False
    elif ext in LEGACY:
        info["meta_empty"] = False  # cannot be checked here
        text = path.read_bytes().decode("latin-1", "ignore")
    else:
        text = path.read_text(encoding="utf-8", errors="ignore")
    info["pii"] = _matches(PII_RE, text)
    info["answers"] = _matches(ANS_RE, text)
    return info


def thumbnails(pdfs: list[Path], out_png: Path, cols: int = 5, cell: tuple[int, int] = (120, 160)) -> int:
    """First two pages of each PDF as a contact sheet with red file-name labels. Returns the number of cells."""
    import fitz
    cells: list[tuple[str, fitz.Pixmap]] = []
    for pdf in pdfs:
        try:
            with fitz.open(pdf) as doc:
                for i in range(min(2, len(doc))):
                    cells.append((f"{pdf.name} p{i + 1}", doc[i].get_pixmap(dpi=40)))
        except Exception:
            continue
    if not cells:
        return 0
    w, h = cell
    rows = math.ceil(len(cells) / cols)
    sheet = fitz.open()
    page = sheet.new_page(width=cols * w, height=rows * h)
    for k, (label, pix) in enumerate(cells):
        x, y = (k % cols) * w, (k // cols) * h
        page.insert_image(fitz.Rect(x + 4, y + 12, x + w - 4, y + h - 4), pixmap=pix, keep_proportion=True)
        page.insert_text(fitz.Point(x + 4, y + 9), label[:34], fontsize=6, color=(1, 0, 0))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    page.get_pixmap(dpi=96).save(out_png)
    sheet.close()
    return len(cells)


# ---------------------------------------------------------------- registry: course README, timeline, CONTRIBUTORS

ANON = "匿名 / anonymous"
COURSE_TABLE_HEADER = "| 学期 / Session | 老师 / Lecturer | 考核 / Assessment | 资料来自 / Contributed by | 备注 / Notes |"
TIMELINE_HEADING = "### 其他同学 | Other contributors"
TIMELINE_HEADER = "| 学期 / Session | 代码 / Code | 课程 / Course | 贡献者 / Contributor |"
PLACEHOLDER = "| [Name] |"


def _cell(text: str) -> str:
    """User text that goes into a table cell: no newlines, pipes escaped."""
    return re.sub(r"\s*\n\s*", " ", text.strip()).replace("|", "\\|")


def credit_name(f: Form, login: str) -> str:
    if f.credit == CREDIT_ANON:
        return ANON
    if f.credit == CREDIT_NICK:
        return _cell(f.nickname)
    return f"[{login}](https://github.com/{login})"


def find_course_dir(root: Path, code: str) -> Path | None:
    """The existing course folder for a code, whichever programme it sits under."""
    for prog in PROGS:
        hits = sorted(d for d in (root / prog).glob(f"{code}_*") if d.is_dir())
        if hits:
            return hits[0]
    return None


def course_dir_name(code: str, name: str) -> str:
    return f"{code}_{re.sub(r'[^A-Za-z0-9_-]', '', name.strip().replace(' ', '_')).strip('_')}"


def new_course_readme(code: str, name: str) -> str:
    return (f"# {code} {name}\n\n"
            "每个修读学期一行；有新学期的资料就加一行。One row per session; add a row when you contribute material from a new session.\n\n"
            f"{COURSE_TABLE_HEADER}\n|---|---|---|---|---|\n\n- 小贴士 / Tips：\n")


def _split_lines(text: str) -> tuple[list[str], str]:
    eol = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n").split("\n"), eol


def _cells(line: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _table(lines: list[str], header_idx: int) -> tuple[int, int]:
    """(first data row, one past the last data row) of the table whose header is at header_idx."""
    start = header_idx + 2
    end = start
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    return start, end


def _add_token(cell: str, token: str) -> str:
    parts = [t.strip() for t in cell.split(" · ") if t.strip()]
    if token not in parts:
        parts.append(token)
    return " · ".join(parts)


def update_course_readme(text: str, f: Form, credit: str) -> str:
    lines, eol = _split_lines(text)
    type_link = f"[{f.type}]({f.session}/{f.type}/)"
    notes = _cell(f.notes)
    try:
        header = next(i for i, l in enumerate(lines) if l.startswith("| 学期"))
    except StopIteration:
        lines += ["", COURSE_TABLE_HEADER, "|---|---|---|---|---|"]
        header = len(lines) - 2
    start, end = _table(lines, header)
    insert_at = end
    for i in range(start, end):
        cells = _cells(lines[i])
        if len(cells) < 5:
            cells += [""] * (5 - len(cells))
        m = re.search(r"\d{4}-\d{2}", cells[0])
        placeholder = not m or cells[1] == "[Name]" or ("[" in cells[0] and "](" not in cells[0])
        if placeholder:
            insert_at = min(insert_at, i)
            continue
        if m.group(0) == f.session:
            cells[0] = f"[{f.session}]({f.session}/)"
            if not cells[1] and f.lecturer:
                cells[1] = _cell(f.lecturer)
            if not cells[2] and f.weighting:
                cells[2] = _cell(f.weighting)
            cells[3] = _add_token(cells[3], credit)
            cells[4] = _add_token(cells[4], type_link)
            if notes:
                cells[4] = _add_token(cells[4], notes)
            lines[i] = _row(cells)
            return eol.join(lines)
        if m.group(0) > f.session:
            insert_at = min(insert_at, i)
    new_row = _row([f"[{f.session}]({f.session}/)", _cell(f.lecturer), _cell(f.weighting), credit,
                    type_link + (f" · {notes}" if notes else "")])
    lines.insert(insert_at, new_row)
    return eol.join(lines)


def update_timeline(text: str, f: Form, credit: str, dir_name: str) -> str:
    lines, eol = _split_lines(text)
    name = dir_name.split("_", 1)[1].replace("_", " ") if "_" in dir_name else dir_name
    row = f"| {f.taken} | [{f.code}]({dir_name}/) | [{name}]({dir_name}/) | {credit} |"
    if row in lines:
        return text
    try:
        heading = next(i for i, l in enumerate(lines) if l.strip() == TIMELINE_HEADING)
        header = next(i for i in range(heading, len(lines)) if lines[i].startswith("|"))
        _, end = _table(lines, header)
        lines.insert(end, row)
    except StopIteration:
        block = ["", TIMELINE_HEADING, "", TIMELINE_HEADER, "|---|---|---|---|", row, ""]
        at = next((i for i, l in enumerate(lines) if l.startswith("## 文件命名")), None)
        if at is None:
            while lines and lines[-1] == "":
                lines.pop()
            lines += block
        else:
            lines[at:at] = block
    return eol.join(lines)


def update_contributors(text: str, f: Form, credit: str, n: int) -> str:
    if f.credit == CREDIT_ANON or credit in text:
        return text
    lines, eol = _split_lines(text)
    if f.intake.isdigit():
        heading, intake_cell = f"## {f.intake} 入学", f"{f.intake} 入学（{int(f.intake) + 4} 届）"
    else:
        heading, intake_cell = "## 其他入学年份", "待补充 / tbc"
    row = f"| {credit} | {intake_cell}| {n} 份 {f.code} {f.session} {f.type} / {n} {f.type} files for {f.code} {f.session} | |"
    start = next((i for i, l in enumerate(lines) if l.startswith(heading)),
                 next((i for i, l in enumerate(lines) if l.startswith("## 其他入学年份")), None))
    if start is None:
        return text
    at = next((i for i in range(start, len(lines)) if lines[i].startswith(PLACEHOLDER)), None)
    if at is None:  # section without a placeholder row: append to its table
        header = next(i for i in range(start, len(lines)) if lines[i].startswith("|"))
        at = _table(lines, header)[1]
    lines.insert(at, row)
    return eol.join(lines)


@dataclass
class Placement:
    course_dir: str
    created_readme: bool
    placed: list[tuple[str, str]]
    notes: list[str]
    meta: dict[str, str]


def _edit(path: Path, fn) -> None:
    text = path.read_bytes().decode("utf-8")
    new = fn(text)
    if new != text:
        path.write_bytes(new.encode("utf-8"))


def apply(root: Path, f: Form, files: list[tuple[str, Path]], login: str) -> Placement:
    """Copy the accepted files into the tree, clear their metadata, register them, regenerate the index."""
    credit = credit_name(f, login)
    notes: list[str] = []
    course = find_course_dir(root, f.code)
    created = False
    if course is None:
        course = root / f.prog / course_dir_name(f.code, f.name)
        course.mkdir(parents=True, exist_ok=True)
    else:
        prog = course.parent.name
        if prog != f.prog:
            notes.append(f"{f.code} 的课程目录已在 {prog}/ 下，文件归入那里而不是 {f.prog}/ "
                         f"| the {f.code} folder already lives under {prog}/, so the files went there rather than {f.prog}/")
        existing = course.name.split("_", 1)[1].replace("_", " ") if "_" in course.name else ""
        if existing and existing.lower() != " ".join(f.name.split()).lower():
            notes.append(f"表单课名「{f.name}」与目录名「{existing}」不同，沿用目录名 "
                         f"| form says \"{f.name}\" but the folder is \"{existing}\"; the folder name stands")
    if not (course / "README.md").exists():
        (course / "README.md").write_bytes(new_course_readme(f.code, f.name).encode("utf-8"))
        created = True
        notes.append(f"新建了课程目录和 README：{course.parent.name}/{course.name}/ "
                     f"| created the course folder and README: {course.parent.name}/{course.name}/")
    prog = course.parent.name
    target = course / f.session / f.type
    target.mkdir(parents=True, exist_ok=True)
    taken = {p.name for p in target.iterdir()}
    placed: list[tuple[str, str]] = []
    meta: dict[str, str] = {}
    for original, path in files:
        name = target_name(f, original, len(files), taken)
        dest = target / name
        shutil.copyfile(path, dest)
        rel = dest.relative_to(root).as_posix()
        meta[rel] = clear_metadata(dest)
        placed.append((original, rel))
    _edit(course / "README.md", lambda t: update_course_readme(t, f, credit))
    _edit(root / prog / "README.md", lambda t: update_timeline(t, f, credit, course.name))
    _edit(root / "CONTRIBUTORS.md", lambda t: update_contributors(t, f, credit, len(files)))
    subprocess.run([sys.executable, str(root / "scripts" / "update_index.py"), prog],
                   check=True, cwd=root, capture_output=True, text=True)
    return Placement(f"{prog}/{course.name}", created, placed, notes, meta)
