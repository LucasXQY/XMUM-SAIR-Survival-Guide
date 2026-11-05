"""Generate the static website from this repository.

用法 / Usage:  python site/build.py [--out _site] [--prefix /XMUM-SAIR-Survival-Guide/]

扫描 EEE/ AIT/ ROBO/ 下的课程文件夹，渲染仓库里的 markdown，生成 HTML 和搜索索引到
_site/，最后对生成结果做自检。设计说明见 site/DESIGN.md。

Scans the course folders under EEE/ AIT/ ROBO/, renders the repo's markdown,
writes HTML plus a search index to _site/ and checks its own output.
See site/DESIGN.md for the design.
"""
from __future__ import annotations

import html as html_mod
import os
import posixpath
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import markdown

REPO = "LucasXQY/XMUM-SAIR-Survival-Guide"
GH = f"https://github.com/{REPO}"
RAW = f"https://raw.githubusercontent.com/{REPO}/main"
PROGS = {
    "EEE": "电子信息工程 | Electrical & Electronic Engineering",
    "AIT": "人工智能 | Artificial Intelligence",
    "ROBO": "机器人与自动化工程 | Robotics & Automation Engineering",
}
SUBS = ("Past-Papers", "Syllabus", "Assignments", "Labs", "Tutorials",
        "Handbooks", "Notes", "Exam-Review", "Tips")
SESSION_RE = re.compile(r"\d{4}-\d{2}")
# timeline rows "| 2022-04 | [COM107](folder/) | ..." — same regex as scripts/update_index.py
TAKEN_RE = re.compile(r"^\| (\d{4}-\d{2}) \| \[?([^\]|]+?)\]?(?:\([^)]*\))? \|")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")


@dataclass
class File:
    prog: str
    code: str
    course: str
    session: str
    type: str
    name: str
    path: str   # repo-relative posix path
    size: int


@dataclass
class Course:
    prog: str
    dir: str
    code: str
    name: str
    path: str   # "EEE/COM107_Circuits_and_Devices"
    readme: str | None
    sessions: dict[str, dict[str, list[File]]] = field(default_factory=dict)
    taken_in: list[str] = field(default_factory=list)
    lecturers: dict[str, str] = field(default_factory=dict)


def warn(msg: str) -> None:
    print(f"WARNING: {msg}", file=sys.stderr)


def parse_taken(readme_text: str) -> dict[str, list[str]]:
    taught: dict[str, list[str]] = {}
    for line in readme_text.splitlines():
        m = TAKEN_RE.match(line)
        if m:
            sess, code = m.groups()
            sessions = taught.setdefault(code.strip(), [])
            if sess not in sessions:
                sessions.append(sess)
    return {code: sorted(s) for code, s in taught.items()}


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_lecturers(readme_text: str) -> dict[str, str]:
    """Session → lecturer from the first table (session cell may be a link)."""
    rows = []
    for line in readme_text.splitlines():
        if line.lstrip().startswith("|"):
            rows.append(line)
        elif rows:
            break
    out: dict[str, str] = {}
    for line in rows[2:]:   # skip header and separator
        cells = _cells(line)
        if len(cells) < 2:
            continue
        session = LINK_RE.sub(r"\1", cells[0]).strip()
        if (SESSION_RE.fullmatch(session) or session == "unknown") and cells[1]:
            out[session] = cells[1]
    return out


def _session_key(s: str) -> tuple[int, str]:
    """Sort key so that reverse=True gives newest first and 'unknown' last."""
    return (-1, "") if s == "unknown" else (0, s)


def scan(root: Path) -> list[Course]:
    courses: list[Course] = []
    for prog in PROGS:
        pdir = root / prog
        if not pdir.is_dir():
            continue
        preadme = pdir / "README.md"
        taken = parse_taken(preadme.read_text(encoding="utf-8")) if preadme.is_file() else {}
        for d in sorted(os.listdir(pdir)):
            cdir = pdir / d
            if not cdir.is_dir() or "_" not in d:
                continue
            code, name = d.split("_", 1)
            rpath = cdir / "README.md"
            readme = rpath.read_text(encoding="utf-8") if rpath.is_file() else None
            course = Course(prog, d, code, name.replace("_", " "), f"{prog}/{d}", readme,
                            taken_in=taken.get(code, []),
                            lecturers=parse_lecturers(readme) if readme else {})
            sessions = [s for s in os.listdir(cdir) if (cdir / s).is_dir()
                        and (SESSION_RE.fullmatch(s) or s == "unknown")]
            for sess in sorted(sessions, key=_session_key, reverse=True):
                types: dict[str, list[File]] = {}
                for sub in SUBS:
                    sdir = cdir / sess / sub
                    if not sdir.is_dir():
                        continue
                    files = [File(prog, code, course.name, sess, sub, f,
                                  f"{course.path}/{sess}/{sub}/{f}", (sdir / f).stat().st_size)
                             for f in sorted(os.listdir(sdir))
                             if not f.startswith(".") and (sdir / f).is_file()]
                    if files:
                        types[sub] = files
                if types:
                    course.sessions[sess] = types
            courses.append(course)
    return courses


def all_files(courses: list[Course]) -> list[File]:
    return [f for c in courses for types in c.sessions.values() for files in types.values() for f in files]


# ---------------------------------------------------------------- rendering

# repo markdown → site page (directory with index.html)
ROOT_PAGES = {
    "README.md": "about/",
    "DISCLAIMER.md": "disclaimer/",
    "CONTRIBUTING.md": "contributing/",
    "CONTRIBUTORS.md": "contributors/",
    "Lecturers.md": "lecturers/",
    "Research-Opportunities.md": "research/",
}


class Site:
    def __init__(self, root: Path, prefix: str):
        self.root = Path(root)
        self.prefix = prefix
        self.courses = scan(self.root)
        self.by_path = {c.path: c for c in self.courses}


def url_path(path: str) -> str:
    return quote(path, safe="/")


def slugify(text: str, sep: str) -> str:
    """GitHub-style heading id: lowercase, drop punctuation, spaces → sep (repeats kept)."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return text.strip().replace(" ", sep)


def rewrite_link(site: Site, href: str, src_md: str) -> str:
    """Turn a relative link inside repo markdown into a site URL or a GitHub URL."""
    if href.startswith(("http://", "https://", "mailto:", "#")):
        return href
    path, _, frag = href.partition("#")
    frag = f"#{frag}" if frag else ""
    p = posixpath.normpath(posixpath.join(posixpath.dirname(src_md), path)).strip("/")
    if p in ROOT_PAGES:
        return site.prefix + ROOT_PAGES[p] + frag
    parts = p.split("/")
    if len(parts) == 2 and parts[0] in PROGS and parts[1] == "README.md":
        return f"{site.prefix}{parts[0]}/{frag}"
    course = site.by_path.get("/".join(parts[:2]))
    if course:
        rest = parts[2:]
        if not rest or rest == ["README.md"]:
            return f"{site.prefix}{course.path}/{frag}"
        if len(rest) <= 2 and (SESSION_RE.fullmatch(rest[0]) or rest[0] == "unknown"):
            return f"{site.prefix}{course.path}/#{rest[0]}"
    full = site.root / p
    if full.is_dir():
        return f"{GH}/tree/main/{url_path(p)}"
    if not full.is_file():
        warn(f"{src_md}: link to missing {p}")
    return f"{GH}/blob/main/{url_path(p)}"


def render_md(site: Site, text: str, src_md: str) -> str:
    out = markdown.markdown(text, extensions=["tables", "fenced_code", "toc"],
                            extension_configs={"toc": {"slugify": slugify}})

    def fix(m: re.Match) -> str:
        href = rewrite_link(site, html_mod.unescape(m.group(1)), src_md)
        return f'href="{html_mod.escape(href, quote=True)}"'

    return re.sub(r'href="([^"]*)"', fix, out)
