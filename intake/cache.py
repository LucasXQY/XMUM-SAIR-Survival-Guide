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
WHAT_MAX = 40


def _note(v):
    """Every string beneath a summary/notes/note key is free text: blank the ones that look personal."""
    if isinstance(v, str):
        return "" if PII_RE.search(v) else v
    if isinstance(v, dict):
        return {k: _note(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_note(x) for x in v]
    return copy.deepcopy(v)


def _what(v):
    if not isinstance(v, str):
        return v
    return "" if PII_RE.search(v) else v[:WHAT_MAX]


def _redaction(r):
    if not isinstance(r, dict):
        return _scrub(r)
    return {a: (_what(b) if a == "what" else _scrub(b)) for a, b in r.items() if a != "text"}


def _scrub(v):
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if k in NOTE_KEYS:
                out[k] = _note(x)
            elif k == "redactions" and isinstance(x, list):
                out[k] = [_redaction(r) for r in x]
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
