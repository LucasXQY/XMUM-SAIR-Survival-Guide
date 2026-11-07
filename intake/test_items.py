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


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
