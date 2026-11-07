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
from intake import VALUE_RE, personal

NOTE_KEYS = ("summary", "notes", "note", "weighting", "lecturers")   # Claude's free text
WHAT_MAX = 40
TRIES = 5          # writes retried after a Conflict


def _note(v):
    """Every string beneath a NOTE_KEYS key (summary, notes, note, weighting, lecturers) is free text: blank the ones
    that look personal (a keyword or a value: intake.personal)."""
    if isinstance(v, str):
        return "" if personal(v) else v
    if isinstance(v, dict):
        return {k: _note(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_note(x) for x in v]
    return copy.deepcopy(v)


def _what(v):
    """A redaction's label ("学号 | student ID"): blank when it holds a value (intake.VALUE_RE: an ID, an email, a phone
    number, a run of 6+ digits), else capped. Category words are the label, so keywords are not held against it."""
    if not isinstance(v, str):
        return v
    return "" if VALUE_RE.search(v) or VALUE_RE.search(v[:WHAT_MAX]) else v[:WHAT_MAX]


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

    def save(self, data: dict, keep_stored_overrides: bool = True) -> None:
        """A rebuild's results, scrubbed. Only commands change `overrides` (update_overrides), so by default the
        overrides stored at write time stand and the run's copy, read minutes earlier, is ignored; the run's other keys
        replace the stored ones. Each try reads the file and writes with that sha: a Conflict means someone wrote in
        between, so it reads and merges again, up to TRIES times (then the Conflict propagates).
        keep_stored_overrides=False writes `data` as given, overrides included."""
        msg = f"intake-cache: issue {int(self.issue)}"
        for _ in range(TRIES):
            stored, sha = self._file.read()
            out = dict(data)
            if keep_stored_overrides:
                out.pop("overrides", None)
                out = {**stored, **out}
                if "overrides" in stored:
                    out["overrides"] = stored["overrides"]
            try:
                self._file.write(scrub(out), sha, msg)
                return
            except cc.Conflict:
                continue
        raise cc.Conflict(f"{self.name} kept changing")

    def update_overrides(self, change) -> dict | None:
        """Compare-and-swap of `overrides` alone, for comment commands. `change(data)` gets a copy of the stored file
        and returns the new overrides (None: nothing to write); they are written with the sha that copy was read with,
        every other key exactly as read. On a Conflict (a rebuild saved in between) the file is read again and `change`
        applied again, up to TRIES times. Returns the overrides written, or None."""
        msg = f"intake-cache: commands on issue {int(self.issue)}"
        for _ in range(TRIES):
            stored, sha = self._file.read()
            new = change(copy.deepcopy(stored))
            if new is None:
                return None
            try:
                self._file.write(scrub({**stored, "overrides": new}), sha, msg)
                return new
            except cc.Conflict:
                continue
        raise cc.Conflict(f"{self.name} kept changing")

    def update(self, change) -> dict | None:
        """Compare-and-swap of the whole file, for `/retry`: `change(data)` gets a copy of the stored file and returns
        the new contents (None: nothing to write), written scrubbed with the sha that copy was read with. On a Conflict
        the file is read again and `change` applied again, up to TRIES times. Returns what was written, or None."""
        msg = f"intake-cache: /retry on issue {int(self.issue)}"
        for _ in range(TRIES):
            stored, sha = self._file.read()
            new = change(copy.deepcopy(stored))
            if new is None:
                return None
            try:
                self._file.write(scrub(new), sha, msg)
                return new
            except cc.Conflict:
                continue
        raise cc.Conflict(f"{self.name} kept changing")

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
