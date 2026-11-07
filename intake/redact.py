"""Black out personal data in a PDF (spec §5 steps 3–4): the full check's redactions become PyMuPDF redaction
annotations, applied so that the text, line art and image pixels underneath are removed, not just covered; then the
metadata, XMP and embedded files go. Every page's text is read again afterwards and every blacked-out string must be
gone. Problems name pages or redaction numbers, never the text; the rectangles kept for the cache hold no text."""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

WIDEN = 0.02        # each side of a box grows by this share of the displayed page's width / height
MIN_WORD = 3        # the word fallback searches the words of at least this many characters
BLACK = (0, 0, 0)

LIST_BAD = "打码列表格式不对 | the redaction list is malformed"
ENTRY_BAD = "第 {i} 条打码格式不对 | redaction #{i} is malformed"
CACHED_BAD = "第 {i} 个缓存的打码矩形格式不对 | cached redaction #{i} is malformed"
NOT_FOUND = "第 {p} 页找不到要涂掉的文字 | page {p}: the text to black out was not found"
STILL = "第 {p} 页仍能抽到被涂掉的文字 | page {p} still contains a redacted string"
UNREADABLE = "PDF 打不开 | the PDF could not be opened"
SAME_FILE = "打码结果不能覆盖原文件 | the redacted copy may not overwrite the original"
METADATA = "元数据未能清除 | the metadata could not be cleared"
FAILED = "打码出错 | redaction failed ({})"


@dataclass
class Redacted:
    """`out` is the redacted copy: written whenever the redactions could be applied, even when `ok` is False (a
    maintainer's /approve commits the redacted version, spec §7); None when nothing was written. `rects` are the
    rectangles applied, [{"page": n, "rect": [x0, y0, x1, y1]}] in unrotated page coordinates (what the cache keeps).
    `box_pages` are the pages with box redactions (with cached rectangles: every redacted page). `problems` name pages or
    redaction numbers only."""
    ok: bool
    out: Path | None
    rects: list[dict] = field(default_factory=list)
    box_pages: list[int] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _num(v) -> bool:
    return type(v) in (int, float) and math.isfinite(v)


def _rect4(v) -> bool:
    """Four finite numbers x0 < x1, y0 < y1."""
    return isinstance(v, (list, tuple)) and len(v) == 4 and all(_num(x) for x in v) and v[0] < v[2] and v[1] < v[3]


def _valid(r, n: int) -> bool:
    """A redaction from the check: page an int in 1..n; kind "text" with a non-blank string, or kind "box" with four
    numbers that cover part of the 0–1000 page."""
    if not isinstance(r, dict) or type(r.get("page")) is not int or not 1 <= r["page"] <= n:
        return False
    if r.get("kind") == "text":
        return isinstance(r.get("text"), str) and bool(_squash(r["text"]))
    if r.get("kind") == "box":
        b = r.get("box")
        return _rect4(b) and max(b[0], 0) < min(b[2], 1000) and max(b[1], 0) < min(b[3], 1000)
    return False


def _box_rect(page, box):
    """A 0–1000 box on the page as displayed (rotation applied: what the model saw), widened by WIDEN of the displayed
    width and height on each side, clamped to the page, in unrotated page coordinates (what redaction annotations take)."""
    import fitz
    w, h = page.rect.width, page.rect.height
    x0, y0, x1, y1 = box
    r = fitz.Rect(x0 / 1000 * w - WIDEN * w, y0 / 1000 * h - WIDEN * h,
                  x1 / 1000 * w + WIDEN * w, y1 / 1000 * h + WIDEN * h) & page.rect
    return r * page.derotation_matrix


def _outward(r) -> list[float]:
    """The rectangle rounded outwards to 0.01 pt, so the cached copy covers at least as much."""
    return [math.floor(r.x0 * 100) / 100, math.floor(r.y0 * 100) / 100,
            math.ceil(r.x1 * 100) / 100, math.ceil(r.y1 * 100) / 100]


def _leaks(doc, needles: list[tuple[str, bool]]) -> list[int]:
    """1-based pages whose text still contains one of `needles` [(text, fold)], compared with all whitespace removed
    on both sides (so a string broken over lines or spaced out still counts), and case-insensitively when `fold`."""
    pages = []
    want = [(_squash(t).casefold() if fold else _squash(t), fold) for t, fold in needles if _squash(t)]
    for i, page in enumerate(doc, 1):
        hay = _squash(page.get_text())
        low = hay.casefold()
        if any(n in (low if fold else hay) for n, fold in want):
            pages.append(i)
    return pages


def text_gone(pdf: Path, redactions: list[dict]) -> bool:
    """True when no text redaction's string can be read on ANY page of `pdf` (not only the page it names): whitespace
    removed on both sides, case-insensitive. False for an unreadable PDF or a text redaction without a string."""
    import fitz
    needles = []
    for r in redactions:
        if isinstance(r, dict) and r.get("kind") == "text":
            if not isinstance(r.get("text"), str) or not _squash(r["text"]):
                return False
            needles.append((r["text"], True))
    try:
        with fitz.open(pdf) as doc:
            return not _leaks(doc, needles)
    except Exception:
        return False


def _cached_marks(cached, n: int):
    """[(page, Rect)] from cached rectangles, or the problems when any is malformed."""
    import fitz
    if not isinstance(cached, list):
        return None, [LIST_BAD]
    bad = [i for i, c in enumerate(cached, 1)
           if not (isinstance(c, dict) and type(c.get("page")) is int and 1 <= c["page"] <= n and _rect4(c.get("rect")))]
    if bad:
        return None, [CACHED_BAD.format(i=i) for i in bad]
    return [(c["page"], fitz.Rect(c["rect"])) for c in cached], []


def _plan(doc, redactions):
    """(marks [(page, Rect)], box pages, needles for the text check, problems) for the check's redactions. Text: every
    hit of the whitespace-normalised string on its page (MuPDF's search ignores case and follows a string over line
    breaks); when there is none, every hit of each of its words of MIN_WORD+ characters, and the target fails when it
    has no such word or one is not found. Boxes: see _box_rect."""
    marks, boxes, needles, problems = [], set(), [], []
    for r in redactions:
        page = doc[r["page"] - 1]
        if r["kind"] == "box":
            marks.append((r["page"], _box_rect(page, r["box"])))
            boxes.add(r["page"])
            continue
        needle = _norm(r["text"])
        needles.append((needle, True))
        hits = page.search_for(needle)
        if not hits:
            words = list(dict.fromkeys(w for w in needle.split(" ") if len(w) >= MIN_WORD))
            found = [page.search_for(w) for w in words]
            needles += [(w, False) for w in words]
            hits = [h for f in found for h in f]
            if not words or not all(found):
                problems.append(NOT_FOUND.format(p=r["page"]))
        marks += [(r["page"], h) for h in hits]
    return marks, sorted(boxes), needles, problems


def apply(src: Path, out: Path, redactions: list[dict], cached_rects: list[dict] | None = None) -> Redacted:
    """Black out `redactions` (the full check's, pages from 1) in a copy of `src` written to `out`; `src` is only read.
    With `cached_rects` (a rebuild), exactly those rectangles and nothing else: `redactions` are ignored and the text
    check is skipped (there is no text to look for). Any malformed entry fails closed before anything is written.
    `out` must end in .pdf (clear_metadata goes by the extension). Never raises for bad input."""
    import fitz
    src, out = Path(src), Path(out)
    try:
        if out.resolve() == src.resolve() or (out.exists() and src.exists() and os.path.samefile(out, src)):
            return Redacted(False, None, problems=[SAME_FILE])
    except OSError:
        return Redacted(False, None, problems=[SAME_FILE])
    try:
        doc = fitz.open(src)
    except Exception:
        return Redacted(False, None, problems=[UNREADABLE])
    try:
        if not doc.is_pdf or doc.needs_pass or doc.page_count < 1:
            return Redacted(False, None, problems=[UNREADABLE])
        return _apply(doc, out, redactions, cached_rects)
    except Exception as e:                          # never print e: it may quote the file
        out.unlink(missing_ok=True)
        return Redacted(False, None, problems=[FAILED.format(type(e).__name__)])
    finally:
        doc.close()


def _apply(doc, out: Path, redactions, cached_rects) -> Redacted:
    import fitz
    import intake
    n = doc.page_count
    if cached_rects is not None:
        marks, problems = _cached_marks(cached_rects, n)
        if marks is None:
            return Redacted(False, None, problems=problems)
        rects = [{"page": p, "rect": [float(v) for v in r]} for p, r in marks]
        box_pages, needles = sorted({p for p, _ in marks}), None
    else:
        if not isinstance(redactions, list):
            return Redacted(False, None, problems=[LIST_BAD])
        bad = [i for i, r in enumerate(redactions, 1) if not _valid(r, n)]
        if bad:
            return Redacted(False, None, problems=[ENTRY_BAD.format(i=i) for i in bad])
        found, box_pages, needles, problems = _plan(doc, redactions)
        rects = [{"page": p, "rect": _outward(r)} for p, r in found]
        marks = [(x["page"], fitz.Rect(x["rect"])) for x in rects]
    for pno in sorted({p for p, _ in marks}):
        page = doc[pno - 1]
        rot = page.rotation
        if rot:     # on a rotated page PyMuPDF draws the black fill ignoring a crop box offset: apply it unrotated
            page.set_rotation(0)
        for p, r in marks:
            if p == pno:
                page.add_redact_annot(r, fill=BLACK)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)   # line art and text: removed (the defaults)
        if rot:
            page.set_rotation(rot)
    for name in doc.embfile_names():
        doc.embfile_del(name)
    doc.set_metadata({})
    doc.del_xml_metadata()
    doc.save(out, garbage=4, deflate=True)
    if intake.clear_metadata(out) != "cleared":
        out.unlink(missing_ok=True)
        return Redacted(False, None, problems=[METADATA])
    if needles:
        with fitz.open(out) as done:
            problems += [STILL.format(p=p) for p in _leaks(done, needles)]
    return Redacted(not problems, out, rects, box_pages, list(dict.fromkeys(problems)))


def render(pdf: Path, pages: list[int], dpi: int = 150) -> list[bytes]:
    """PNGs of `pages` (from 1) as displayed: rotation applied, annotations drawn. ValueError for a page out of range."""
    import fitz
    with fitz.open(pdf) as doc:
        if any(type(p) is not int or not 1 <= p <= doc.page_count for p in pages):
            raise ValueError("page out of range")
        return [doc[p - 1].get_pixmap(dpi=dpi).tobytes("png") for p in pages]
