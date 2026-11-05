"""评论审核机器人：按关键词表把辱骂、歧视和政治敏感内容折叠起来，并记一笔给维护者。
Comment moderation bot: folds abusive, discriminatory and politically sensitive content by keyword list and logs it for the maintainer.

用法 | Usage:  python moderation/moderation.py --event "$GITHUB_EVENT_PATH" [--event-name NAME] [--dry-run]
设计 | Design: moderation/DESIGN.md。测试 | Tests: python moderation/test_moderation.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORDS_DIR = HERE / "words"
HIDE = ("zh_profanity", "en_profanity", "slurs", "attacks", "sensitive")   # a hit in these folds the comment
REVIEW = ("review",)                                                         # a hit here is only logged
BOTS = {"github-actions[bot]", "giscus[bot]", "dependabot[bot]"}
MAINTAINERS = {"OWNER", "MEMBER", "COLLABORATOR"}                            # author_association values not moderated
LABEL, LOG_LABEL = "moderation", "moderation-log"
LOG_TITLE = "审核记录 | Moderation log"

NOTICE = ("上面一条内容因含有不允许的词（{cats}）被机器人折叠，维护者会看一眼。这里只谈课程：不骂人、不人身攻击、不谈政治。"
          "如果你觉得是误判，发邮件到 xieqiyi@ieee.org。\n\n"
          "The content above was folded by the bot for disallowed words ({cats}); a maintainer will take a look. "
          "This site is about courses only: no insults, no personal attacks, no politics. "
          "If you think this was a mistake, email xieqiyi@ieee.org.")
CATEGORY_NAMES = {"zh_profanity": "脏话 profanity", "en_profanity": "脏话 profanity", "slurs": "歧视 slur",
                  "attacks": "人身攻击 personal attack", "sensitive": "政治敏感 politically sensitive", "review": "待查 review"}


@dataclass
class Hit:
    category: str
    word: str


@dataclass
class Action:
    kind: str      # minimize | lock_discussion | lock_issue | label_issue | comment_discussion | comment_issue | log
    target: str    # node id, issue number or (for log) the URL
    text: str = ""


# ---------------------------------------------------------------- words and matching

def load_words(folder: Path = WORDS_DIR) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for p in sorted(folder.glob("*.txt")):
        words = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip().lower()
            if line:
                words.append(unicodedata.normalize("NFKC", line))
        out[p.stem] = words
    return out


def normalize(text: str) -> tuple[str, str]:
    """(lowercased NFKC text, the same with whitespace and punctuation removed — for CJK patterns)."""
    t = unicodedata.normalize("NFKC", text or "").lower()
    loose = re.sub(r"[\W_]+", "", t)   # \w keeps CJK characters, so only spaces and punctuation go
    return t, loose


def scan(text: str, words: dict[str, list[str]] | None = None) -> list[Hit]:
    words = words if words is not None else load_words()
    t, loose = normalize(text)
    for allowed in words.get("allow", []):
        t = t.replace(allowed, " ")
        loose = loose.replace(re.sub(r"[\W_]+", "", allowed), "")
    hits: list[Hit] = []
    for cat, ws in words.items():
        if cat == "allow":
            continue
        for w in ws:
            if re.search(r"[^\x00-\x7f]", w):                      # CJK or other non-ASCII: loose substring
                if re.sub(r"[\W_]+", "", w) in loose:
                    hits.append(Hit(cat, w))
            else:                                                   # ASCII: whole words, any whitespace between them
                pattern = r"(?<![a-z0-9])" + r"\s+".join(re.escape(p) for p in w.split()) + r"(?![a-z0-9])"
                if re.search(pattern, t):
                    hits.append(Hit(cat, w))
    return hits


# ---------------------------------------------------------------- events → actions

def subject(event_name: str, ev: dict) -> dict | None:
    """What was posted: kind, text, author, association, node id, number, url, parent discussion id."""
    if event_name == "discussion_comment" and "comment" in ev:
        c, d = ev["comment"], ev.get("discussion", {})
        return {"kind": "discussion_comment", "text": c.get("body") or "", "author": c["user"]["login"],
                "association": c.get("author_association", "NONE"), "node": c["node_id"], "number": d.get("number"),
                "url": c.get("html_url", ""), "parent": d.get("node_id", "")}
    if event_name == "discussion" and "discussion" in ev:
        d = ev["discussion"]
        return {"kind": "discussion", "text": f"{d.get('title', '')}\n{d.get('body') or ''}", "author": d["user"]["login"],
                "association": d.get("author_association", "NONE"), "node": d["node_id"], "number": d.get("number"),
                "url": d.get("html_url", ""), "parent": d["node_id"]}
    if event_name == "issues" and "issue" in ev:
        i = ev["issue"]
        return {"kind": "issue", "text": f"{i.get('title', '')}\n{i.get('body') or ''}", "author": i["user"]["login"],
                "association": i.get("author_association", "NONE"), "node": i.get("node_id", ""), "number": i["number"],
                "url": i.get("html_url", ""), "parent": ""}
    if event_name == "issue_comment" and "comment" in ev:
        c, i = ev["comment"], ev.get("issue", {})
        return {"kind": "issue_comment", "text": c.get("body") or "", "author": c["user"]["login"],
                "association": c.get("author_association", "NONE"), "node": c["node_id"], "number": i.get("number"),
                "url": c.get("html_url", ""), "parent": ""}
    return None


def plan(event_name: str, ev: dict, words: dict[str, list[str]] | None = None) -> list[Action]:
    s = subject(event_name, ev)
    if s is None or s["author"] in BOTS or s["association"] in MAINTAINERS:
        return []
    hits = scan(s["text"], words)
    if not hits:
        return []
    hide = [h for h in hits if h.category in HIDE]
    actions: list[Action] = []
    if hide:
        cats = "、".join(dict.fromkeys(CATEGORY_NAMES.get(h.category, h.category) for h in hide))
        notice = NOTICE.format(cats=cats)
        if s["kind"] == "discussion_comment":
            actions += [Action("minimize", s["node"]), Action("comment_discussion", s["parent"], notice)]
        elif s["kind"] == "discussion":
            actions += [Action("lock_discussion", s["node"]), Action("comment_discussion", s["parent"], notice)]
        elif s["kind"] == "issue":
            actions += [Action("lock_issue", str(s["number"])), Action("label_issue", str(s["number"]), LABEL),
                        Action("comment_issue", str(s["number"]), notice)]
        elif s["kind"] == "issue_comment":
            actions += [Action("minimize", s["node"]), Action("comment_issue", str(s["number"]), notice)]
    summary = ", ".join(f"{h.category}:{h.word}" for h in hits)
    verdict = "折叠 | hidden" if hide else "仅记录 | logged only"
    actions.append(Action("log", s["url"], f"{s['kind']} by @{s['author']} — {verdict} — {summary}"))
    return actions


# ---------------------------------------------------------------- GitHub side effects

def gh(*args: str, input: str | None = None) -> str:
    r = subprocess.run(["gh", *args], text=True, capture_output=True, encoding="utf-8", input=input)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])} failed: {(r.stderr or r.stdout).strip()[-1500:]}")
    return r.stdout.strip()


def graphql(query: str, **vars: str) -> str:
    args = ["api", "graphql", "-f", f"query={query}"]
    for k, v in vars.items():
        args += ["-f", f"{k}={v}"]
    return gh(*args)


def log_issue_number(repo: str) -> str:
    found = json.loads(gh("issue", "list", "--repo", repo, "--label", LOG_LABEL, "--state", "open", "--limit", "1", "--json", "number"))
    if found:
        return str(found[0]["number"])
    gh("label", "create", LOG_LABEL, "--repo", repo, "--color", "5319E7", "--description", "机器人审核记录 | Bot moderation log", "--force")
    url = gh("issue", "create", "--repo", repo, "--title", LOG_TITLE, "--label", LOG_LABEL, "--body",
             "机器人折叠或标记的内容都记在这里，一条一个评论。误判的请到原处 Unhide，然后在词表 moderation/words/ 里改。\n\n"
             "Everything the bot folded or flagged is listed here, one comment each. For a false positive, unhide it where it was "
             "posted and adjust the word lists in moderation/words/.")
    return url.rstrip("/").rsplit("/", 1)[-1]


def apply(actions: list[Action], repo: str) -> None:
    for a in actions:
        if a.kind == "minimize":
            graphql("mutation($id: ID!) { minimizeComment(input: {subjectId: $id, classifier: ABUSE}) { minimizedComment { isMinimized } } }", id=a.target)
        elif a.kind == "lock_discussion":
            graphql("mutation($id: ID!) { lockLockable(input: {lockableId: $id, lockReason: TOO_HEATED}) { lockedRecord { locked } } }", id=a.target)
        elif a.kind == "comment_discussion":
            graphql("mutation($id: ID!, $body: String!) { addDiscussionComment(input: {discussionId: $id, body: $body}) { comment { id } } }",
                    id=a.target, body=a.text)
        elif a.kind == "lock_issue":
            gh("issue", "lock", a.target, "--repo", repo, "--reason", "too_heated")
        elif a.kind == "label_issue":
            gh("label", "create", a.text, "--repo", repo, "--color", "B60205", "--description", "机器人折叠过 | Folded by the moderation bot", "--force")
            gh("issue", "edit", a.target, "--repo", repo, "--add-label", a.text)
        elif a.kind == "comment_issue":
            gh("issue", "comment", a.target, "--repo", repo, "--body-file", "-", input=a.text)
        elif a.kind == "log":
            gh("issue", "comment", log_issue_number(repo), "--repo", repo, "--body-file", "-", input=f"{a.target}\n\n{a.text}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--event", required=True, help="path of the GitHub event payload (GITHUB_EVENT_PATH)")
    ap.add_argument("--event-name", default=os.environ.get("GITHUB_EVENT_NAME", ""), help="GITHUB_EVENT_NAME")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""), help="owner/name")
    ap.add_argument("--dry-run", action="store_true", help="print the actions, call nothing")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ev = json.loads(Path(args.event).read_text(encoding="utf-8"))
    actions = plan(args.event_name, ev)
    if not actions:
        print("nothing to do")
        return 0
    for a in actions:
        print(f"{a.kind} {a.target}" + (f" — {a.text[:80]}" if a.kind == "log" else ""))
    if not args.dry_run:
        apply(actions, args.repo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
