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
import sys
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
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
NAV = [("EEE", "EEE/"), ("AIT", "AIT/"), ("ROBO", "ROBO/"), ("问答 | Q&A", "qa/"),
       ("研究机会 | Research", "research/"), ("教师 | Lecturers", "lecturers/"),
       ("贡献者 | Contributors", "contributors/"), ("如何贡献 | Contribute", "contributing/"),
       ("关于 | About", "about/")]


def template() -> Template:
    return Template((HERE / "templates" / "base.html").read_text(encoding="utf-8"))


def nav_html(site: Site) -> str:
    links = "".join(f'<a href="{site.prefix}{p}">{esc(t)}</a>' for t, p in NAV)
    links += f'<a href="{GH}">GitHub</a>'
    form = (f'<form class="mini-search" action="{site.prefix}" method="get" role="search">'
            '<label class="sr-only" for="nav-q">搜索 | Search</label>'
            '<input id="nav-q" name="q" type="search" placeholder="搜索 | Search"></form>')
    return f"<nav>{links}</nav>{form}"


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
        lect = f" · 老师 | Lecturer: {esc(c.lecturers[s])}" if s in c.lecturers else ""
        parts.append(f'<h3 id="{s}">{label}{lect}</h3>')
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
    return page(site, m.group(1).strip() if m else md, render_md(site, text, md))


def home_page(site: Site) -> str:
    cards = []
    for prog, name in PROGS.items():
        cs = [c for c in site.courses if c.prog == prog]
        n_mat, n_files = sum(1 for c in cs if c.sessions), len(all_files(cs))
        cards.append(f'<a class="card" href="{site.prefix}{prog}/"><h3>{prog}</h3><p>{esc(name)}</p>'
                     f'<p class="stats">{n_mat} / {len(cs)} 门课有资料 · {n_files} 份文件<br>'
                     f'{n_mat} of {len(cs)} courses with material · {n_files} files</p></a>')
    links = [("问答 | Q&A", f"{site.prefix}qa/"), ("研究机会 | Research", f"{site.prefix}research/"),
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
        shutil.rmtree(out)

    def write(rel: str, text: str) -> None:
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    write("index.html", home_page(site))
    write("404.html", not_found_page(site))
    write("qa/index.html", qa_page(site))
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
    shutil.copytree(HERE / "static", out / "static")
    return site


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="_site")
    ap.add_argument("--prefix", default="/XMUM-SAIR-Survival-Guide/", help="URL path the site is served under")
    args = ap.parse_args(argv)
    root = HERE.parent
    site = build(root, Path(args.out), args.prefix)
    print(f"{len(site.courses)} courses, {len(all_files(site.courses))} files → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
