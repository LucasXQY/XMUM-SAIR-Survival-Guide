"""Where each file ends up (spec section 6). Pure functions: no network, no files."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import intake

SKIP_REASONS = ("lecture_slides", "textbook", "answers", "marking_scheme", "student_work", "not_course_material", "other")
SKIP_TEXT = {
    "lecture_slides": "讲义 | lecture slides",
    "textbook": "课本 | textbook",
    "answers": "含答案 | contains answers",
    "marking_scheme": "评分标准 | marking scheme",
    "student_work": "学生作业 | student work",
    "not_course_material": "不是课程资料 | not course material",
    "other": "其他原因 | other reason",
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
    if not intake.CODE_RE.match(code):
        code, confident = "", False
    session = str(raw.get("session") or "").strip()
    if not intake.SESSION_RE.match(session):
        session = "unknown"
    typ = str(raw.get("type") or "").strip()
    if typ not in intake.SUBS:
        typ, confident = "", False
    reason = str(raw.get("skip_reason") or "").strip()
    keep = raw.get("keep") is not False
    if keep:
        reason = ""
    elif reason not in SKIP_REASONS:
        reason = "other"
    return Sort(course_code=code, course_name=str(raw.get("course_name") or "").strip()[:80], session=session,
                type=typ, label=_label(raw.get("label")), assessment=_label(raw.get("assessment")),
                set=_label(raw.get("set")), keep=keep, skip_reason=reason, confident=confident,
                note=str(raw.get("note") or "").strip()[:200])


def resolve_session(sort: Sort, form) -> str:
    if intake.SESSION_RE.match(sort.session or ""):
        return sort.session
    if sort.course_code and sort.course_code == form.code:
        for hint in (form.session, form.taken):
            if intake.SESSION_RE.match(hint or ""):
                return hint
    return "unknown"


def _strip_set(value: str) -> str:
    return re.sub(r"^set[_-]?", "", _label(value), flags=re.I)


def file_name(code, session, type, label, set, ext, taken: set[str]) -> str:
    when = session.replace("-", "") if intake.SESSION_RE.match(session or "") else "unknown"
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
    if not intake.CODE_RE.match(code) or typ not in intake.SUBS:
        return None
    if not intake.SESSION_RE.match(session):
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
        text = SKIP_TEXT.get(s.skip_reason, SKIP_TEXT["other"])
        if s.confident:
            return done("skip", f"不收：{text} | not accepted: {text}")
        return done("maybe_skip", f"可能误判，不收：{text}；可用 /keep 捞回 | maybe wrongly skipped: {text}; /keep restores it")

    if check is not None:
        if check.answers == "yes":
            return done("skip", "含答案，不收 | contains answers, not accepted")
        if check.marking_scheme == "yes":
            return done("skip", "评分标准，不收 | marking scheme, not accepted")
        if check.answers == "unsure":
            flags.append("answers_unsure")

    fcode = form.code if intake.CODE_RE.match(form.code or "") else ""
    code = session = typ = ""
    if place or (s.confident and s.course_code):
        code, typ = s.course_code, s.type
        session = s.session if place else resolve_session(s, form)
        if fcode and fcode != code:
            flags.append("hint_mismatch")
    elif fcode:
        code = fcode
        typ = form.type if form.type in intake.SUBS else s.type
        session = next((h for h in (form.session, form.taken) if intake.SESSION_RE.match(h or "")), "")
        session = session or (s.session if intake.SESSION_RE.match(s.session or "") else "unknown")
        flags.append("ai_unsure")
        if typ not in intake.SUBS:
            code = ""
    label = (s.assessment or s.label) if typ == "Past-Papers" else s.label
    placed = dict(code=code, name=s.course_name, session=session or "unknown", type=typ, label=label, set=s.set) if code else {}

    problem = None
    if check is None:
        problem = "没被检查 | not checked"
    elif check.personal_data == "unsure":
        problem = "不确定有没有个人信息 | unsure whether it holds personal data"
    elif check.personal_data == "yes":
        problem = "有个人信息，未处理 | holds personal data, not redacted"
    if problem:
        if not approved:
            return done("review", f"需要你看：{problem} | needs a look: {problem}", **placed)
        flags.append(f"approved_by:{approved}")

    if not code:
        return done("inbox", "课程不明，放入待整理 | course unknown, held in the inbox")
    return done("commit", "提交 | committed", **placed)
