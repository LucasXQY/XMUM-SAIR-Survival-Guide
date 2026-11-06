"""把 GitHub 表单时期的评价搬到 Cloudflare：从私有数据仓库读出每一票（匿名哈希、分数、学期、时间），交给 Worker 的导入接口。
可以重复运行：同一票只保留较新的那份。部署工作流 assistant.yml 在部署后自动跑一次。
Moves the votes from the GitHub-form days to Cloudflare: reads every vote (anonymous hash, scores, session, time) from the
private data repository and hands them to the Worker's import endpoint. Safe to rerun: the newer copy of a vote wins.
The deploy workflow (assistant.yml) runs it after each deploy.

环境 | Env: REVIEWS_TOKEN, REVIEWS_DATA_REPO (the private repository), REVIEWS_ADMIN_TOKEN, ASSISTANT_URL (the Worker)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def legacy_votes(data_root: Path) -> list[dict]:
    """votes/<CODE>/<lecturer-key>.json → one entry per vote, voter id unchanged (a salted hash of the GitHub account)."""
    out = []
    for f in sorted((data_root / "votes").glob("*/*.json")) if (data_root / "votes").is_dir() else []:
        doc = json.loads(f.read_text(encoding="utf-8"))
        for voter, v in doc.get("votes", {}).items():
            out.append({"code": doc["code"], "name": doc["name"], "session": v.get("session", ""), "at": v.get("at", ""),
                        "scores": v.get("scores", {}), "voter": voter})
    return out


def chunks(items: list, n: int) -> list[list]:
    return [items[i:i + n] for i in range(0, len(items), n)]


def post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    token, repo = os.environ.get("REVIEWS_TOKEN", ""), os.environ.get("REVIEWS_DATA_REPO", "")
    admin, worker = os.environ.get("REVIEWS_ADMIN_TOKEN", ""), os.environ.get("ASSISTANT_URL", "").rstrip("/")
    if not (token and repo and admin and worker):
        print("legacy import skipped: REVIEWS_TOKEN, REVIEWS_DATA_REPO, REVIEWS_ADMIN_TOKEN and ASSISTANT_URL are all needed")
        return 0
    sys.path.insert(0, str(HERE))
    from reviews import open_data_repo
    data = open_data_repo(Path(tempfile.mkdtemp()), repo, token)
    votes = legacy_votes(data)
    imported = sum(post(f"{worker}/admin/api", {"token": admin, "op": "import", "votes": c})["imported"] for c in chunks(votes, 200))
    print(f"{len(votes)} legacy votes read, {imported} accepted by the Worker")
    return 0


if __name__ == "__main__":
    sys.exit(main())
