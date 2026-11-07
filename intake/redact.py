"""Black out personal data in a PDF (spec §5 steps 3–4): the full check's redactions become PyMuPDF redaction
annotations, applied so that the text, image pixels and any line art they touch are removed, not just covered. Every
annotation and form field on a redacted page goes first (a field's value would survive under the black box), and the
outline, page labels, page thumbnails and piece info, metadata, XMP and embedded files go from the whole file. Every
page is read again afterwards: every blacked-out string, and every word the word fallback blacked out, must be gone.
Problems name pages or redaction numbers, never the text; the rectangles kept for the cache hold no text."""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

WIDEN = 0.02        # each side of a box grows by this share of the displayed page's width / height
MIN_WORD = 3        # the word fallback searches the words of at least this many characters
BLACK = (0, 0, 0)
PAGE_KEYS = ("PieceInfo", "Metadata", "Thumb")      # removed from every page
_REF = re.compile(r"(\d+)\s+\d+\s+R")
_EDGE = re.compile(r"^\W+|\W+$")
_HYPHEN_BREAK = re.compile(r"-[ \t]*\n\s*")

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
    maintainer's /approve commits the redacted version, spec §7); None when nothing was written (and then no file is
    left at `out`, not even one from an earlier run). `rects` are the rectangles applied, [{"page": n, "rect": [x0, y0,
    x1, y1]}] in unrotated page coordinates (what the cache keeps). `box_pages` are the pages with box redactions (with
    cached rectangles: every redacted page). `problems` name pages or redaction numbers only."""
    ok: bool
    out: Path | None
    rects: list[dict] = field(default_factory=list)
    box_pages: list[int] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _words(s: str) -> list[str]:
    """Whitespace-separated words with leading and trailing punctuation trimmed."""
    return [w for w in (_EDGE.sub("", x) for x in s.split()) if w]


def _long_words(s: str) -> list[str]:
    return list(dict.fromkeys(w for w in _words(s) if len(w) >= MIN_WORD))


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


def _readable(page) -> list[str]:
    """What a reader can get out of a page: its text (widget and free-text appearances included), plus every
    annotation's contents, author and subject and every form field's value."""
    out = [page.get_text()]
    for a in page.annots():
        out += [str(a.info.get(k) or "") for k in ("content", "title", "subject")]
    for w in page.widgets():
        out.append(str(w.field_value or ""))
    return out


def _left(doc, redactions: list[dict], fallback_words=()) -> list[int]:
    """1-based pages of `doc` on which a text redaction's string can still be read anywhere, compared with all
    whitespace removed on both sides (so a string broken over lines or spaced out counts, and again with hyphenated
    line breaks joined) and ignoring case; or one of `fallback_words` (the words the word fallback blacked out, in any
    case, as it does) as a whole word: equal to a page word (get_text("words")) or an annotation or field word, edge
    punctuation trimmed, ignoring case ("important" is not "tan"). Single words of strings found whole are not
    checked: a lecturer "Dr Tan" must not fail a student "Tan Ah Kow"."""
    texts = [r["text"] for r in redactions if r.get("kind") == "text"]
    strings = [s for s in (_squash(t).casefold() for t in texts) if s]
    words = {w.casefold() for x in fallback_words for w in _words(x)}
    pages = []
    for i, page in enumerate(doc, 1):
        found = _readable(page)
        hay = [_squash(t).casefold() for t in found] + [_squash(_HYPHEN_BREAK.sub("", t)).casefold() for t in found]
        on_page = set()
        if words:
            on_page = {_EDGE.sub("", x[4]).casefold() for x in page.get_text("words")}
            on_page |= {w.casefold() for t in found[1:] for w in _words(t)}
        if any(s in h for s in strings for h in hay) or words & on_page:
            pages.append(i)
    return pages


def text_gone(pdf: Path, redactions: list[dict], fallback_words: list[str] | None = None) -> bool:
    """True when no text redaction's string, nor any of `fallback_words` (the words apply's word fallback used), can
    be read on ANY page of `pdf` (not only the page it names; see _left). False for an unreadable PDF, a `redactions`
    that is not a list, any malformed entry (the same rules as apply), or `fallback_words` that is not a list of
    non-blank strings."""
    import fitz
    words = [] if fallback_words is None else fallback_words
    if not isinstance(redactions, list) or not isinstance(words, (list, tuple)) \
            or not all(isinstance(w, str) and _words(w) for w in words):
        return False
    try:
        with fitz.open(pdf) as doc:
            if not all(_valid(r, doc.page_count) for r in redactions):
                return False
            return not _left(doc, redactions, words)
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
    """(marks [(page, Rect)], box pages, words the fallback used, problems) for the check's redactions. Text: every
    hit of the whitespace-normalised string on its page (MuPDF's search ignores case and follows a string over line
    breaks); when there is none, every page word equal (ignoring case and edge punctuation) to one of its words of
    MIN_WORD+ characters, and the target fails when it has no such word or one is not on the page. Boxes: see
    _box_rect."""
    import fitz
    marks, boxes, used, problems = [], set(), [], []
    for r in redactions:
        page = doc[r["page"] - 1]
        if r["kind"] == "box":
            marks.append((r["page"], _box_rect(page, r["box"])))
            boxes.add(r["page"])
            continue
        needle = _norm(r["text"])
        hits = page.search_for(needle)
        if not hits:
            words = _long_words(needle)
            used += words
            on_page = [(fitz.Rect(x[:4]), _EDGE.sub("", x[4]).casefold()) for x in page.get_text("words")]
            found = [[rect for rect, pw in on_page if pw == w.casefold()] for w in words]
            hits = [h for f in found for h in f]
            if not words or not all(found):
                problems.append(NOT_FOUND.format(p=r["page"]))
        marks += [(r["page"], h) for h in hits]
    return marks, sorted(boxes), list(dict.fromkeys(used)), problems


def _top_refs(array: str) -> list[int]:
    """Object numbers referenced by the top-level entries of a PDF array "[...]". What sits inside a direct dict,
    a nested array or a string entry (an annotation's /P, /Popup, /Parent, /AP ...) is never followed."""
    body = array.strip()
    if not (body.startswith("[") and body.endswith("]")):
        return []
    body, flat, depth, i = body[1:-1], [], 0, 0
    while i < len(body):
        c = body[i]
        if c == "(":                                            # a literal string: balanced, with escapes
            n, i = 1, i + 1
            while i < len(body) and n:
                n += {"(": 1, ")": -1}.get(body[i], 0)
                i += 2 if body[i] == "\\" else 1
            flat.append(" ")
        elif body.startswith("<<", i) or body.startswith(">>", i):
            depth += 1 if c == "<" else -1
            flat.append(" ")
            i += 2
        elif c == "<":                                          # a hex string
            j = body.find(">", i)
            flat.append(" ")
            i = len(body) if j < 0 else j + 1
        elif c in "[]":
            depth += 1 if c == "[" else -1
            flat.append(" ")
            i += 1
        else:
            flat.append(c if depth == 0 else " ")
            i += 1
    return [int(m) for m in _REF.findall("".join(flat))]


def _refs(doc, got) -> list[int]:
    """Object numbers in an array from xref_get_key (top-level entries only, see _top_refs): a direct array, or a
    reference to an array (or to one object)."""
    kind, val = got
    if kind == "xref":
        x = int(val.split()[0])
        obj = doc.xref_object(x) if 0 < x < doc.xref_length() else ""
        return _top_refs(obj) if obj.lstrip().startswith("[") else [x]
    return _top_refs(val) if kind == "array" else []


def _page_tree(doc) -> set[int]:
    """The catalog, every page and every node of the page tree: never emptied, whatever a broken file lists."""
    cat = doc.pdf_catalog()
    out, todo = {cat}, _refs(doc, doc.xref_get_key(cat, "Pages"))
    while todo:
        x = todo.pop()
        if x not in out and 0 < x < doc.xref_length():
            out.add(x)
            todo += _refs(doc, doc.xref_get_key(x, "Kids"))
    return out | {doc.page_xref(i) for i in range(doc.page_count)}


def _ours(doc, x: int, keep_out: set[int]) -> bool:
    """Is object x an annotation or a form field (the only objects ever emptied)? Not the page tree, not a stream,
    not anything typed other than /Annot (a font, an image ...)."""
    if x in keep_out or not 0 < x < doc.xref_length() or doc.xref_is_stream(x):
        return False
    if doc.xref_get_key(x, "Type")[1] not in ("null", "/Annot"):
        return False
    return bool(set(doc.xref_get_keys(x)) & {"Subtype", "FT", "T", "Kids", "Parent", "V"})


def _blank(doc, x: int) -> None:
    """Empty object x, so that nothing it held survives even if something still points at it."""
    doc.update_object(x, "<<>>")


def _drop_annots(doc, page, keep_out: set[int]) -> None:
    """Every annotation of the page (widgets, links, notes, ink, pop-ups ...) off the page, and every one that is an
    object of its own emptied. Direct annotation dicts go with the /Annots array; refs inside them are not followed."""
    got = doc.xref_get_key(page.xref, "Annots")
    if got[0] == "null":
        return
    doc.xref_set_key(page.xref, "Annots", "null")
    for x in _refs(doc, got):
        if _ours(doc, x, keep_out):
            _blank(doc, x)


def _prune_form(doc) -> None:
    """Keep in /AcroForm only the fields that still have a widget on a page; empty the others (a parent field's value
    would otherwise survive garbage collection); no /AcroForm at all when none is left. /XFA (which can hold any
    field's data) and /CO always go, whether /AcroForm is a direct dict (as PyMuPDF writes it) or an object."""
    cat = doc.pdf_catalog()
    got = doc.xref_get_key(cat, "AcroForm")
    if got[0] == "null":
        return
    form, key = (int(got[1].split()[0]), "") if got[0] == "xref" else (cat, "AcroForm/")
    for k in ("XFA", "CO"):
        if doc.xref_get_key(form, key + k)[0] != "null":
            doc.xref_set_key(form, key + k, "null")
    keep_out = _page_tree(doc)
    live = {x for page in doc for x in _refs(doc, doc.xref_get_key(page.xref, "Annots"))
            if 0 < x < doc.xref_length() and doc.xref_get_key(x, "Subtype")[1] == "/Widget"}
    seen, dead = set(), []

    def keep(x: int) -> bool:
        if x in seen:
            return x in live
        seen.add(x)
        if not _ours(doc, x, keep_out):         # not a field: dropped from /Fields, never followed or emptied
            return False
        kids = _refs(doc, doc.xref_get_key(x, "Kids"))
        kept = [k for k in kids if keep(k)]
        if len(kept) != len(kids):
            doc.xref_set_key(x, "Kids", "[" + " ".join(f"{k} 0 R" for k in kept) + "]")
        if x in live or kept:
            return True
        dead.append(x)
        return False
    fields = [f for f in _refs(doc, doc.xref_get_key(cat, "AcroForm/Fields")) if keep(f)]
    for x in dead:
        _blank(doc, x)
    if not fields:
        doc.xref_set_key(cat, "AcroForm", "null")
        return
    doc.xref_set_key(form, key + "Fields", "[" + " ".join(f"{f} 0 R" for f in fields) + "]")


def _strip(doc) -> None:
    """What a redacted file never keeps: unused form fields, the outline, page labels, every page's piece info,
    metadata stream and thumbnail, embedded files, the info dictionary and the XMP metadata."""
    _prune_form(doc)
    doc.set_toc([])
    cat = doc.pdf_catalog()
    for k in ("PageLabels", "PieceInfo"):
        if doc.xref_get_key(cat, k)[0] != "null":
            doc.xref_set_key(cat, k, "null")
    for page in doc:
        for k in PAGE_KEYS:
            if doc.xref_get_key(page.xref, k)[0] != "null":
                doc.xref_set_key(page.xref, k, "null")
    for name in doc.embfile_names():
        doc.embfile_del(name)
    doc.set_metadata({})
    doc.del_xml_metadata()


def _remove(out: Path) -> None:
    try:
        out.unlink(missing_ok=True)
    except OSError:
        pass


def apply(src: Path, out: Path, redactions: list[dict], cached_rects: list[dict] | None = None) -> Redacted:
    """Black out `redactions` (the full check's, pages from 1) in a copy of `src` written to `out`; `src` is only read.
    With `cached_rects` (a rebuild), exactly those rectangles and nothing else: `redactions` are ignored and the text
    check is skipped (there is no text to look for). Any malformed entry fails closed before anything is written, and
    whenever nothing is written a file left at `out` by an earlier run is deleted. `out` must end in .pdf
    (clear_metadata goes by the extension). Never raises for bad input."""
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
        _remove(out)
        return Redacted(False, None, problems=[UNREADABLE])
    try:
        if not doc.is_pdf or doc.needs_pass or doc.page_count < 1:
            result = Redacted(False, None, problems=[UNREADABLE])
        else:
            result = _apply(doc, out, redactions, cached_rects)
    except Exception as e:                          # never print e: it may quote the file
        result = Redacted(False, None, problems=[FAILED.format(type(e).__name__)])
    finally:
        doc.close()
    if result.out is None:
        _remove(out)
    return result


def _apply(doc, out: Path, redactions, cached_rects) -> Redacted:
    import fitz
    import intake
    n = doc.page_count
    if cached_rects is not None:
        marks, problems = _cached_marks(cached_rects, n)
        if marks is None:
            return Redacted(False, None, problems=problems)
        rects = [{"page": p, "rect": [float(v) for v in r]} for p, r in marks]
        box_pages, fallback = sorted({p for p, _ in marks}), []
    else:
        if not isinstance(redactions, list):
            return Redacted(False, None, problems=[LIST_BAD])
        bad = [i for i, r in enumerate(redactions, 1) if not _valid(r, n)]
        if bad:
            return Redacted(False, None, problems=[ENTRY_BAD.format(i=i) for i in bad])
        found, box_pages, fallback, problems = _plan(doc, redactions)
        rects = [{"page": p, "rect": _outward(r)} for p, r in found]
        marks = [(x["page"], fitz.Rect(x["rect"])) for x in rects]
    keep_out = _page_tree(doc)
    for pno in sorted({p for p, _ in marks}):
        page = doc[pno - 1]
        rot = page.rotation
        if rot:     # on a rotated page PyMuPDF draws the black fill ignoring a crop box offset: apply it unrotated
            page.set_rotation(0)
        _drop_annots(doc, page, keep_out)
        page = doc.reload_page(page)
        for p, r in marks:
            if p == pno:
                page.add_redact_annot(r, fill=BLACK)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS,                   # text: removed (the default)
                              graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)  # a stroke only partly covered too
        if rot:
            page.set_rotation(rot)
    _strip(doc)
    doc.save(out, garbage=4, deflate=True)
    if intake.clear_metadata(out) != "cleared":
        return Redacted(False, None, problems=[METADATA])
    if cached_rects is None:
        with fitz.open(out) as done:
            problems += [STILL.format(p=p) for p in _left(done, redactions, fallback)]
    return Redacted(not problems, out, rects, box_pages, list(dict.fromkeys(problems)))


def render(pdf: Path, pages: list[int], dpi: int = 150) -> list[bytes]:
    """PNGs of `pages` (from 1) as displayed: rotation applied, annotations drawn. ValueError for a page out of range."""
    import fitz
    with fitz.open(pdf) as doc:
        if any(type(p) is not int or not 1 <= p <= doc.page_count for p in pages):
            raise ValueError("page out of range")
        return [doc[p - 1].get_pixmap(dpi=dpi).tobytes("png") for p in pages]
