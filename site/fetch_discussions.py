"""拉取讨论区的帖子给网站用（pages.yml 在构建前运行）。| Fetch discussion posts for the site (pages.yml runs it before the build).

用法 | Usage:  python site/fetch_discussions.py _data/discussions.json      (needs GH_TOKEN with discussions: read)

只要帖子标题、链接、时间、评论数、标签；giscus 为每个页面建的讨论串和被审核锁定的帖子不列出。
Only titles, links, dates, comment counts and labels; giscus page threads and posts locked by moderation are left out.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = os.environ.get("GITHUB_REPOSITORY", "xmum-sair/xmum-sair.github.io")
PAGE_THREAD_AUTHORS = {"giscus", "giscus[bot]"}
QUERY = """query($owner: String!, $name: String!) { repository(owner: $owner, name: $name) {
  discussions(first: 100, orderBy: {field: UPDATED_AT, direction: DESC}) { nodes {
    number title url createdAt updatedAt locked author { login } comments { totalCount } labels(first: 10) { nodes { name } } } } } }"""


def shape(nodes: list[dict]) -> list[dict]:
    out = []
    for n in nodes:
        if n.get("locked") or (n.get("author") or {}).get("login") in PAGE_THREAD_AUTHORS:
            continue
        out.append({"number": n["number"], "title": n["title"], "url": n["url"], "created": n["createdAt"],
                    "updated": n["updatedAt"], "comments": (n.get("comments") or {}).get("totalCount", 0),
                    "labels": [l["name"] for l in (n.get("labels") or {}).get("nodes", [])]})
    return out


def main(argv: list[str] | None = None) -> int:
    dest = Path((argv or sys.argv[1:] or ["_data/discussions.json"])[0])
    owner, name = REPO.split("/")
    try:
        raw = subprocess.run(["gh", "api", "graphql", "-f", f"query={QUERY}", "-f", f"owner={owner}", "-f", f"name={name}"],
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
        posts = shape(json.loads(raw)["data"]["repository"]["discussions"]["nodes"])
    except Exception as e:   # the site still builds; the discussion page says the list is unavailable
        print(f"WARNING: discussions unavailable: {e}", file=sys.stderr)
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(posts, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(posts)} discussion posts -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
