"""Regenerate the course-index table in <Programme>/README.md.

用法 / Usage:  python scripts/update_index.py EEE   （或 AIT、ROBO、GE | or AIT, ROBO, GE）

扫描 EEE/<CODE>_<Course_Name>/<YYYY-MM>/<子文件夹>/，统计每个学期每类资料的文件数，
并从 EEE、AIT、ROBO 三个 README 里"修课时间表"的表格读出每门课被修读的学期（YYYY-MM），
然后重写 <!-- COURSE-INDEX --> 和 <!-- /COURSE-INDEX --> 之间的内容。时间表本身是手写的。
GE/（G 选修和 MPU 公共课）没有自己的时间表，修读学期来自三个专业的时间表。

Scans EEE/<CODE>_<Course_Name>/<YYYY-MM>/<subfolder>/, counts files per session
and type, reads the sessions (YYYY-MM) each course was taken in from the
hand-written course-timeline tables of the EEE, AIT and ROBO READMEs, and rewrites
everything between the COURSE-INDEX markers. GE/ (G electives and MPU courses) has
no timeline of its own; its sessions come from the three programme timelines.
"""
import os, re, sys

SUBS = ("Past-Papers", "Syllabus", "Assignments", "Labs", "Tutorials",
        "Handbooks", "Notes", "Exam-Review", "Tips")
PROGRAMMES = ("EEE", "AIT", "ROBO")   # the timelines live in these; GE/ (G and MPU courses) has none of its own
prog = sys.argv[1] if len(sys.argv) > 1 else "EEE"
repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root = os.path.join(repo, prog)
readme = os.path.join(root, "README.md")
text = open(readme, encoding="utf-8").read()

# when each course was taken: timeline rows "| 2022-04 | [COM107](folder/) | ..." in any programme README
# (a G or MPU course under GE/ is listed in the timeline of whoever took it)
taught = {}
for p in PROGRAMMES:
    path = os.path.join(repo, p, "README.md")
    if not os.path.isfile(path):
        continue
    for line in open(path, encoding="utf-8").read().splitlines():
        m = re.match(r"^\| (\d{4}-\d{2}) \| \[?([^\]|]+?)\]?(?:\([^)]*\))? \|", line)
        if m:
            sess, code = m.groups()
            taught.setdefault(code.strip(), [])
            if sess not in taught[code.strip()]:
                taught[code.strip()].append(sess)

rows = []
for d in sorted(os.listdir(root)):
    p = os.path.join(root, d)
    if not os.path.isdir(p) or "_" not in d:
        continue
    code, name = d.split("_", 1)
    name = name.replace("_", " ")
    sessions = sorted(x for x in os.listdir(p)
                      if os.path.isdir(os.path.join(p, x)) and (re.fullmatch(r"\d{4}-\d{2}", x) or x == "unknown"))
    sess_links, mat_lines = [], []
    for sess in sessions:
        links = []
        for s in SUBS:
            sp = os.path.join(p, sess, s)
            if os.path.isdir(sp):
                n = sum(1 for f in os.listdir(sp) if not f.startswith("."))
                if n: links.append(f"[{s} ({n})]({d}/{sess}/{s})")
        if not links: continue
        sess_links.append(f"[{sess}]({d}/{sess})")
        mat_lines.append((f"{sess}: " if len(sessions) > 1 else "") + " · ".join(links))
    if os.path.exists(os.path.join(p, "README.md")):
        mat_lines.insert(0, f"[README]({d}/README.md)")
    mat = "<br>".join(mat_lines) if mat_lines else "⬜ 征集中 / wanted"
    when = "、".join(sorted(taught.get(code, []))) or "—"
    cov = " · ".join(sess_links) or "—"
    rows.append(f"| {code} | [{name}]({d}/) | {when} | {cov} | {mat} |")

table = "\n".join([
    "| 代码 / Code | 课程 / Course | 修课学期 / Taken in | 资料学期 / Sessions covered | 资料 / Material |",
    "|---|---|---|---|---|", *rows])
new = re.sub(r"<!-- COURSE-INDEX -->.*?<!-- /COURSE-INDEX -->",
             f"<!-- COURSE-INDEX -->\n{table}\n<!-- /COURSE-INDEX -->", text, flags=re.S)
assert new != text or "<!-- COURSE-INDEX -->" in text, "markers not found"
open(readme, "w", encoding="utf-8", newline="\n").write(new)
print(f"{len(rows)} courses indexed")
