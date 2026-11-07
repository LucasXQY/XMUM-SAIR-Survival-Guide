"""Where each file ends up (spec section 6). Pure functions: no network, no files."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import intake

SKIP_REASONS = ("lecture_slides", "textbook", "answers", "marking_scheme", "student_work", "not_course_material", "other")
SKIP_TEXT = {
    "lecture_slides": ("讲义", "lecture slides"),
    "textbook": ("课本", "textbook"),
    "answers": ("含答案", "contains answers"),
    "marking_scheme": ("评分标准", "marking scheme"),
    "student_work": ("学生作业", "student work"),
    "not_course_material": ("不是课程资料", "not course material"),
    "other": ("其他原因", "other reason"),
}
LABEL_MAX = 40


@dataclass
class Sort:
    course_code: str
    course_name: str
    session: str
    type: str
    label: str
    assessment: str
    set: str
    keep: bool
    skip_reason: str
    confident: bool
    note: str


@dataclass
class Check:
    answers: str
    marking_scheme: str
    personal_data: str
    summary: str
    notes: str
    redactions: list = field(default_factory=list)
    lecturers: list = field(default_factory=list)
    weighting: str = ""


@dataclass
class Decision:
    k: int
    outcome: str                 # commit | inbox | skip | maybe_skip | review
    code: str = ""
    name: str = ""
    session: str = "unknown"
    type: str = ""
    label: str = ""
    set: str = ""
    reason: str = ""
    flags: list = field(default_factory=list)
    blocking: bool = False


def _label(value) -> str:
    return intake.clean_label(str(value or ""))[:LABEL_MAX].strip("_.")


def validate_sort(raw, cat_codes: set[str]) -> Sort | None:
    """Untrusted model output in, a Sort whose path-shaping fields are safe out."""
    if not isinstance(raw, dict):
        return None
    confident = raw.get("confident") is True
    code = str(raw.get("course_code") or "").strip().upper()
    if not intake.CODE_RE.fullmatch(code):
        code, confident = "", False
    session = str(raw.get("session") or "").strip()
    if session != "unknown" and not intake.SESSION_RE.fullmatch(session):
        session, confident = "unknown", False
    typ = str(raw.get("type") or "").strip()
    if typ not in intake.SUBS:
        typ, confident = "", False
    reason = str(raw.get("skip_reason") or "").strip()
    keep = raw.get("keep") is not False
    if keep:
        reason = ""
    elif reason not in SKIP_REASONS:
        reason = "other"
    parts = {}
    for key in ("label", "assessment", "set"):
        text = str(raw.get(key) or "")
        if any(bad in text for bad in ("/", "\\", "..")):
            confident = False
        parts[key] = _label(text)
    return Sort(course_code=code, course_name=str(raw.get("course_name") or "").strip()[:80], session=session,
                type=typ, label=parts["label"], assessment=parts["assessment"],
                set=parts["set"], keep=keep, skip_reason=reason, confident=confident,
                note=str(raw.get("note") or "").strip()[:200])


def resolve_session(sort: Sort, form) -> str:
    if intake.SESSION_RE.fullmatch(sort.session or ""):
        return sort.session
    if sort.course_code and sort.course_code == form.code:
        for hint in (form.session, form.taken):
            if intake.SESSION_RE.fullmatch(hint or ""):
                return hint
    return "unknown"


def _strip_set(value: str) -> str:
    return re.sub(r"^set[_-]?", "", _label(value), flags=re.I)


def file_name(code, session, type, label, set, ext, taken: set[str]) -> str:
    if not isinstance(code, str) or not intake.CODE_RE.fullmatch(code):
        raise ValueError("bad course code")
    if not isinstance(session, str) or not (session == "unknown" or intake.SESSION_RE.fullmatch(session)):
        raise ValueError("bad session")
    if type not in intake.SUBS:
        raise ValueError("bad type")
    when = session.replace("-", "")
    label = _label(label)
    if type == "Past-Papers":
        label = re.sub(r"_?Question$", "", label, flags=re.I).strip("_.") or "PastPaper"
        s = _strip_set(set)
        stem = f"{code}_{when}_{label}" + (f"_Set{s}" if s else "") + "_Question"
    else:
        stem = f"{code}_{when}_{label or type.replace('-', '')}"
    name, n = f"{stem}.{ext}", 1
    while name in taken:
        n += 1
        name = f"{stem}_{n}.{ext}"
    taken.add(name)
    return name


def _usable_place(p) -> dict | None:
    if not isinstance(p, dict):
        return None
    code = str(p.get("code") or "").strip().upper()
    session = str(p.get("session") or "").strip()
    typ = str(p.get("type") or "").strip()
    if not intake.CODE_RE.fullmatch(code) or typ not in intake.SUBS:
        return None
    if not intake.SESSION_RE.fullmatch(session):
        session = "unknown"
    return {"code": code, "session": session, "type": typ, "label": _label(p.get("label"))}


def decide(item, sort, check, form, override, dup) -> Decision:
    override = override or {}
    k = item.k
    flags: list[str] = []

    def done(outcome, reason, **kw):
        return Decision(k=k, outcome=outcome, reason=reason, flags=flags,
                        blocking=outcome in ("inbox", "review"), **kw)

    if override.get("skip"):
        return done("skip", "维护者选择不收 | skipped by a maintainer")
    if dup:
        return done("skip", f"重复，仓库已有 | duplicate of {dup}")

    place = _usable_place(override.get("place"))
    approved = re.sub(r"[^A-Za-z0-9-]", "", str(override.get("approved_by") or ""))
    s = sort or Sort("", "", "unknown", "", "", "", "", True, "", False, "")
    if override.get("keep"):
        s = Sort(**{**s.__dict__, "keep": True, "skip_reason": ""})
    if place:
        s = Sort(**{**s.__dict__, "keep": True, "confident": True, "course_code": place["code"],
                    "session": place["session"], "type": place["type"],
                    "label": place["label"] or s.label, "assessment": "" if place["label"] else s.assessment})
        flags.append("placed_by_maintainer")

    if not s.keep:
        zh, en = SKIP_TEXT.get(s.skip_reason, SKIP_TEXT["other"])
        if s.confident:
            return done("skip", f"不收：{zh} | not accepted: {en}")
        return done("maybe_skip", f"可能误判，不收：{zh}；可用 /keep 捞回 | maybe wrongly skipped: {en}; /keep restores it")

    malformed = None
    if check is not None:
        if check.answers == "yes":
            return done("skip", "含答案，不收 | contains answers, not accepted")
        if check.marking_scheme == "yes":
            return done("skip", "评分标准，不收 | marking scheme, not accepted")
        if check.answers == "unsure":
            flags.append("answers_unsure")
        elif check.answers != "no":
            malformed = ("检查结果无法识别（答案） | unreadable check result (answers)")
        if check.marking_scheme != "no":
            malformed = ("检查结果无法识别（评分标准） | unreadable check result (marking scheme)")
        if check.personal_data not in ("no", "unsure", "yes"):
            malformed = ("检查结果无法识别（个人信息） | unreadable check result (personal data)")

    fcode = form.code if intake.CODE_RE.fullmatch(form.code or "") else ""
    code = session = typ = ""
    if place or (s.confident and s.course_code):
        code, typ = s.course_code, s.type
        session = s.session if place else resolve_session(s, form)
        if fcode and fcode != code:
            flags.append("hint_mismatch")
    elif fcode:
        code = fcode
        typ = form.type if form.type in intake.SUBS else s.type
        session = next((h for h in (form.session, form.taken) if intake.SESSION_RE.fullmatch(h or "")), "")
        session = session or (s.session if intake.SESSION_RE.fullmatch(s.session or "") else "unknown")
        flags.append("ai_unsure")
        if typ not in intake.SUBS:
            code = ""
    label = (s.assessment or s.label) if typ == "Past-Papers" else s.label
    name = sort.course_name if sort and code == sort.course_code else (form.name if code == fcode else "")
    placed = dict(code=code, name=name, session=session or "unknown", type=typ, label=label, set=s.set) if code else {}

    problem = None
    if check is None:
        problem = "没被检查 | not checked"
    elif malformed:
        problem = malformed
    elif check.personal_data == "unsure":
        problem = "不确定有没有个人信息 | unsure whether it holds personal data"
    elif check.personal_data == "yes":
        problem = "有个人信息，未处理 | holds personal data, not redacted"
    if problem:
        if not approved:
            zh, _, en = problem.partition(" | ")
            return done("review", f"需要你看：{zh} | needs a look: {en}", **placed)
        flags.append(f"approved_by:{approved}")

    if not code:
        return done("inbox", "课程不明，放入待整理 | course unknown, held in the inbox")
    return done("commit", "提交 | committed", **placed)
