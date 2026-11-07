"""Checks for intake/items.py. Run from the repo root: python intake/test_items.py (no network needed)."""
import shutil, sys, pathlib, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import intake
import items as items_mod


def tmp():
    return pathlib.Path(tempfile.mkdtemp())


def pdf(path, pages):
    import fitz
    d = fitz.open()
    for text in pages:
        pg = d.new_page()
        if text:
            pg.insert_text((72, 72), text + " " + "filler text " * 12)
    d.save(path); d.close()
    return path


def repo_copy():
    """A throwaway repo root with one PDF under EEE/."""
    root = tmp(); (root / "EEE" / "COM107_X" / "2022-04" / "Past-Papers").mkdir(parents=True)
    pdf(root / "EEE" / "COM107_X" / "2022-04" / "Past-Papers" / "COM107_202204_Final_Question.pdf", ["Existing paper"])
    return root


def test_items_number_files_and_hide_zip_member_names():
    w = tmp(); a = pdf(w / "张三_EEE2109300.pdf", ["Final Examination COM107", "Q2"]); b = pdf(w / "scan.pdf", ["", "", ""])
    items = items_mod.make_items([("张三_EEE2109300.pdf", a), ("scan.pdf", b)], ["papers.zip", "scan.pdf"])
    assert [i.k for i in items] == [1, 2] and items[0].source == "papers.zip › 1" and items[1].source == "scan.pdf"
    assert "EEE2109300" not in items[0].source and items[0].pages == 2 and not items[0].scanned and items[1].scanned


def test_exact_duplicates_against_the_repo_and_within_the_upload():
    root = repo_copy(); existing = next((root / "EEE").rglob("*.pdf"))
    copy = tmp() / "x.pdf"; shutil.copyfile(existing, copy)
    items = items_mod.make_items([("x.pdf", copy), ("y.pdf", copy)], ["x.pdf", "y.pdf"])
    d = items_mod.exact_duplicates(items, root)
    assert d[1] == existing.relative_to(root).as_posix() and d[2] in ("#1", d[1])


def test_duplicates_inside_the_upload_and_unique_files():
    w = tmp(); a = pdf(w / "a.pdf", ["one"]); b = pdf(w / "b.pdf", ["two"]); c = w / "c.pdf"; shutil.copyfile(a, c)
    items = items_mod.make_items([("a.pdf", a), ("b.pdf", b), ("c.pdf", c)], ["a.pdf", "b.pdf", "c.pdf"])
    assert items_mod.exact_duplicates(items, tmp()) == {3: "#1"}


def test_plain_text_and_unreadable_pdf():
    w = tmp(); t = w / "n.txt"; t.write_text("short", encoding="utf-8"); bad = w / "bad.pdf"; bad.write_bytes(b"not a pdf")
    a, b = items_mod.make_items([("n.txt", t), ("bad.pdf", bad)], ["n.txt", "bad.pdf"])
    assert a.pages == 1 and a.page_text == ["short"] and a.scanned and a.ext == "txt"
    assert b.pages == 0 and b.page_text == [] and b.scanned and len(b.sha) == 64


def test_zip_members_numbered_like_the_rejected_ones():
    import zipfile
    w = tmp(); z = w / "p.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("pic.jpg", b"\xff\xd8"); zf.writestr("张三_EEE2109300.txt", "hello")
    ok, bad, origins = intake.unpack([("p.zip", z)], w)
    assert [n for n, _ in bad] == ["p.zip › 1"] and origins == ["p.zip › 2"]
    assert items_mod.make_items(ok, origins)[0].source == "p.zip › 2"


def docx(path, text="Hello world"):
    import zipfile
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f"<w:document><w:t>{text}</w:t></w:document>")
    return path


def fake_soffice(w):
    """A stand-in for soffice as an argv list (portable): writes <stem>.pdf with two pages into --outdir."""
    script = w / "fake_soffice.py"
    script.write_text("""import sys, pathlib, fitz
a = sys.argv[1:]; out = pathlib.Path(a[a.index('--outdir') + 1]); src = pathlib.Path(a[-1])
d = fitz.open()
for t in ('First page', 'Second page'):
    d.new_page().insert_text((72, 72), t + ' ' + 'filler text ' * 12)
d.save(out / (src.stem + '.pdf'))
""", encoding="utf-8")
    return [sys.executable, str(script)]


def test_office_conversion_is_optional_and_never_touches_the_original():
    w = tmp(); d = docx(w / "a.docx")
    assert items_mod.to_pdf(d, w, soffice="definitely-not-installed") is None
    it = items_mod.make_items([("a.docx", d)], ["a.docx"], soffice="definitely-not-installed")[0]
    assert it.view is None and it.path == d
    if shutil.which("soffice"):
        assert items_mod.to_pdf(d, w).suffix == ".pdf"


def test_office_view_comes_from_the_converted_pdf():
    w = tmp(); d = docx(w / "a.docx"); before = d.read_bytes(); soffice = fake_soffice(w)
    out = items_mod.to_pdf(d, w / "out", soffice)
    assert out is not None and out.suffix == ".pdf" and out.exists() and out.parent != d.parent
    assert items_mod.to_pdf(d, w / "out", [sys.executable, "-c", "raise SystemExit(1)"]) is None
    it = items_mod.make_items([("a.docx", d)], ["a.docx"], soffice=soffice, work=w / "v")[0]
    assert it.view is not None and it.view.suffix == ".pdf" and it.path == d and it.ext == "docx"
    assert it.pages == 2 and "Second page" in it.page_text[1] and not it.scanned
    assert d.read_bytes() == before


def test_pdf_view_is_itself_and_text_files_have_none():
    w = tmp(); a = pdf(w / "a.pdf", ["one"]); t = w / "n.txt"; t.write_text("hi", encoding="utf-8")
    x, y = items_mod.make_items([("a.pdf", a), ("n.txt", t)], ["a.pdf", "n.txt"])
    assert x.view == a and y.view is None


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
