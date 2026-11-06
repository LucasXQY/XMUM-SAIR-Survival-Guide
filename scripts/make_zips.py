"""Zip every <course>/<session>/ folder that has material into <out>/<CODE>_<session>.zip.

用法 / Usage:  python scripts/make_zips.py [_zips]

工作流 .github/workflows/downloads.yml 在 main 的资料变动后运行它，并把 zip 上传到名为 downloads 的 Release；
网站课程页的「打包下载」按钮指向那些文件。
The downloads workflow runs this after material changes on main and uploads the zips to the
release named `downloads`; the site's per-session download buttons point at them.
"""
import pathlib
import sys
import zipfile

root = pathlib.Path(__file__).resolve().parents[1]
out = root / (sys.argv[1] if len(sys.argv) > 1 else "_zips")
out.mkdir(exist_ok=True)
n = 0
for prog in ("EEE", "AIT", "ROBO", "GE"):
    for course in sorted((root / prog).glob("*_*")):
        if not course.is_dir():
            continue
        code = course.name.split("_", 1)[0]
        for sess in sorted(p for p in course.iterdir() if p.is_dir()):
            files = sorted(f for f in sess.rglob("*") if f.is_file() and not f.name.startswith("."))
            if not files:
                continue
            with zipfile.ZipFile(out / f"{code}_{sess.name}.zip", "w", zipfile.ZIP_DEFLATED) as zf:
                for f in files:
                    zf.write(f, f.relative_to(sess).as_posix())
            n += 1
print(f"{n} zips -> {out}")
