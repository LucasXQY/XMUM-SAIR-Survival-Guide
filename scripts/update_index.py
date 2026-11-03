"""Regenerate the course-index table in <Programme>/README.md.

用法 / Usage:  python scripts/update_index.py EEE

扫描 EEE/<CODE>_<Course_Name>/ 下的子文件夹，统计文件数，并从同一个 README 里
"各届培养方案" 的表格读出每门课在哪一届哪个学期开，然后重写
<!-- COURSE-INDEX --> 和 <!-- /COURSE-INDEX --> 之间的内容。培养方案表本身是手写的。

Scans EEE/<CODE>_<Course_Name>/ subfolders, counts files, reads which cohort /
year / semester each course appears in from the hand-written curriculum tables
in the same README, and rewrites everything between the COURSE-INDEX markers.
"""
import os, re, sys

SUBS = ("Past-Papers", "Syllabus", "Assignments", "Labs", "Tutorials",
        "Handbooks", "Notes", "Exam-Review", "Tips")
prog = sys.argv[1] if len(sys.argv) > 1 else "EEE"
root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), prog)
readme = os.path.join(root, "README.md")
text = open(readme, encoding="utf-8").read()

# where each course is taught: parse "### 2021 入学（2025 届）..." + rows "| Y1 | S3 | [COM107](folder/) | ..."
taught = {}
cohort = None
for line in text.splitlines():
    m = re.match(r"^### (\d{4}) 入学", line)
    if m:
        cohort = m.group(1); continue
    m = re.match(r"^\| (Y\d) \| (S\d) \| \[?([^\]|]+?)\]?(?:\([^)]*\))? \|", line)
    if m and cohort:
        y, s, code = m.groups()
        taught.setdefault(code.strip(), []).append(f"{cohort} {y}{s}")

rows = []
for d in sorted(os.listdir(root)):
    p = os.path.join(root, d)
    if not os.path.isdir(p) or "_" not in d:
        continue
    code, name = d.split("_", 1)
    name = name.replace("_", " ")
    links = []
    for s in SUBS:
        sp = os.path.join(p, s)
        if os.path.isdir(sp):
            n = sum(1 for f in os.listdir(sp) if not f.startswith("."))
            if n: links.append(f"[{s} ({n})]({d}/{s})")
    if os.path.exists(os.path.join(p, "README.md")):
        links.insert(0, f"[README]({d}/README.md)")
    mat = " · ".join(links) if links else "⬜ 征集中 / wanted"
    when = "、".join(taught.get(code, [])) or "—"
    rows.append(f"| {code} | [{name}]({d}/) | {when} | {mat} |")

table = "\n".join([
    "| 代码 / Code | 课程 / Course | 开课（入学年 学年学期）/ Taught (intake Y·S) | 资料 / Material |",
    "|---|---|---|---|", *rows])
new = re.sub(r"<!-- COURSE-INDEX -->.*?<!-- /COURSE-INDEX -->",
             f"<!-- COURSE-INDEX -->\n{table}\n<!-- /COURSE-INDEX -->", text, flags=re.S)
assert new != text or "<!-- COURSE-INDEX -->" in text, "markers not found"
open(readme, "w", encoding="utf-8", newline="\n").write(new)
print(f"{len(rows)} courses indexed")
