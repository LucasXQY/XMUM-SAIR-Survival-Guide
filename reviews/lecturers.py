"""评价里出现、但课程 README 里没有的老师：机器人开一个 PR 把他们加进对应课程的学期表，维护者确认后合并，老师就有名录页。
Lecturers named in reviews but missing from the course READMEs: the bot opens a PR adding them to the course's session
table; once a maintainer merges it, the lecturer gets a directory page.

来源 | Sources: bot-state 分支的 pending-lecturers.json（reviews.py 登记新老师时写入，带学期）和 data 分支 ratings.json
（只有课程和老师，没有学期，这些写成 unknown，PR 里请维护者补学期）。
pending-lecturers.json on bot-state (written by reviews.py, with the session) and ratings.json on the data branch
(course and lecturer only: these get the session "unknown" and the PR asks the maintainer to fill it in).

用法 | Usage:  python reviews/lecturers.py [--dry-run]      （工作流 lecturers.yml | run by lecturers.yml）
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from reviews import lecturer_key   # noqa: E402  (same key the ratings use)
from export_legacy import post    # noqa: E402  (names the client; Cloudflare blocks Python's default)

REPO = os.environ.get("GITHUB_REPOSITORY", "xmum-sair/xmum-sair.github.io")
PROGS = ("EEE", "AIT", "ROBO", "GE")
PENDING = "pending-lecturers.json"
BRANCH = "bot/new-lecturers"
NOTE = "老师来自课程评价 / lecturer from a course review"   # no "|": it would split the table cell
BOT = ["-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com"]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]


def _table(lines: list[str]) -> tuple[int, int] | None:
    """(first data row, one past the last) of the session table, or None."""
    head = next((i for i, l in enumerate(lines) if l.startswith("| 学期")), None)
    if head is None:
        return None
    end = head + 2
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    return head + 2, end


def _session(cell: str) -> str:
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", cell).strip()


def _names(cell: str) -> list[str]:
    return [n.strip() for n in re.split(r"[,;、&]| and ", cell) if n.strip() and not n.strip().startswith("[")]


def readme_lecturers(text: str) -> set[str]:
    lines = text.replace("\r\n", "\n").split("\n")
    span = _table(lines)
    if not span:
        return set()
    return {lecturer_key(n) for l in lines[span[0]:span[1]] for n in _names((_cells(l) + ["", ""])[1])}


def add_lecturer(text: str, session: str, name: str) -> str:
    """The README with `name` in the lecturer cell of `session`'s row (a new row, in order, if there is none)."""
    if lecturer_key(name) in readme_lecturers(text):
        return text
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    span = _table(lines)
    if not span:
        lines += ["", "| 学期 / Session | 老师 / Lecturer | 考核 / Assessment | 资料来自 / Contributed by | 备注 / Notes |",
                  "|---|---|---|---|---|"]
        span = (len(lines), len(lines))
    start, end = span
    insert_at = end
    for i in range(start, end):
        cells = (_cells(lines[i]) + [""] * 5)[:max(5, len(_cells(lines[i])))]
        s = _session(cells[0])
        if s == session:
            cells[1] = f"{cells[1]}, {name}" if cells[1] else name
            lines[i] = "| " + " | ".join(cells) + " |"
            return eol.join(lines)
        if session != "unknown" and (s == "unknown" or s > session) and insert_at == end:
            insert_at = i
    lines.insert(insert_at, f"| {session} | {name} |  |  | {NOTE} |")
    return eol.join(lines)


def wanted(pending: list[dict], ratings: dict, readmes: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """(lecturers to add to a course README, those whose course has no folder in the repo). One entry per
    (course, lecturer); a real session beats "unknown"."""
    found: dict[tuple[str, str], dict] = {}
    for p in pending:
        found.setdefault((p["code"], lecturer_key(p["name"])), dict(p))
    for code, entry in sorted((ratings.get("courses") or {}).items()):
        for key, e in sorted((entry.get("lecturers") or {}).items()):
            found.setdefault((code, key), {"code": code, "name": e["name"], "session": "unknown"})
    add, missing = [], []
    for (code, key), item in sorted(found.items()):
        if code not in readmes:
            missing.append(item)
        elif key not in readme_lecturers(readmes[code]):
            add.append(item)
    return add, missing


def pr_body(add: list[dict], missing: list[dict]) -> str:
    rows = [f"| {a['code']} | {a['name']} | {a['session']} |" for a in add]
    parts = ["课程评价里出现了课程 README 学期表里没有的老师。合并后他们就有名录页，评价卡片也会链到名录页。",
             "学期写着 unknown 的，是只从汇总分数里看到的（汇总不带学期）；知道学期的话直接在这个 PR 里改，或合并后再改。",
             "",
             "Reviews named lecturers the course READMEs do not list. Merging gives them directory pages. \"unknown\" sessions",
             "come from the aggregate scores, which carry no session; fix them here or after merging if you know them.",
             "", "| 课程 / Course | 老师 / Lecturer | 学期 / Session |", "|---|---|---|", *rows]
    if missing:
        parts += ["", "仓库里还没有这些课的文件夹，没有加 | No folder for these courses yet, so nothing was added:", ""]
        parts += [f"- {m['code']}: {m['name']}" for m in missing]
    parts += ["", "这个分支由机器人重建，不要直接推送 | The bot rebuilds this branch; do not push to it."]
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------- git / gh

def run(*cmd: str, input: str | None = None, check: bool = True) -> str:
    r = subprocess.run(list(cmd), text=True, capture_output=True, encoding="utf-8", input=input, cwd=ROOT)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])}: {(r.stderr or r.stdout).strip()[-800:]}")
    return r.stdout.strip()


def course_readmes(root: Path) -> dict[str, Path]:
    out = {}
    for prog in PROGS:
        for d in sorted((root / prog).glob("*_*")) if (root / prog).is_dir() else []:
            if (d / "README.md").is_file():
                out.setdefault(d.name.split("_", 1)[0], d / "README.md")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(ROOT / "llm"))
    import claude_check as cc
    state = cc.StateFile(REPO, PENDING)
    pending_data, pending_sha = state.read()
    legacy = pending_data.get("items", [])   # noted by the GitHub-form bot; nothing new arrives here any more
    pending = list(legacy)
    worker, admin = os.environ.get("ASSISTANT_URL", "").rstrip("/"), os.environ.get("REVIEWS_ADMIN_TOKEN", "")
    if worker and admin:   # since 2026-11-06 the reviews live on the Worker: its kept votes give lecturer and session
        pending = pending + post(f"{worker}/admin/api", {"token": admin, "op": "lecturers"})["lecturers"]
        ratings = {}
    else:                  # the GitHub-form days: the data branch's ratings.json (course and lecturer, no session)
        raw = run("gh", "api", f"repos/{REPO}/contents/ratings.json?ref=data", check=False)
        ratings = json.loads(base64.b64decode(json.loads(raw)["content"])) if raw.startswith("{") else {}
    if not args.dry_run:
        run("git", "fetch", "-q", "origin", "main")
        run("git", "checkout", "-q", "-B", BRANCH, "origin/main")
    paths = course_readmes(ROOT)
    readmes = {code: p.read_text(encoding="utf-8") for code, p in paths.items()}
    add, missing = wanted(pending, ratings, readmes)
    keep = [p for p in legacy if (p["code"], lecturer_key(p["name"])) in {(a["code"], lecturer_key(a["name"])) for a in add}
            or p["code"] not in readmes]   # entries main already has are done
    print(f"{len(add)} to add, {len(missing)} without a course folder")
    if args.dry_run:
        print(pr_body(add, missing) if add else "nothing to propose")
        return 0
    if keep != legacy:
        state.write({"items": keep}, pending_sha, "pending lecturers: drop the ones now in main")
    existing = run("gh", "pr", "list", "--repo", REPO, "--head", BRANCH, "--state", "open", "--json", "number", "--jq", ".[0].number", check=False)
    if not add:
        if existing:
            run("gh", "pr", "close", existing, "--repo", REPO, "--comment", "都已经在 main 里了 | All of these are in main now.")
        return 0
    for a in add:
        p = paths[a["code"]]
        p.write_text(add_lecturer(p.read_text(encoding="utf-8"), a["session"], a["name"]), encoding="utf-8")
    run("git", "add", *[str(paths[a["code"]].relative_to(ROOT)) for a in add])
    run("git", *BOT, "commit", "-q", "-m", "content: add lecturers named in course reviews\n\n" + "\n".join(f"{a['code']}: {a['name']} ({a['session']})" for a in add))
    run("git", "push", "-q", "--force", "origin", BRANCH)
    title = "[老师 | Lecturers] 课程评价里出现的新老师 | Lecturers named in reviews"
    if existing:
        run("gh", "pr", "edit", existing, "--repo", REPO, "--title", title, "--body-file", "-", input=pr_body(add, missing))
    else:
        run("gh", "pr", "create", "--repo", REPO, "--base", "main", "--head", BRANCH, "--title", title, "--body-file", "-", input=pr_body(add, missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
