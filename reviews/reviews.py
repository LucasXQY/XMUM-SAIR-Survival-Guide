"""课程评价机器人：把「课程评价」Issue 表单里的分数匿名登记到维护者的私有仓库，公开的只有汇总。
Course-review bot: records the scores from a "course review" issue form anonymously in the maintainer's private
repository and publishes aggregates only.

流程 | Flow: 解析表单 → 校验 → 投票写入私有仓库（投票人 = 加盐哈希）→ 汇总（少于 MIN_N 人只给人数）→ 推到公开仓库的 data 分支
（ratings.json，网站读取）→ 给作者留一句 → 一分钟后删除 Issue（没有删除用的 token 时退回关闭并锁定）。没登记成功的表单保留一周让作者看到原因，
之后由每次运行顺带清理。设计见 site/DESIGN.md §15。
Parse → validate → upsert the vote in the private data repo (voter = salted hash) → aggregate (count only below MIN_N) →
push ratings.json to the public repo's `data` branch (read by the site) → one reply → delete the issue a minute later
(close and lock instead when there is no delete token). A form that failed stays a week so its author can read why; every run
sweeps up the ones past that. Design: site/DESIGN.md §15.

用法 | Usage:
  python reviews/reviews.py --issue N                 # one issue (the workflow)
  python reviews/reviews.py --rebuild                 # sweep open review issues, rebuild and publish ratings.json
  python reviews/reviews.py --dry-run --form FILE --data DIR --voter X --out ratings.json   # no network (tests)
环境 | Env: GH_TOKEN (public repo), REVIEWS_TOKEN (read/write on the private data repo only), REVIEWS_SALT, REVIEWS_DATA_REPO (owner/name),
           REVIEWS_DELETE_TOKEN (the maintainer's token with Issues read/write on the public repo; deleting an issue needs a repo admin)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDS = {"code": "课程代码 | Course code", "lecturer": "老师 | Lecturer",
          "year": "年份 | Year", "term": "学期 | Term", "session_other": "其他学期 | Other session (YYYY-MM)",
          "confirm": "确认 | Confirm"}
YEARS = tuple(str(y) for y in range(2019, 2028))
TERMS = ("02", "04", "09")                   # the three intakes of a year: February, April, September
TERM_OTHER = "其他 | Other"
DIMS = [("course", "课程质量 | Course quality"), ("instructor", "老师质量 | Instructor quality"),
        ("difficulty", "难度 | Difficulty"), ("work", "作业量 | Work required"),
        ("learned", "学到多少 | Amount learned"), ("communication", "沟通 | Communication"),
        ("access", "找得到老师 | Instructor access"), ("recommend", "是否推荐 | Would recommend")]
MAIN = ("course", "instructor", "difficulty", "work")
SKIP = "不评 | Skip"
CONFIRM = "我修过这门课，这些分数是我自己的评价 | I took this course; these scores are my own judgement"
MIN_N = 3                                   # below this many voters only the count is published
CODE_RE = re.compile(r"^[A-Z]{1,4}(?:\d{3,4}|\d\.\d)$")
SESSION_RE = re.compile(r"^\d{4}-\d{2}$")
NO_RESPONSE = "_No response_"
HEADING_RE = re.compile(r"^### (.*?)\s*$", re.M)
TITLE_RE = re.compile(r"^(?:dr|prof|professor|assoc|associate|asst|assistant|puan|encik|en|cik|mr|mrs|ms|ir|ts)\.?\s+", re.I)
LABEL_REVIEW, LABEL_NEEDS_INFO = "review", "needs-info"
RECORDED, NOT_RECORDED = "已登记（匿名）", "表单还差一点"   # first words of the bot's two replies; the sweep keys on them
DELETE_DELAY = 60                     # seconds between the reply and deleting the issue, so the author's notification goes out first
KEEP_FAILED = timedelta(days=7)       # a form that was not recorded stays this long so its author can read why
BOT_IDENT = ["-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com"]


@dataclass
class Review:
    code: str = ""
    lecturer: str = ""
    session: str = ""
    scores: dict[str, int] = field(default_factory=dict)   # dimension → 1..5 (anything else fails validation)
    confirmed: bool = False


# ---------------------------------------------------------------- form

def _sections(body: str) -> dict[str, str]:
    parts = HEADING_RE.split(body.replace("\r\n", "\n"))
    return {t.strip(): x for t, x in zip(parts[1::2], parts[2::2])}


def _clean(value: str) -> str:
    value = value.strip()
    return "" if value == NO_RESPONSE else value


def parse_review(body: str) -> Review:
    sec = _sections(body)
    scores: dict[str, int] = {}
    for key, title in DIMS:
        v = _clean(sec.get(title, ""))
        if v and v != SKIP:
            scores[key] = int(v) if v.isdigit() else -1
    confirmed = bool(re.search(r"^\s*- \[[xX]\] " + re.escape(CONFIRM) + r"\s*$", sec.get(FIELDS["confirm"], ""), re.M))
    year, term = _clean(sec.get(FIELDS["year"], "")), _clean(sec.get(FIELDS["term"], ""))
    if term == TERM_OTHER:
        session = _clean(sec.get(FIELDS["session_other"], ""))
    elif year and term:
        session = f"{year}-{term}"
    else:
        session = ""
    return Review(_clean(sec.get(FIELDS["code"], "")).upper(), _clean(sec.get(FIELDS["lecturer"], "")), session, scores, confirmed)


def validate(r: Review) -> list[str]:
    p: list[str] = []
    if not CODE_RE.match(r.code):
        p.append(f"{FIELDS['code']}：应像 COM107、MPU3.1 这样 | should look like COM107 or MPU3.1")
    if not r.lecturer:
        p.append(f"{FIELDS['lecturer']}：请填老师名字，照课程页上的写法 | the lecturer's name is required, as spelled on the course page")
    if r.session and not SESSION_RE.match(r.session):
        p.append(f"{FIELDS['session_other']}：格式是 YYYY-MM，如 2021-11 | must be YYYY-MM, e.g. 2021-11")
    titles = dict(DIMS)
    bad = [titles[k] for k, v in r.scores.items() if not 1 <= v <= 5]
    if bad:
        p.append("分数只能是 1–5 | scores must be 1–5: " + "；".join(bad))
    if not any(1 <= v <= 5 for v in r.scores.values()):
        p.append("至少给一个维度打分 | give at least one score")
    if not r.confirmed:
        p.append(f"{FIELDS['confirm']}：请勾选确认 | please tick the confirmation box")
    return p


# ---------------------------------------------------------------- votes and aggregates

def display_name(name: str) -> str:
    name = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", name)).strip()
    while TITLE_RE.match(name):
        name = TITLE_RE.sub("", name, count=1)
    return name


def lecturer_key(name: str) -> str:
    """'Dr. Chua Ming Yam', 'chua  ming yam' → 'chua-ming-yam': one file per person however they were spelled."""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", display_name(name).lower())).strip("-")


def voter_hash(user_id: int, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{user_id}".encode()).hexdigest()[:24]


def vote_file(data_root: Path, r: Review) -> Path:
    return data_root / "votes" / r.code / f"{lecturer_key(r.lecturer)}.json"


def record(data_root: Path, r: Review, voter: str, when: str) -> Path:
    """One vote per (voter, course, lecturer): a later submission replaces the earlier one."""
    f = vote_file(data_root, r)
    f.parent.mkdir(parents=True, exist_ok=True)
    doc = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"code": r.code, "votes": {}}
    doc["name"] = display_name(r.lecturer)
    doc["votes"][voter] = {"scores": {k: v for k, v in r.scores.items() if 1 <= v <= 5}, "session": r.session, "at": when}
    f.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return f


def aggregate(data_root: Path) -> dict:
    """ratings.json: per course and lecturer the voter count, and the mean per dimension once MIN_N people voted."""
    out: dict = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "min_n": MIN_N,
                 "dims": [k for k, _ in DIMS], "main": list(MAIN), "courses": {}}

    def summary(votes: list[dict]) -> dict:
        entry: dict = {"n": len(votes), "counts": {k: sum(1 for v in votes if k in v["scores"]) for k, _ in DIMS}}
        if len(votes) >= MIN_N:
            for k, _ in DIMS:
                vals = [v["scores"][k] for v in votes if k in v["scores"]]
                entry[k] = round(sum(vals) / len(vals), 1) if len(vals) >= MIN_N else None
        return entry

    per_course_votes: dict[str, dict[str, dict]] = {}   # code → voter → latest vote across all lecturers of the course
    for f in sorted((data_root / "votes").glob("*/*.json")) if (data_root / "votes").is_dir() else []:
        doc = json.loads(f.read_text(encoding="utf-8"))
        entry = summary(list(doc["votes"].values()))
        entry["name"] = doc["name"]
        out["courses"].setdefault(doc["code"], {"lecturers": {}})["lecturers"][f.stem] = entry
        latest = per_course_votes.setdefault(doc["code"], {})
        for voter, v in doc["votes"].items():
            if voter not in latest or v.get("at", "") > latest[voter].get("at", ""):
                latest[voter] = v
    for code, by_voter in per_course_votes.items():   # the course as a whole: one vote per person, whoever taught them
        out["courses"][code]["all"] = summary(list(by_voter.values()))
    return out


# ---------------------------------------------------------------- GitHub side

def run(cmd: list[str], **kw) -> str:
    r = subprocess.run(cmd, text=True, capture_output=True, encoding="utf-8", **kw)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])} failed ({r.returncode}): {(r.stderr or r.stdout).strip()[-1500:]}")
    return r.stdout.strip()


def gh(*args: str, token: str | None = None, input: str | None = None) -> str:
    env = dict(os.environ)
    if token:
        env["GH_TOKEN"] = token
    return run(["gh", *args], env=env, input=input)


def clone(repo: str, token: str, dest: Path, branch: str | None = None) -> bool:
    """Shallow clone over HTTPS with a token; False when the branch (or repo) does not exist yet."""
    url = f"https://x-access-token:{token}@github.com/{repo}.git"
    args = ["git", "clone", "-q", "--depth", "1"] + (["--branch", branch] if branch else []) + [url, str(dest)]
    r = subprocess.run(args, text=True, capture_output=True, encoding="utf-8")
    return r.returncode == 0


def commit_and_push(repo_dir: Path, message: str, branch: str) -> None:
    run(["git", *BOT_IDENT, "add", "-A"], cwd=repo_dir)
    if not run(["git", "status", "--porcelain"], cwd=repo_dir):
        return
    run(["git", *BOT_IDENT, "commit", "-q", "-m", message], cwd=repo_dir)
    for attempt in range(3):   # another run may have pushed meanwhile
        r = subprocess.run(["git", "push", "-q", "-u", "origin", branch], cwd=repo_dir, text=True, capture_output=True, encoding="utf-8")
        if r.returncode == 0:
            return
        subprocess.run(["git", *BOT_IDENT, "pull", "-q", "--rebase", "origin", branch], cwd=repo_dir, text=True, capture_output=True)
    raise RuntimeError("push to the data repository failed three times")


def open_data_repo(work: Path, data_repo: str, token: str) -> Path:
    dest = work / "data"
    if dest.exists():
        return dest
    if not clone(data_repo, token, dest):
        raise RuntimeError(f"cannot clone the data repository {data_repo}: is REVIEWS_DATA_REPO set and REVIEWS_TOKEN allowed to read it?")
    return dest


def publish(agg: dict, work: Path, repo: str, token: str) -> None:
    """ratings.json on the public repo's `data` branch (not protected; the site reads it from raw.githubusercontent.com)."""
    pub = work / "pub"
    if not pub.exists() and not clone(repo, token, pub, "data"):
        pub.mkdir(parents=True, exist_ok=True)
        run(["git", "init", "-q", "-b", "data"], cwd=pub)
        run(["git", "remote", "add", "origin", f"https://x-access-token:{token}@github.com/{repo}.git"], cwd=pub)
        (pub / "README.md").write_text("课程评价的汇总数据，由 reviews.yml 自动生成，不要手改。\n"
                                       "Aggregated course ratings, written by reviews.yml; do not edit by hand.\n", encoding="utf-8")
    (pub / "ratings.json").write_text(json.dumps(agg, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    commit_and_push(pub, "ratings: rebuild", "data")


def finish_issue(number: int, repo: str) -> None:
    """Close and lock: what happens to a failed form, and to a recorded one when it cannot be deleted."""
    gh("issue", "close", str(number), "--repo", repo)
    gh("issue", "lock", str(number), "--repo", repo)


def delete_issue(node_id: str, token: str) -> None:
    gh("api", "graphql", "-f", "query=mutation($id: ID!) { deleteIssue(input: {issueId: $id}) { clientMutationId } }",
       "-f", f"id={node_id}", token=token)


def remove_source(number: int, repo: str, node_id: str, token: str, wait: int = DELETE_DELAY) -> bool:
    """Delete the issue so no public trace links an account to its scores (maintainer's decision, 2026-11-06).
    Without the delete token, or if GitHub refuses, close and lock it instead; True when it was deleted."""
    if token:
        time.sleep(wait)
        try:
            delete_issue(node_id, token)
            return True
        except Exception as e:  # e.g. the token lacks the right; the issue must not stay open either way
            print(f"#{number}: could not delete, closing and locking instead: {e}", file=sys.stderr)
    finish_issue(number, repo)
    return False


def sweep_decision(closed_at: str, bot_replies: list[str], now: datetime) -> bool:
    """Should this closed review issue be deleted now?"""
    if any(r.startswith(RECORDED) for r in bot_replies):
        return True
    if any(r.startswith(NOT_RECORDED) for r in bot_replies):
        return now - datetime.fromisoformat(closed_at.replace("Z", "+00:00")) >= KEEP_FAILED
    return False


def sweep(repo: str, token: str) -> int:
    """Delete closed review issues whose time is up; returns how many went."""
    if not token:
        return 0
    found = json.loads(gh("issue", "list", "--repo", repo, "--label", LABEL_REVIEW, "--state", "closed", "--limit", "100",
                          "--json", "number,id,closedAt"))
    now, gone = datetime.now(timezone.utc), 0
    for iss in found:
        replies = json.loads(gh("api", f"repos/{repo}/issues/{iss['number']}/comments", "--jq",
                                '[.[] | select(.user.login == "github-actions[bot]") | .body]') or "[]")
        if sweep_decision(iss["closedAt"], replies, now):
            try:
                delete_issue(iss["id"], token)
                gone += 1
            except Exception as e:
                print(f"#{iss['number']}: could not delete: {e}", file=sys.stderr)
                break   # the same refusal would repeat for every issue
    return gone


def recorded_reply(code: str, lecturer: str, deleting: bool) -> str:
    what = f"{code} · {display_name(lecturer)}"
    if deleting:
        zh = "一分钟后这个 Issue 会被自动删除，分数只以匿名编号留在维护者的私有仓库里"
        en = "this issue is deleted automatically in a minute; the scores stay only in the maintainer's private repository, under an anonymous id"
    else:
        zh = "这个 Issue 现在关闭锁定，维护者会定期删除"
        en = "this issue is now closed and locked and the maintainer deletes these periodically"
    return (f"{RECORDED}：{what}。同一门课同一位老师每人只算一票，想改分数就再提交一次。{zh}；网站上的平均分在至少 {MIN_N} 人评价后显示。\n\n"
            f"Recorded anonymously: {what}. One vote per person per course and lecturer; submit again to change it. "
            f"{en[0].upper() + en[1:]}; averages appear once at least {MIN_N} people have rated.")


def process_issue(n: int, repo: str, work: Path, data_repo: str, token: str | None, salt: str, publish_after: bool = True) -> None:
    iss = json.loads(gh("api", f"repos/{repo}/issues/{n}"))
    labels = [l["name"] for l in iss.get("labels", [])]
    if iss["state"] != "open" or LABEL_REVIEW not in labels:
        print(f"#{n}: not an open review issue, skipped")
        return
    r = parse_review(iss.get("body") or "")
    problems = validate(r)
    if problems:
        gh("issue", "comment", str(n), "--repo", repo, "--body-file", "-", input=(
            f"{NOT_RECORDED}，这次没有登记 | Not recorded yet, a few things to fix:\n\n" + "\n".join(f"- {p}" for p in problems)
            + "\n\n这个 Issue 会被关闭，一周后删除，改好后请重新提交一份。| This issue is closed and deleted in a week; please submit a new one."))
        finish_issue(n, repo)
        print(f"#{n}: {len(problems)} problem(s)")
        return
    if not token:
        raise RuntimeError("REVIEWS_TOKEN is not set: the vote cannot be stored privately")
    data = open_data_repo(work, data_repo, token)
    record(data, r, voter_hash(iss["user"]["id"], salt), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    commit_and_push(data, f"vote: {r.code} {lecturer_key(r.lecturer)}", "main")
    if publish_after:
        publish(aggregate(data), work, repo, os.environ.get("GH_TOKEN", ""))
    delete_token = os.environ.get("REVIEWS_DELETE_TOKEN", "")
    gh("issue", "comment", str(n), "--repo", repo, "--body-file", "-", input=recorded_reply(r.code, r.lecturer, bool(delete_token)))
    deleted = remove_source(n, repo, iss["node_id"], delete_token)
    print(f"#{n}: recorded {r.code} {lecturer_key(r.lecturer)}, issue {'deleted' if deleted else 'closed and locked'}")


def open_review_issues(repo: str) -> list[int]:
    found = json.loads(gh("issue", "list", "--repo", repo, "--label", LABEL_REVIEW, "--state", "open", "--limit", "100", "--json", "number"))
    return sorted(i["number"] for i in found)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--issue", type=int)
    ap.add_argument("--rebuild", action="store_true", help="process every open review issue, then rebuild and publish ratings.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--form", help="dry run: a file holding the rendered issue body")
    ap.add_argument("--data", help="dry run: directory standing in for the private data repository")
    ap.add_argument("--voter", default="tester", help="dry run: voter id")
    ap.add_argument("--out", help="dry run: where to write ratings.json")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "xmum-sair/xmum-sair.github.io"))
    ap.add_argument("--data-repo", default=os.environ.get("REVIEWS_DATA_REPO", ""))
    ap.add_argument("--work", default="_reviews")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.dry_run:
        r = parse_review(Path(args.form).read_text(encoding="utf-8"))
        problems = validate(r)
        if problems:
            print("\n".join(problems))
            return 0
        data = Path(args.data)
        record(data, r, args.voter, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        agg = aggregate(data)
        if args.out:
            Path(args.out).write_text(json.dumps(agg, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"recorded {r.code} {lecturer_key(r.lecturer)} as {args.voter}; {sum(len(c['lecturers']) for c in agg['courses'].values())} (course, lecturer) pairs")
        return 0

    token, salt = os.environ.get("REVIEWS_TOKEN") or None, os.environ.get("REVIEWS_SALT", "")
    if not salt:
        print("WARNING: REVIEWS_SALT is empty; voter hashes are weaker", file=sys.stderr)
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    delete_token = os.environ.get("REVIEWS_DELETE_TOKEN", "")

    def tidy() -> None:   # every run also clears closed review issues whose time is up
        try:
            print(f"swept {sweep(args.repo, delete_token)} closed review issue(s)")
        except Exception as e:
            print(f"sweep failed: {e}", file=sys.stderr)

    if args.issue:
        process_issue(args.issue, args.repo, work, args.data_repo, token, salt)
        tidy()
        return 0
    if args.rebuild:
        failed = 0
        for n in open_review_issues(args.repo):
            try:
                process_issue(n, args.repo, work, args.data_repo, token, salt, publish_after=False)
            except Exception as e:  # keep going; the sweep reports at the end
                print(f"#{n}: {e}", file=sys.stderr)
                failed += 1
        if not token:
            raise RuntimeError("REVIEWS_TOKEN is not set")
        data = open_data_repo(work, args.data_repo, token)
        publish(aggregate(data), work, args.repo, os.environ.get("GH_TOKEN", ""))
        print("ratings.json rebuilt")
        tidy()
        return 1 if failed else 0
    print("nothing to do: pass --issue N, --rebuild or --dry-run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
