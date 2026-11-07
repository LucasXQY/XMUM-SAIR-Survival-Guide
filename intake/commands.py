"""Maintainer commands in issue or PR comments: /place #k CODE SESSION Type [Label], /skip #k, /keep #k, /approve #k, /retry."""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from intake import CODE_RE, SESSION_RE, SUBS, clean_label

AUTHORIZED = {"OWNER", "MEMBER", "COLLABORATOR"}
WITH_K = {"place", "skip", "keep", "approve"}
KINDS = WITH_K | {"retry"}
LABEL_MAX = 40
USAGE = "/place #k 课程代码 YYYY-MM|unknown 类型 [标签] | /place #k CODE YYYY-MM|unknown Type [Label]"


@dataclass
class Command:
    kind: str
    k: int | None = None
    args: dict = field(default_factory=dict)


def authorized(association: str) -> bool:
    return association in AUTHORIZED


def _error(word: str, k: str | None = None) -> str:
    where = f" {k}" if k else ""
    return f"无法理解 /{word}{where}，请检查参数（用法：{USAGE}） | Could not read /{word}{where}; check the arguments (usage: {USAGE})"


def _parse_line(line: str) -> tuple[Command | None, str | None]:
    tok = line.split()
    word = tok[0][1:].lower()
    if word not in KINDS:
        return None, None                      # maybe another bot's command: stay silent
    if word == "retry":
        return Command("retry"), None
    if len(tok) < 2 or not re.fullmatch(r"#[0-9]{1,6}", tok[1]) or int(tok[1][1:]) < 1:
        return None, _error(word)
    k = int(tok[1][1:])
    if word != "place":
        return Command(word, k), None
    if len(tok) < 5:
        return None, _error(word, f"#{k}")
    code, session, typ = tok[2].upper(), tok[3].lower(), tok[4]
    if not CODE_RE.match(code) or not (session == "unknown" or SESSION_RE.match(session)) or typ not in SUBS:
        return None, _error(word, f"#{k}")
    args = {"code": code, "session": session, "type": typ}
    if len(tok) > 5:
        raw = tok[5]
        label = clean_label(raw)
        if any(b in raw for b in ("/", "\\")) or ".." in raw or not label or len(label) > LABEL_MAX or ".." in label:
            return None, _error(word, f"#{k}")
        args["label"] = label
    return Command("place", k, args), None


def parse(body: str) -> tuple[list[Command], list[str]]:
    cmds, errs = [], []
    for line in (body or "").splitlines():
        line = line.strip()
        if not line.startswith("/") or len(line) == 1:
            continue
        c, e = _parse_line(line)
        if c:
            cmds.append(c)
        if e:
            errs.append(e)
    return cmds, errs


def merge(override: dict | None, cmd: Command, login: str) -> dict:
    """The override for one file after a command; always a new dict."""
    o = dict(override or {})
    if cmd.kind == "skip":
        o["skip"] = True
        o.pop("keep", None)
    elif cmd.kind == "keep":
        o["keep"] = True
        o.pop("skip", None)
    elif cmd.kind == "place":
        o["place"] = {a: cmd.args[a] for a in ("code", "session", "type", "label") if a in cmd.args}
    elif cmd.kind == "approve":
        o["approved_by"] = login
    return o
