"""每周提醒待审的评价：有被标记、还没审的票就开（或更新）一个 Issue，附管理页链接；全部审完就关掉它。
Weekly reminder about flagged reviews: opens or updates an issue with the admin page link while flagged votes wait,
and closes it once none are left. Run by .github/workflows/review-queue.yml.

环境 | Env: GH_TOKEN, ASSISTANT_URL (the Worker), REVIEWS_ADMIN_TOKEN
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY", "xmum-sair/xmum-sair.github.io")
LABEL, TITLE = "review-queue", "待审评价 | Reviews to check"
FLAGS = {"burst": "某门课某位老师一小时内突增 | burst for one course and lecturer",
         "new_name": "名单外的老师或课程 | lecturer or course not on the site list"}


def issue_text(summary: dict, admin_url: str) -> str | None:
    if not summary.get("unreviewed"):
        return None
    rows = "\n".join(f"- {FLAGS.get(k, k)}：{n}" for k, n in sorted(summary.get("by_flag", {}).items()))
    return (f"有 {summary['unreviewed']} 票被标记、还没审。这些票已经照常计入平均分，名单外的老师名在网站上暂时显示为「待确认」。"
            f"到管理页逐个保留或丢弃：{admin_url}（口令是 secret `REVIEWS_ADMIN_TOKEN`）。\n\n"
            f"{summary['unreviewed']} flagged votes wait for review. They already count; unlisted lecturer names show as "
            f"\"unconfirmed\" on the site. Keep or drop them on the admin page: {admin_url} (token: the `REVIEWS_ADMIN_TOKEN` secret).\n\n"
            f"{rows}\n\n共 {summary.get('total', 0)} 票，已丢弃 {summary.get('dropped', 0)} 票 | "
            f"{summary.get('total', 0)} votes in all, {summary.get('dropped', 0)} dropped. 每周一更新 | Updated every Monday.\n")


def gh(*args: str, input: str | None = None) -> str:
    r = subprocess.run(["gh", *args], text=True, capture_output=True, encoding="utf-8", input=input)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}: {(r.stderr or r.stdout).strip()[-500:]}")
    return r.stdout.strip()


def main() -> int:
    worker, admin = os.environ.get("ASSISTANT_URL", "").rstrip("/"), os.environ.get("REVIEWS_ADMIN_TOKEN", "")
    if not (worker and admin):
        print("skipped: ASSISTANT_URL and REVIEWS_ADMIN_TOKEN are needed")
        return 0
    req = urllib.request.Request(f"{worker}/admin/api", data=json.dumps({"token": admin, "op": "summary"}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        summary = json.loads(r.read().decode("utf-8"))
    text = issue_text(summary, f"{worker}/admin")
    print(text or "nothing to check")
    found = json.loads(gh("issue", "list", "--repo", REPO, "--label", LABEL, "--state", "open", "--json", "number"))
    if text and found:
        gh("issue", "edit", str(found[0]["number"]), "--repo", REPO, "--body-file", "-", input=text)
    elif text:
        gh("label", "create", LABEL, "--repo", REPO, "--color", "FBCA04", "--description", "待审的课程评价 | flagged reviews", "--force")
        gh("issue", "create", "--repo", REPO, "--title", TITLE, "--label", LABEL, "--body-file", "-", input=text)
    elif found:
        gh("issue", "close", str(found[0]["number"]), "--repo", REPO, "--comment", "都审完了 | All checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
