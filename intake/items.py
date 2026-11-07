"""One record per accepted file: what the sorting and placement steps work on. No network, no Claude."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import intake

SCANNED_BELOW = 100          # a page with fewer characters of text counts as scanned
REPO_DIRS = ("EEE", "AIT", "ROBO", "GE")
OFFICE_EXTS = ("docx", "pptx", "xlsx", "doc", "ppt", "xls")
CONVERT_TIMEOUT = 120       # seconds for one LibreOffice conversion


@dataclass
class Item:
    k: int                   # 1-based, in accepted order
    source: str              # attachment name, or "<zip name> › <n>" for a zip member (never the member's own name)
    path: Path
    sha: str                 # sha256 hex of the bytes
    ext: str
    pages: int               # PDF page count; 1 for other files; 0 for a PDF that cannot be opened
    scanned: bool            # most pages (non-PDF: the whole file) have under SCANNED_BELOW characters
    page_text: list[str]     # every page's text (Office/text: one entry)
    view: Path | None = None  # the PDF the AI reads: the file itself for a PDF, the converted copy for Office, else None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read(path: Path, ext: str) -> tuple[int, list[str]]:
    """(pages, page_text); a PDF PyMuPDF cannot open gives (0, [])."""
    if ext == "pdf":
        try:
            import fitz
            with fitz.open(path) as doc:
                text = [page.get_text() for page in doc]
            return len(text), text
        except Exception:
            return 0, []
    try:
        return 1, [intake._plain_text(path)]
    except Exception:
        return 1, [""]


def to_pdf(path: Path, out_dir: Path, soffice: str | list[str] | None = None) -> Path | None:
    """Convert an Office file to PDF with LibreOffice; the original is only read. `soffice` is the executable, or an
    argv prefix (a list, handy for tests); default: soffice / libreoffice on PATH. None when LibreOffice is missing,
    fails or times out. Never raises and never prints the file name. The copy goes in a fresh subfolder of out_dir."""
    try:
        if soffice is None:
            soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if not soffice:
            return None
        cmd = [soffice] if isinstance(soffice, str) else list(soffice)
        out_dir = Path(out_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        sub = Path(tempfile.mkdtemp(dir=out_dir))
        r = subprocess.run(cmd + ["--headless", "--convert-to", "pdf", "--outdir", str(sub), str(Path(path).resolve())],
                           timeout=CONVERT_TIMEOUT, capture_output=True)
        pdf = sub / f"{path.stem}.pdf"
        return pdf if r.returncode == 0 and pdf.exists() else None
    except Exception:
        return None


def _is_scanned(page_text: list[str]) -> bool:
    if not page_text:
        return True
    return sum(len(t.strip()) < SCANNED_BELOW for t in page_text) * 2 > len(page_text)


def make_items(accepted: list[tuple[str, Path]], origins: list[str], soffice: str | list[str] | None = None,
               work: Path | None = None) -> list[Item]:
    """`origins[i]` comes from `intake.unpack`: the attachment name, or already "<zip> › <n>" for a zip member.
    A bare .zip name (not from unpack) gets its members numbered in order.
    PDFs are their own `view`; Office files are converted to PDF in `work` (default `<file folder>/_view`) and `pages`,
    `page_text`, `scanned` then come from that PDF. If conversion fails, `view` is None and the Office text is used."""
    out: list[Item] = []
    members: dict[str, int] = {}
    for k, ((name, path), origin) in enumerate(zip(accepted, origins), 1):
        if intake.ORIGIN_SEP in origin or intake._split_ext(origin)[1] != "zip":
            source = origin
        else:
            members[origin] = members.get(origin, 0) + 1
            source = f"{origin}{intake.ORIGIN_SEP}{members[origin]}"
        ext = intake._split_ext(path.name)[1]
        view = path if ext == "pdf" else None
        if ext in OFFICE_EXTS:
            view = to_pdf(path, work or path.parent / "_view", soffice)
        pages, text = _read(view or path, "pdf" if view else ext)
        if ext in OFFICE_EXTS and view and pages == 0:   # converter said fine but the PDF is unreadable
            view = None
            pages, text = _read(path, ext)
        out.append(Item(k, source, path, _sha256(path), ext, pages, _is_scanned(text), text, view))
    return out


def exact_duplicates(items: list[Item], root: Path) -> dict[int, str]:
    """k -> repo-relative path of a byte-identical file under EEE/ AIT/ ROBO/ GE/, else "#<k>" of the first earlier
    item with the same bytes. The repo wins when both apply. Repo files are hashed only when their size matches an item."""
    sizes = {i.path.stat().st_size for i in items}
    by_sha: dict[str, str] = {}
    for d in REPO_DIRS:
        for dirpath, _, files in os.walk(root / d):
            for f in sorted(files):
                p = Path(dirpath) / f
                try:
                    if p.stat().st_size in sizes:
                        by_sha.setdefault(_sha256(p), p.relative_to(root).as_posix())
                except OSError:
                    continue
    found: dict[int, str] = {}
    first: dict[str, int] = {}
    for i in items:
        if i.sha in by_sha:
            found[i.k] = by_sha[i.sha]
        elif i.sha in first:
            found[i.k] = f"#{first[i.sha]}"
        first.setdefault(i.sha, i.k)
    return found
