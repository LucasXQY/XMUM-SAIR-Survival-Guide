"""Per-upload cache on the bot-state branch. That branch is public and its commits are permanent, so everything is
scrubbed before it is written: redactions keep page and position only, and free-text notes that look personal are blanked."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "llm"))
sys.path.insert(0, str(HERE))
import claude_check as cc
from intake import PII_RE

NOTE_KEYS = ("summary", "notes", "note")


def _scrub(v):
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if k in NOTE_KEYS and isinstance(x, str):
                out[k] = "" if PII_RE.search(x) else x
            elif k in NOTE_KEYS and isinstance(x, list):
                out[k] = ["" if isinstance(i, str) and PII_RE.search(i) else _scrub(i) for i in x]
            elif k == "redactions" and isinstance(x, list):
                out[k] = [{a: _scrub(b) for a, b in r.items() if a != "text"} if isinstance(r, dict) else _scrub(r) for r in x]
            else:
                out[k] = _scrub(x)
        return out
    if isinstance(v, list):
        return [_scrub(i) for i in v]
    return copy.deepcopy(v)


def scrub(data: dict) -> dict:
    """A deep copy that is safe to publish: no redaction text, no personal-looking summary/notes/note. The input is untouched."""
    return _scrub(data)


class IntakeCache:
    def __init__(self, repo: str, issue: int, gh=cc._gh):
        self.repo, self.issue, self.gh = repo, issue, gh
        self.name = f"intake-cache/issue-{int(issue)}.json"
        self._file = cc.StateFile(repo, self.name, gh)

    def load(self) -> dict:
        return self._file.read()[0]

    def save(self, data: dict) -> None:
        clean = scrub(data)
        msg = f"intake-cache: issue {int(self.issue)}"
        _, sha = self._file.read()
        try:
            self._file.write(clean, sha, msg)
        except cc.Conflict:
            stored, sha = self._file.read()
            merged = dict(clean)
            merged["overrides"] = {**(stored.get("overrides") or {}), **(clean.get("overrides") or {})}
            self._file.write(merged, sha, msg)   # a second Conflict propagates

    def delete(self) -> None:
        _, sha = self._file.read()
        if not sha:
            return
        body = {"message": f"intake-cache: drop issue {int(self.issue)}", "branch": cc.STATE_BRANCH, "sha": sha}
        try:
            self.gh("api", "-X", "DELETE", f"repos/{self.repo}/contents/{self.name}", "--input", "-", input=json.dumps(body))
        except RuntimeError as e:
            if "404" not in str(e):
                raise
