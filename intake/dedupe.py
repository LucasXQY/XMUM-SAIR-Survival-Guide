"""Near-duplicates (spec section 5, step 5): first-page text similarity against the PDFs already in the course folder.
No network, no Claude; the pair comparison itself lives in ai.compare_pair."""
from __future__ import annotations

import difflib
import re
from pathlib import Path

import ai   # for the PyMuPDF lock (ai._FITZ), shared with every other fitz user

SAME_AT = 0.9
ASK_AT = 0.6
_WORD = re.compile(r"[a-z0-9]{2,}|[一-鿿]")


def normalise(text: str) -> list[str]:
    """Lower-case words of 2+ letters or digits; each Han character is a token of its own."""
    return _WORD.findall(str(text or "").lower())


def similarity(a: str, b: str) -> float:
    wa, wb = normalise(a), normalise(b)
    if not wa or not wb:
        return 0.0
    return difflib.SequenceMatcher(None, wa, wb, autojunk=False).ratio()


def classify(score: float) -> str:
    return "same" if score >= SAME_AT else "ask" if score >= ASK_AT else "different"


def first_page_text(path: Path) -> str | None:
    """Text of the first page of a PDF, None when it cannot be read."""
    try:
        import fitz
        with ai._FITZ, fitz.open(path) as doc:
            return doc[0].get_text() if len(doc) else None
    except Exception:
        return None


def candidates(item, course_dir: Path | None, root: Path | None = None, cache: dict | None = None) -> list[tuple[str, float]]:
    """[(repo-relative posix path, score)] of PDFs under course_dir whose first page scores >= ASK_AT against the item's,
    best first. `cache` (path -> first-page text or None) is filled and reused, so a run reads each repo PDF once. Safe to
    call from worker threads: PDFs are opened under ai._FITZ. Scanned items, items without page text and a missing folder give []. Unreadable PDFs are skipped."""
    if course_dir is None or item.scanned or not item.page_text or not Path(course_dir).is_dir():
        return []
    mine = item.page_text[0]
    if not normalise(mine):
        return []
    course_dir = Path(course_dir)
    root = Path(root) if root is not None else course_dir.parent.parent
    out = []
    for p in sorted(course_dir.rglob("*")):
        if not p.is_file() or p.suffix.lower() != ".pdf":
            continue
        key = str(p)
        if cache is not None and key in cache:
            text = cache[key]
        else:
            text = first_page_text(p)
            if cache is not None:
                cache[key] = text
        if text is None:
            continue
        score = similarity(mine, text)
        if score >= ASK_AT:
            try:
                rel = p.relative_to(root).as_posix()
            except ValueError:
                rel = p.as_posix()
            out.append((rel, score))
    return sorted(out, key=lambda t: (-t[1], t[0]))


def _when(session: str) -> str:
    return str(session).replace("-", "")


def _names(course_dir: Path):
    if course_dir is None or not Path(course_dir).is_dir():
        return []
    return [p.name for p in Path(course_dir).rglob("*") if p.is_file()]


def next_set(course_dir: Path, code: str, session: str, label: str) -> str:
    """Next free set letter for the assessment: the file without a set counts as A, so the first new one is B."""
    pat = re.compile(rf"^{re.escape(code)}_{re.escape(_when(session))}_{re.escape(label)}_Set([A-Za-z0-9]+)_Question\.", re.I)
    taken = {"A"}
    for n in _names(course_dir):
        m = pat.match(n)
        if m:
            taken.add(m.group(1).upper())
    for c in "BCDEFGHIJKLMNOPQRSTUVWXYZ":
        if c not in taken:
            return c
    return "Z"


def next_version(course_dir: Path, code: str, session: str, label: str) -> int:
    """Next free _v<N> for the document; none yet gives 2."""
    pat = re.compile(rf"^{re.escape(code)}_{re.escape(_when(session))}_{re.escape(label)}_v(\d+)(?:_Question)?(?:_\d+)?\.", re.I)
    used = [int(m.group(1)) for m in map(pat.match, _names(course_dir)) if m]
    return max(used + [1]) + 1
