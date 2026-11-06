"""每周查坏链接：生成一遍网站，检查站内链接、打包下载、外部链接；有问题就开（或更新）一个 Issue，没问题就关掉它。
Weekly link check: builds the site, checks internal links, the per-session zips and external links; opens (or updates)
an issue when something is broken and closes it when everything works again.

用法 | Usage:  python scripts/check_links.py [--dry-run]      （工作流 links.yml 每周一运行 | run weekly by links.yml）
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = os.environ.get("GITHUB_REPOSITORY", "xmum-sair/xmum-sair.github.io")
LABEL, TITLE = "link-check", "坏链接 | Broken links"
# pages that turn automated checkers away but work in a browser
REFUSE_BOTS = {"https://github.com/signup"}
# links that are checked another way: repo files (the build's own check), zips (below), prefilled forms
SKIP_RE = re.compile(r"/blob/main/|raw\.githubusercontent\.com|/releases/download/|/issues/new|/discussions/new|/discussions\?")


def internal(site: Path, prefix: str = "/") -> list[tuple[str, str]]:
    """(page, href) for every site-relative link whose target file does not exist."""
    bad = []
    for page in sorted(site.rglob("*.html")):
        for href in re.findall(r'href="([^"]*)"', page.read_text(encoding="utf-8")):
            href = html.unescape(href)
            if not href.startswith(prefix) or href.startswith("//"):
                continue
            rel = href[len(prefix):].split("#")[0].split("?")[0]
            target = site / rel / "index.html" if rel == "" or rel.endswith("/") else site / rel
            if not target.is_file():
                bad.append((page.relative_to(site).as_posix(), href))
    return bad


def external_hrefs(site: Path) -> set[str]:
    out = set()
    for page in site.rglob("*.html"):
        for h in re.findall(r'href="(https?://[^"]+)"', page.read_text(encoding="utf-8")):
            h = html.unescape(h)
            if not SKIP_RE.search(h):
                out.add(h)
    return out


def _fetch(url: str):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "xmum-sair-link-check"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except Exception as e:
        return getattr(e, "code", None) or type(e).__name__


def external(hrefs: set[str], fetch=_fetch) -> list[tuple[str, object]]:
    urls = sorted(h for h in hrefs if h not in REFUSE_BOTS)
    with ThreadPoolExecutor(8) as ex:
        return [(u, s) for u, s in zip(urls, ex.map(fetch, urls)) if s != 200]


def missing_zips(linked: set[str], assets: list[str]) -> list[str]:
    return sorted(linked - set(assets))


def report(dead: list, broken: list, zips: list) -> str:
    if not (dead or broken or zips):
        return ""
    parts = ["机器人每周检查一次网站链接，下面是这次发现的问题。修好后下次检查会自动关闭这个 Issue。",
             "The weekly link check found the problems below; the next check closes this issue once they are fixed.", ""]
    if dead:
        parts += ["## 站内死链 | Dead internal links", "", "| 页面 / Page | 链接 / Link |", "|---|---|"]
        parts += [f"| `{p}` | `{h}` |" for p, h in dead[:100]] + [""]
    if broken:
        parts += ["## 外部链接打不开 | External links failing", "", "| 链接 / Link | 结果 / Result |", "|---|---|"]
        parts += [f"| {u} | `{s}` |" for u, s in broken[:100]] + [""]
    if zips:
        parts += ["## 缺少打包下载 | Missing zips", "", "运行一次 Actions → downloads → Run workflow。| Run Actions → downloads once.", ""]
        parts += [f"- `{z}`" for z in zips[:100]]
    return "\n".join(parts) + "\n"


def gh(*args: str, input: str | None = None) -> str:
    r = subprocess.run(["gh", *args], text=True, capture_output=True, encoding="utf-8", input=input)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}: {(r.stderr or r.stdout).strip()[-500:]}")
    return r.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print the report, touch no issue")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(ROOT / "site"))
    import build
    out = Path(tempfile.mkdtemp()) / "_site"
    site = build.build(ROOT, out, "/")
    dead = internal(out, "/")
    broken = external(external_hrefs(out))
    assets = json.loads(gh("api", f"repos/{REPO}/releases/tags/downloads", "--jq", "[.assets[].name]") or "[]")
    zips = missing_zips({f"{c.code}_{s}.zip" for c in site.courses for s in c.sessions}, assets)
    text = report(dead, broken, zips)
    print(text or "all links work")
    if args.dry_run:
        return 0
    found = json.loads(gh("issue", "list", "--repo", REPO, "--label", LABEL, "--state", "open", "--json", "number"))
    if text:
        if found:
            gh("issue", "edit", str(found[0]["number"]), "--repo", REPO, "--body-file", "-", input=text)
        else:
            gh("label", "create", LABEL, "--repo", REPO, "--color", "D93F0B", "--description", "每周链接检查 | weekly link check", "--force")
            gh("issue", "create", "--repo", REPO, "--title", TITLE, "--label", LABEL, "--body-file", "-", input=text)
    elif found:
        gh("issue", "close", str(found[0]["number"]), "--repo", REPO, "--comment", "这周的检查全部通过 | This week's check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
