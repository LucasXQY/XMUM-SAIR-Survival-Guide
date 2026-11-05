"""Generate the static website from this repository.

用法 / Usage:  python site/build.py [--out _site] [--prefix /XMUM-SAIR-Survival-Guide/]

扫描 EEE/ AIT/ ROBO/ 下的课程文件夹，渲染仓库里的 markdown，生成 HTML 和搜索索引到
_site/，最后对生成结果做自检。设计说明见 site/DESIGN.md。

Scans the course folders under EEE/ AIT/ ROBO/, renders the repo's markdown,
writes HTML plus a search index to _site/ and checks its own output.
See site/DESIGN.md for the design.
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from urllib.parse import quote, unquote

import markdown

REPO = "LucasXQY/XMUM-SAIR-Survival-Guide"
GH = f"https://github.com/{REPO}"
RAW = f"https://raw.githubusercontent.com/{REPO}/main"
SITE_URL = "https://lucasxqy.github.io/XMUM-SAIR-Survival-Guide/"   # canonical address; changes with REPO after the org move
DOWNLOADS = f"{GH}/releases/download/downloads"                      # per-session zips kept by .github/workflows/downloads.yml
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
    contributors: dict[str, str] = field(default_factory=dict)   # session → the README's 资料来自 cell


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
    return parse_column(readme_text, 1)


def parse_contributors(readme_text: str) -> dict[str, str]:
    """Session → the 资料来自 / Contributed by cell of the first table."""
    return parse_column(readme_text, 3)


def parse_column(readme_text: str, col: int) -> dict[str, str]:
    rows = []
    for line in readme_text.splitlines():
        if line.lstrip().startswith("|"):
            rows.append(line)
        elif rows:
            break
    out: dict[str, str] = {}
    for line in rows[2:]:   # skip header and separator
        cells = _cells(line)
        if len(cells) <= col:
            continue
        session = LINK_RE.sub(r"\1", cells[0]).strip()
        if (SESSION_RE.fullmatch(session) or session == "unknown") and cells[col]:
            out[session] = cells[col]
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
            if readme is None:
                warn(f"{prog}/{d}: README.md missing")
            course = Course(prog, d, code, name.replace("_", " "), f"{prog}/{d}", readme,
                            taken_in=taken.get(code, []),
                            lecturers=parse_lecturers(readme) if readme else {},
                            contributors=parse_contributors(readme) if readme else {})
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


# ---------------------------------------------------------------- lecturers, recent uploads, wanted list, sitemap

def lecturer_slug(name: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")


def split_lecturers(cell: str) -> list[str]:
    """A README cell may name several people: 'A, B' / 'A、B' / 'A & B'."""
    return [n.strip() for n in re.split(r"[,;、&/]| and ", cell) if n.strip() and not n.strip().startswith("[")]


def lecturers(site: Site) -> dict[str, list[tuple[str, str]]]:
    """Lecturer → [(course code, session)], from every course README's session table."""
    out: dict[str, list[tuple[str, str]]] = {}
    for c in site.courses:
        for sess, cell in c.lecturers.items():
            for name in split_lecturers(cell):
                out.setdefault(name, []).append((c.code, sess))
    return dict(sorted(out.items(), key=lambda kv: kv[0].lower()))


def lecturer_links_html(site: Site, cell: str) -> str:
    names = split_lecturers(cell)
    if not names:
        return esc(cell)
    return "、".join(f'<a href="{site.prefix}lecturers/{lecturer_slug(n)}/">{esc(n)}</a>' for n in names)


LECTURER_TEMPLATE = ("- 课程 / Courses：\n- 授课风格 / Teaching style：\n- 考核风格 / Assessment style：\n"
                     "- 沟通 / Communication：\n- 性格 / Personality：\n- 适合找 TA 做 / Good to approach for：\n- 同学建议 / Tips：")


def lecturer_index_html(site: Site) -> str:
    cards = []
    for name, taught in lecturers(site).items():
        codes = sorted({code for code, _ in taught})
        sessions = sorted({s for _, s in taught})
        cards.append(f'<a class="card" href="{site.prefix}lecturers/{lecturer_slug(name)}/"><h3>{esc(name)}</h3>'
                     f'<p>{esc("、".join(codes))}</p><p>{esc("、".join(sessions))}</p></a>')
    return ('<h2 id="profiles">档案 | Profiles</h2>'
            "<p>名单来自各课程文件夹 README 的学期表；点进去看教过的课，并在页面底部留下你的描述（登录 GitHub 即可，立刻可见；"
            "机器人会按关键词自动折叠辱骂和敏感内容，维护者可以删除）。</p>"
            "<p>Names come from the session tables in the course READMEs. Open one to see the courses taught and leave your "
            "description at the bottom (sign in with GitHub; visible at once; a bot folds abusive or sensitive comments by keyword, "
            "maintainers may delete).</p>"
            f'<div class="lect-grid">{"".join(cards)}</div>')


def lecturer_page(site: Site, name: str, taught: list[tuple[str, str]]) -> str:
    rows = []
    for code, sess in sorted(taught, key=lambda t: (t[0], t[1])):
        c = next((c for c in site.courses if c.code == code), None)
        if c is None:
            continue
        rows.append(f'<tr><td>{esc(code)}</td><td><a href="{site.prefix}{c.path}/">{esc(c.name)}</a></td>'
                    f'<td><a href="{site.prefix}{c.path}/#{sess}">{esc(sess)}</a></td></tr>')
    table = ('<div class="table-wrap"><table><thead><tr><th>代码 / Code</th><th>课程 / Course</th><th>学期 / Session</th></tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>')
    rules = (f'<p class="notice">写具体、可观察的事实，只描述不打分；不写外貌、私生活、政治或宗教立场，不写私人联系方式。'
             f'规则见<a href="{site.prefix}lecturers/">教师档案页</a>。老师本人如需修改或移除，邮件 xieqiyi@ieee.org。<br>'
             f'Concrete, observable facts; descriptions, no scores; nothing about appearance, private life, politics or religion, '
             f'no private contacts. Rules on the <a href="{site.prefix}lecturers/">lecturers page</a>. '
             f'Lecturers who want anything changed: xieqiyi@ieee.org.</p>'
             f"<details><summary>可以照这个模板写 | A template you can follow</summary><pre>{esc(LECTURER_TEMPLATE)}</pre></details>")
    content = (f"<h1>{esc(name)}</h1><h2>教过的课 | Courses taught</h2>{table}"
               f'<h2 id="profile">同学描述 | What students say</h2>{rules}'
               + giscus_html(*GISCUS_GENERAL, f"教师 | Lecturer: {name}"))
    return page(site, name, content, f"{name}：教过的课程与同学描述 | courses taught and student descriptions")


def added_dates(root: Path) -> dict[str, str]:
    """Repo path → date (YYYY-MM-DD) the file first appeared at that path, from git history; {} when there is none."""
    try:
        raw = subprocess.run(["git", "-c", "core.quotepath=off", "log", "--format=%cs", "--diff-filter=A", "--no-renames",
                              "--name-only", "--", *PROGS], cwd=root, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        warn("git history unavailable, the recent-uploads list is empty")
        return {}
    dates: dict[str, str] = {}
    date = ""
    for line in raw.decode("utf-8", "replace").splitlines():
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", line):
            date = line
        elif line.strip():
            dates[line] = date   # newest commit first, so the last assignment wins: the earliest add
    return dates


def recent_entries(site: Site, limit: int = 100) -> list[dict]:
    """Uploads grouped by (date, course, session, type), newest first."""
    dates = added_dates(site.root)
    if not dates:
        return []
    groups: dict[tuple, dict] = {}
    for c in site.courses:
        for sess, types in c.sessions.items():
            for t, files in types.items():
                for f in files:
                    d = dates.get(f.path)
                    if not d:
                        continue
                    g = groups.setdefault((d, c.code, sess, t), {
                        "date": d, "code": c.code, "name": c.name, "session": sess, "type": t, "n": 0,
                        "url": f"{site.prefix}{c.path}/#{sess}", "by": LINK_RE.sub(r"\1", c.contributors.get(sess, ""))})
                    g["n"] += 1
    return sorted(groups.values(), key=lambda g: (g["date"], g["code"], g["session"], g["type"]), reverse=True)[:limit]


def recent_html(entries: list[dict]) -> str:
    if not entries:
        return "<p>暂时无法读取上传记录 | Upload history is not available right now.</p>"
    items = []
    for e in entries:
        by = f" · 来自 | by {esc(e['by'])}" if e["by"] else ""
        items.append(f'<li><time datetime="{e["date"]}">{e["date"]}</time> <a href="{e["url"]}">{esc(e["code"])} {esc(e["name"])}</a> '
                     f'<small>{esc(e["session"])} · {esc(e["type"])} · {e["n"]} 份 | files{by}</small></li>')
    return f'<ul class="recent">{"".join(items)}</ul>'


def recent_page(site: Site) -> str:
    content = ("<h1>最近上传 | Recent uploads</h1>"
               f'<p>按文件进入仓库的日期排列，最新在前。订阅：<a href="{site.prefix}feed.xml">RSS / Atom</a>。'
               f'<br>By the date each file entered the repository, newest first. Subscribe: <a href="{site.prefix}feed.xml">RSS / Atom</a>.</p>'
               + recent_html(getattr(site, "recent", [])))
    return page(site, "最近上传 | Recent uploads", content)


def feed_xml(site: Site, entries: list[dict]) -> str:
    def x(s: str) -> str:
        return html_mod.escape(s, quote=True)
    updated = (entries[0]["date"] if entries else "2026-01-01") + "T00:00:00Z"
    items = []
    for e in entries[:50]:
        url = SITE_URL + e["url"][len(site.prefix):]
        title = f"{e['code']} {e['session']} · {e['type']}（{e['n']} 份 | files）"
        summary = f"{e['code']} {e['name']} {e['session']} {e['type']}: {e['n']} 份文件 | files" + (f"，来自 | by {e['by']}" if e["by"] else "")
        items.append(f"<entry><title>{x(title)}</title><link href=\"{x(url)}\"/>"
                     f"<id>{x(SITE_URL)}recent/#{x(e['date'])}-{x(e['code'])}-{x(e['session'])}-{x(e['type'])}</id>"
                     f"<updated>{e['date']}T00:00:00Z</updated><summary>{x(summary)}</summary></entry>")
    return ('<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom">'
            f'<title>XMUM SAIR 生存指南 · 最近上传 | Recent uploads</title><link href="{x(SITE_URL)}"/>'
            f'<link rel="self" href="{x(SITE_URL)}feed.xml"/><id>{x(SITE_URL)}</id><updated>{updated}</updated>'
            + "".join(items) + "</feed>\n")


def wanted_page(site: Site) -> str:
    parts = ["<h1>征集榜 | Wanted</h1>",
             f'<p>下面这些课还没有任何资料。修过的同学如果手上有空白试卷、大纲、作业题或笔记，<a href="{UPLOAD_URL}">用上传表单</a>发给我们。'
             f'<br>These courses have no material yet. If you took one and still have blank papers, a syllabus, assignment briefs or notes, '
             f'<a href="{UPLOAD_URL}">use the upload form</a>.</p>']
    def item(c: Course, extra: str = "") -> str:
        return f'<li><a href="{site.prefix}{c.path}/">{esc(c.code)} {esc(c.name)}</a>{extra}</li>'

    def section(title: str, items: list[str]) -> str:
        return f"<h3>{title}（{len(items)}）</h3>" + (f"<ul>{''.join(items)}</ul>" if items else "<p>无 | none</p>")

    for prog, pname in PROGS.items():
        cs = [c for c in site.courses if c.prog == prog]
        if not cs:
            continue
        empty = [item(c, f' <small>修课学期 | taken in {esc("、".join(c.taken_in))}</small>' if c.taken_in else "")
                 for c in cs if not c.sessions]
        no_papers = [item(c) for c in cs if c.sessions and not any("Past-Papers" in types for types in c.sessions.values())]
        gaps = [item(c, f" <small>· {esc(s)}</small>") for c in cs for s in c.taken_in if s not in c.sessions]
        parts.append(f"<h2>{prog} · {esc(pname)}</h2>"
                     + section("还没有任何资料 | No material at all", empty)
                     + section("缺空白试卷 | No past papers yet", no_papers)
                     + section("有人修过、但那个学期还没资料 | Sessions someone took that are not covered", gaps))
    parts.append("<p>⬜ 征集中 / wanted 也会标在各专业页的课程索引里。The programme pages mark courses without material as ⬜ 征集中 / wanted too.</p>")
    return page(site, "征集榜 | Wanted", "".join(parts))


def site_pages(site: Site) -> list[str]:
    """Every page's path relative to the site root, for the sitemap."""
    pages = ["", "qa/", "recent/", "wanted/", *ROOT_PAGES.values(), *(f"{p}/" for p in PROGS),
             *(f"{c.path}/" for c in site.courses), *(f"lecturers/{lecturer_slug(n)}/" for n in lecturers(site))]
    return list(dict.fromkeys(pages))


def sitemap_xml(site: Site) -> str:
    urls = "".join(f"<url><loc>{html_mod.escape(SITE_URL + p, quote=True)}</loc></url>" for p in site_pages(site))
    return ('<?xml version="1.0" encoding="utf-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + urls + "</urlset>\n")


def robots_txt() -> str:
    return f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n"


def rewrite_link(site: Site, href: str, src_md: str) -> str:
    """Turn a relative link inside repo markdown into a site URL or a GitHub URL."""
    if href.startswith(("http://", "https://", "mailto:", "#")):
        return href
    path, _, frag = href.partition("#")
    frag = f"#{frag}" if frag else ""
    p = posixpath.normpath(posixpath.join(posixpath.dirname(src_md), unquote(path))).strip("/")
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
        # a session folder, or a type folder inside one, is a section of the course page
        if len(rest) == 1 or (len(rest) == 2 and rest[1] in SUBS):
            if rest[0] in course.sessions:
                return f"{site.prefix}{course.path}/#{rest[0]}"
            if SESSION_RE.fullmatch(rest[0]) or rest[0] == "unknown":
                warn(f"{src_md}: {p} has no indexed material, linking to GitHub instead")
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

    out = re.sub(r'href="([^"]*)"', fix, out)
    # wide bilingual tables scroll sideways on phones instead of breaking the layout
    return out.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")


# ---------------------------------------------------------------- pages

HERE = Path(__file__).resolve().parent
esc = html_mod.escape
DEFAULT_DESC = ("厦门大学马来西亚分校 SAIR 学院学生自发整理的开放学习资料库：空白试卷、大纲、作业、实验手册、笔记 | "
                "Student-run open archive of study material for XMUM SAIR: blank papers, syllabi, assignments, lab manuals, notes")
GISCUS_REPO_ID = "R_kgDOQ_iF5g"
GISCUS_COURSE = ("Q&A", "DIC_kwDOQ_iF5s4DKajf")
GISCUS_GENERAL = ("General", "DIC_kwDOQ_iF5s4DKaje")
GISCUS_NOTICE = ("发言需登录 GitHub，用户名公开。请勿张贴答案、评分标准、他人个人信息或老师的私人联系方式。"
                 "评论保存在本仓库的 GitHub Discussions 中，维护者可以删除。<br>"
                 "Sign in with GitHub to post; your username is public. Do not post answers, marking schemes, "
                 "other people's personal data or lecturers' private contact details. Comments live in this repo's "
                 "GitHub Discussions and may be removed by the maintainers.")
# header order = importance: the three programmes, Q&A, (Upload is inserted here), how to contribute, then the rest
NAV = [("EEE", "EEE/", "⚡"), ("AIT", "AIT/", "🧠"), ("ROBO", "ROBO/", "🤖"), ("问答 | Q&A", "qa/", "💬"),
       ("如何贡献 | Contribute", "contributing/", "🤝"), ("教师 | Lecturers", "lecturers/", "🎓"),
       ("研究机会 | Research", "research/", "🔬"), ("贡献者 | Contributors", "contributors/", "👥"),
       ("关于 | About", "about/", "ℹ️")]
UPLOAD_AFTER = 4  # the Upload block sits right after Q&A
UPLOAD_URL = f"{GH}/issues/new?template=upload.yml"  # the upload form (intake/DESIGN.md)
GITHUB_MARK = ('<svg viewBox="0 0 16 16" width="20" height="20" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 '
               '6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 '
               '1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 '
               '.67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 '
               '3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>')


def template() -> Template:
    return Template((HERE / "templates" / "base.html").read_text(encoding="utf-8"))


def nav_block(i: int, href: str, icon: str, main: str, sub: str, cls: str = "", label: str = "") -> str:
    """One header block: icon on the left, two-line label (Chinese over English) on the right."""
    aria = f' aria-label="{esc(label)}"' if label else ""
    return (f'<a class="nb{(" " + cls) if cls else ""}" href="{href}"{aria} style="--i:{i}">'
            f'<span class="nb-ic" aria-hidden="true">{icon}</span>'
            f'<span class="nb-t">{esc(main)}<small>{esc(sub)}</small></span></a>')


def nav_html(site: Site) -> str:
    blocks = []
    for i, (title, path, icon) in enumerate(NAV):
        if title in PROGS:  # programme code over its Chinese name
            main, sub = title, PROGS[title].split(" | ")[0]
        else:
            main, sub = title.split(" | ")
        blocks.append(nav_block(i, f"{site.prefix}{path}", icon, main, sub))
    blocks.insert(UPLOAD_AFTER, nav_block(UPLOAD_AFTER, UPLOAD_URL, "📤", "上传", "Upload", cls="upload", label="上传 | Upload"))
    blocks.append(nav_block(len(blocks), GH, GITHUB_MARK, "GitHub", "仓库 Repository"))
    form = (f'<form class="mini-search" action="{site.prefix}" method="get" role="search">'
            '<label class="sr-only" for="nav-q">搜索 | Search</label>'
            '<input id="nav-q" name="q" type="search" placeholder="搜索 | Search"></form>')
    tools = (f'<div class="tools">{form}'
             '<button class="theme-toggle" type="button" aria-label="切换深浅色 | Toggle theme">🌙</button></div>')
    return f'{tools}<nav class="nav-blocks" aria-label="主导航 | Main navigation">{"".join(blocks)}</nav>'


def page(site: Site, title: str, content: str, description: str = "") -> str:
    return template().substitute(title=esc(title), description=esc(description or DEFAULT_DESC),
                                 base=site.prefix, nav=nav_html(site), content=content)


def giscus_html(category: str, category_id: str, term: str) -> str:
    return (f'<p class="notice">{GISCUS_NOTICE}</p>'
            f'<script src="https://giscus.app/client.js" data-repo="{REPO}" data-repo-id="{GISCUS_REPO_ID}" '
            f'data-category="{esc(category)}" data-category-id="{category_id}" data-mapping="specific" '
            f'data-term="{esc(term)}" data-strict="1" data-reactions-enabled="1" data-emit-metadata="0" '
            'data-input-position="top" data-theme="preferred_color_scheme" data-lang="zh-CN" '
            'crossorigin="anonymous" async></script>')


def human_size(n: int) -> str:
    return f"{n / 1048576:.1f} MB" if n >= 1048576 else f"{max(1, round(n / 1024))} KB"


def course_table_html(site: Site, prog: str) -> str:
    courses = [c for c in site.courses if c.prog == prog]
    head = ("<thead><tr><th>代码 / Code</th><th>课程 / Course</th><th>修课学期 / Taken in</th>"
            "<th>资料学期 / Sessions covered</th><th>资料 / Material</th></tr></thead>")
    rows = []
    for c in courses:
        url = f"{site.prefix}{c.path}/"
        cov = " · ".join(f'<a href="{url}#{s}">{s}</a>' for s in c.sessions) or "—"
        mats = []
        for s, types in c.sessions.items():
            counts = " · ".join(f"{t} ({len(fs)})" for t, fs in types.items())
            mats.append(f"{s}: {counts}" if len(c.sessions) > 1 else counts)
        mat = "<br>".join(mats) if mats else "⬜ 征集中 / wanted"
        rows.append(f'<tr><td>{esc(c.code)}</td><td><a href="{url}">{esc(c.name)}</a></td>'
                    f'<td>{"、".join(c.taken_in) or "—"}</td><td>{cov}</td><td>{mat}</td></tr>')
    if not rows:
        rows.append('<tr><td colspan="5">暂无课程 | No courses yet</td></tr>')
    return f'<div class="table-wrap"><table>{head}<tbody>{"".join(rows)}</tbody></table></div>'


def file_item(f: File) -> str:
    links = ""
    if f.name.lower().endswith(".pdf"):
        links += f' <a class="btn" href="{GH}/blob/main/{url_path(f.path)}">预览 | Preview</a>'
    links += f' <a class="btn" href="{RAW}/{url_path(f.path)}">下载 | Download</a>'
    return f'<li><span class="fname">{esc(f.name)}</span> <small>{human_size(f.size)}</small>{links}</li>'


def course_page(site: Site, c: Course) -> str:
    title = f"{c.code} {c.name}"
    meta = (f'<p class="meta"><a href="{site.prefix}{c.prog}/">{c.prog} · {esc(PROGS[c.prog])}</a> · '
            f'修课学期 | Taken in: {"、".join(c.taken_in) or "—"} · '
            f'<a href="{GH}/tree/main/{url_path(c.path)}">在 GitHub 上查看文件夹 | View folder on GitHub</a></p>')
    body = render_md(site, c.readme, f"{c.path}/README.md") if c.readme else f"<h1>{esc(title)}</h1>"
    body = body.replace("</h1>", "</h1>" + meta, 1) if "</h1>" in body else meta + body
    parts = ['<h2 id="files">资料 | Files</h2>']
    if not c.sessions:
        parts.append("<p>⬜ 征集中 / wanted</p>")
    for s, types in c.sessions.items():
        label = "未知学期 | unknown" if s == "unknown" else s
        lect = f" · 老师 | Lecturer: {lecturer_links_html(site, c.lecturers[s])}" if s in c.lecturers else ""
        zipb = (f' <a class="btn" href="{DOWNLOADS}/{url_path(c.code)}_{s}.zip" '
                f'title="这个学期的全部文件打成一个 zip | Every file of this session in one zip">打包下载 | Download all</a>')
        parts.append(f'<h3 id="{s}">{label}{lect}{zipb}</h3>')
        for t, fs in types.items():
            parts.append(f'<h4>{t} ({len(fs)})</h4><ul class="files">{"".join(file_item(f) for f in fs)}</ul>')
    qa = '<h2 id="qa">问答 | Q&A</h2>' + giscus_html(*GISCUS_COURSE, title)
    return page(site, title, body + "".join(parts) + qa,
                f"{title}：{PROGS[c.prog]} 课程资料与问答 | course material and Q&A")


def prog_page(site: Site, prog: str) -> str:
    rpath = site.root / prog / "README.md"
    text = rpath.read_text(encoding="utf-8") if rpath.is_file() else f"# {prog} | {PROGS[prog]}\n\nCOURSEINDEXTOKEN\n"
    text = re.sub(r"<!-- COURSE-INDEX -->.*?<!-- /COURSE-INDEX -->", "COURSEINDEXTOKEN", text, flags=re.S)
    html = render_md(site, text, f"{prog}/README.md").replace("<p>COURSEINDEXTOKEN</p>", course_table_html(site, prog))
    return page(site, f"{prog} · {PROGS[prog]}", html, f"{prog} {PROGS[prog]} 课程索引 | course index")


def root_page(site: Site, md: str) -> str:
    text = (site.root / md).read_text(encoding="utf-8")
    m = re.search(r"^# (.+)$", text, flags=re.M)
    body = render_md(site, text, md)
    if md == "CONTRIBUTING.md":
        body = (f'<p class="notice">最简单的方式：填<a href="{UPLOAD_URL}">上传表单</a>，机器人会整理文件并开一个 PR 等维护者审核。<br>'
                f'Easiest way: fill in the <a href="{UPLOAD_URL}">upload form</a>; the bot files everything and opens a PR for review.</p>') + body
    if md == "Lecturers.md":
        body += lecturer_index_html(site)
    return page(site, m.group(1).strip() if m else md, body)


def home_page(site: Site) -> str:
    cards = []
    for prog, name in PROGS.items():
        cs = [c for c in site.courses if c.prog == prog]
        n_mat, n_files = sum(1 for c in cs if c.sessions), len(all_files(cs))
        cards.append(f'<a class="card" href="{site.prefix}{prog}/"><h3>{prog}</h3><p>{esc(name)}</p>'
                     f'<p class="stats">{n_mat} / {len(cs)} 门课有资料 · {n_files} 份文件<br>'
                     f'{n_mat} of {len(cs)} courses with material · {n_files} files</p></a>')
    links = [("上传资料 | Upload material", UPLOAD_URL), ("征集榜 | Wanted", f"{site.prefix}wanted/"),
             ("最近上传 | Recent uploads", f"{site.prefix}recent/"),
             ("问答 | Q&A", f"{site.prefix}qa/"), ("研究机会 | Research", f"{site.prefix}research/"),
             ("教师档案 | Lecturers", f"{site.prefix}lecturers/"), ("贡献者 | Contributors", f"{site.prefix}contributors/"),
             ("如何贡献 | How to contribute", f"{site.prefix}contributing/"), ("免责声明 | Disclaimer", f"{site.prefix}disclaimer/"),
             ("关于 | About", f"{site.prefix}about/"), ("GitHub 仓库 | Repository", GH)]
    content = (
        '<section class="hero"><h1>XMUM SAIR 生存指南 | Survival Guide</h1><p class="ciallo">Ciallo～ (∠・ < )⌒☆</p>'
        "<p>厦门大学马来西亚分校人工智能与机器人学院（SAIR）三个本科专业的开放资料库：空白试卷、大纲、作业题、实验手册、笔记，全部免费公开。想找哪门课，直接搜。</p>"
        "<p>An open, student-run archive for the three undergraduate programmes of XMUM's School of Artificial Intelligence "
        "and Robotics: blank past papers, syllabi, assignment briefs, lab manuals and notes, all free. Search for a course to start.</p></section>"
        f'<form id="search" action="{site.prefix}" method="get" role="search">'
        '<label for="q">搜索课程代码、课名、老师或文件名 | Search by course code, name, lecturer or file name</label>'
        '<input id="q" name="q" type="search" autocomplete="off" placeholder="例如 COM107、Circuits、Chua | e.g. COM107"></form>'
        '<div id="results" aria-live="polite"></div>'
        f'<h2>专业 | Programmes</h2><div class="cards">{"".join(cards)}</div>'
        f'<h2>最近上传 | Recent uploads</h2>{recent_html(getattr(site, "recent", [])[:8])}'
        f'<p><a href="{site.prefix}recent/">全部 | All</a> · <a href="{site.prefix}feed.xml">RSS</a> · '
        f'<a href="{site.prefix}wanted/">还缺资料的课 | Courses still wanted</a></p>'
        '<h2>更多 | More</h2><ul class="links">' + "".join(f'<li><a href="{u}">{esc(t)}</a></li>' for t, u in links) + "</ul>")
    return page(site, "首页 | Home", content)


def qa_page(site: Site) -> str:
    content = ("<h1>综合问答 | General Q&amp;A</h1>"
               "<p>不属于某一门课的问题放这里：新生适应、选课顺序、科研与实习、学习方法。某门课的具体问题请到那门课的页面底部提问，方便后来人按课查找。</p>"
               "<p>Questions that do not belong to one course go here: settling in as a fresher, course selection, research and "
               "internships, study habits. For a specific course, ask at the bottom of that course's page so later students can find it.</p>"
               + giscus_html(*GISCUS_GENERAL, "综合问答 | General Q&A"))
    return page(site, "综合问答 | General Q&A", content)


def not_found_page(site: Site) -> str:
    content = ('<h1>找不到页面 | Page not found</h1><p>这个地址没有内容。课程文件夹可能改名了，试试搜索。</p>'
               f'<p>Nothing lives at this address; the course folder may have been renamed. Try the <a href="{site.prefix}">search on the home page</a>.</p>')
    return page(site, "找不到页面 | Not found", content)


def search_index(site: Site) -> dict:
    courses = [{"prog": c.prog, "code": c.code, "name": c.name, "url": f"{site.prefix}{c.path}/",
                "lecturers": sorted(set(c.lecturers.values())), "sessions": list(c.sessions),
                "files": len(all_files([c]))} for c in site.courses]
    files = [{"prog": f.prog, "code": f.code, "course": f.course, "session": f.session, "type": f.type,
              "name": f.name, "path": f.path,
              "preview": f"{GH}/blob/main/{url_path(f.path)}" if f.name.lower().endswith(".pdf") else None,
              "download": f"{RAW}/{url_path(f.path)}"} for f in all_files(site.courses)]
    return {"courses": courses, "files": files}


def build(root: Path, out: Path, prefix: str) -> Site:
    site = Site(root, prefix)
    out = Path(out)
    if out.exists():
        if not (out / "search.json").is_file():   # only wipe a directory a previous build wrote
            raise SystemExit(f"refusing to delete {out}: not a previous build output")
        shutil.rmtree(out)

    def write(rel: str, text: str) -> None:
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith(".html"):   # the template's canonical placeholder becomes this page's public address
            text = text.replace("__CANONICAL__", SITE_URL + (rel[:-len("index.html")] if rel.endswith("index.html") else rel))
        p.write_text(text, encoding="utf-8")

    site.recent = recent_entries(site)

    write("index.html", home_page(site))
    write("404.html", not_found_page(site))
    write("qa/index.html", qa_page(site))
    write("recent/index.html", recent_page(site))
    write("wanted/index.html", wanted_page(site))
    for name, taught in lecturers(site).items():
        write(f"lecturers/{lecturer_slug(name)}/index.html", lecturer_page(site, name, taught))
    for md, rel in ROOT_PAGES.items():
        if (site.root / md).is_file():
            write(rel + "index.html", root_page(site, md))
        else:
            warn(f"{md} missing, page {rel} skipped")
    for prog in PROGS:
        write(f"{prog}/index.html", prog_page(site, prog))
    for c in site.courses:
        write(f"{c.path}/index.html", course_page(site, c))
    write("search.json", json.dumps(search_index(site), ensure_ascii=False))
    write("feed.xml", feed_xml(site, site.recent))
    write("sitemap.xml", sitemap_xml(site))
    write("robots.txt", robots_txt())
    shutil.copytree(HERE / "static", out / "static")
    return site


# ---------------------------------------------------------------- self-check

FORBIDDEN = ("Co-Authored", "Claude", "Anthropic")


def stragglers(site: Site) -> list[str]:
    """Tracked files under the programme folders that the scan did not pick up (wrong depth or name)."""
    try:
        raw = subprocess.run(["git", "ls-files", "-z", *PROGS], cwd=site.root, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):  # no git, or the root is not a checkout (intake dry run)
        warn("git unavailable, straggler check skipped")
        return []
    tracked = [p for p in raw.decode("utf-8").split("\0") if p]
    seen = {f.path for f in all_files(site.courses)}
    return [p for p in tracked if p not in seen and posixpath.basename(p) != "README.md"]


def check_generator_sources() -> list[str]:
    """Forbidden words in the generator's own files. Repo content is not scanned: people and papers may carry any name."""
    hits = []
    for p in sorted(HERE.rglob("*")):
        if p.suffix not in (".py", ".html", ".css", ".js") or "__pycache__" in p.parts or p.name.startswith("test_"):
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "FORBIDDEN" in line:
                continue
            hits += [f"{p.relative_to(HERE).as_posix()}:{i}: {w}" for w in FORBIDDEN if w in line]
    return hits


def check(site: Site, out: Path) -> None:
    """Assert the generated site is consistent; content problems only warn."""
    out = Path(out)
    pages = list(out.glob("*/*_*/index.html"))
    assert len(pages) == len(site.courses), f"{len(pages)} course pages for {len(site.courses)} courses"
    idx = json.loads((out / "search.json").read_text(encoding="utf-8"))
    assert len(idx["files"]) == len(all_files(site.courses)), "search.json file count differs from the scan"
    for f in idx["files"]:
        assert (site.root / f["path"]).is_file(), f"search.json path missing: {f['path']}"
    bad = check_generator_sources()
    assert not bad, f"generator sources contain forbidden words: {bad}"
    for page_file in out.rglob("*.html"):
        text = page_file.read_text(encoding="utf-8")
        for href in re.findall(r'href="([^"]*)"', text):
            href = html_mod.unescape(href)
            if not href.startswith(site.prefix):
                continue
            rel = href[len(site.prefix):].split("#")[0].split("?")[0]
            target = out / rel / "index.html" if rel == "" or rel.endswith("/") else out / rel
            assert target.is_file(), f"{page_file.relative_to(out)}: dead internal link {href}"
    for p in stragglers(site):
        warn(f"not indexed: {p}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="_site")
    ap.add_argument("--prefix", default="/XMUM-SAIR-Survival-Guide/", help="URL path the site is served under")
    ap.add_argument("--root", default=str(HERE.parent), help="repository tree to build from")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    site = build(root, Path(args.out), args.prefix)
    try:
        check(site, Path(args.out))
    except AssertionError as e:
        print(f"ERROR: self-check failed: {e}", file=sys.stderr)
        return 1
    print(f"{len(site.courses)} courses, {len(all_files(site.courses))} files -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
