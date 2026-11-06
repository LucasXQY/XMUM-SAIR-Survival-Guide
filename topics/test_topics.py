"""Checks for topics/topics.py. Run from the repo root: python topics/test_topics.py (no network)."""
import base64, pathlib, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import topics as t


def _pdf(path, text="Fourier transform of a periodic signal. " * 20, pages=1):
    import fitz
    d = fitz.open()
    for _ in range(pages):
        pg = d.new_page()
        if text:
            pg.insert_text((72, 72), text[:90])
            pg.insert_textbox(fitz.Rect(72, 100, 520, 760), text)
    d.save(path); d.close()


def _tree():
    root = pathlib.Path(tempfile.mkdtemp())
    for rel in ["EEE/EEE301_Signals/2023-04/Notes/a.pdf", "EEE/EEE301_Signals/2023-04/Notes/b.pdf",
                "GE/G0191_Face/2023-02/Syllabus/c.pdf"]:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        _pdf(root / rel, text=f"{rel} " * 40)
    (root / "EEE/EEE301_Signals/README.md").write_text("# x", encoding="utf-8")
    (root / "EEE/EEE301_Signals/2023-04/stray.pdf").write_bytes(b"%PDF")          # not in a type folder: not indexed
    (root / "EEE/EEE301_Signals/2023-04/Notes/old.doc").write_bytes(b"\xd0\xcf")    # old format: listed, never sent
    return root


def test_course_files_follow_the_site_layout():
    files = t.course_files(_tree())
    assert sorted(files) == ["EEE/EEE301_Signals/2023-04/Notes/a.pdf", "EEE/EEE301_Signals/2023-04/Notes/b.pdf",
                             "EEE/EEE301_Signals/2023-04/Notes/old.doc", "GE/G0191_Face/2023-02/Syllabus/c.pdf"]


def test_topic_input_sends_text_or_the_scanned_pages():
    w = pathlib.Path(tempfile.mkdtemp())
    _pdf(w / "text.pdf")
    block = t.topic_input(w / "text.pdf")
    assert block["type"] == "text" and "Fourier transform" in block["text"] and block["text"].rstrip().endswith("</file>")
    _pdf(w / "scan.pdf", text="", pages=t.SCAN_PAGES + 3)                          # no text layer: send the pages themselves
    block = t.topic_input(w / "scan.pdf")
    import fitz
    assert block["type"] == "document"
    assert len(fitz.open(stream=base64.b64decode(block["source"]["data"]), filetype="pdf")) == t.SCAN_PAGES
    (w / "x.doc").write_bytes(b"\xd0\xcf")
    assert t.topic_input(w / "x.doc") is None


def test_clean_keeps_a_short_tidy_list():
    v = t.clean({"topics": [" 傅里叶变换 Fourier transform ", "傅里叶变换 Fourier transform", "", "x" * 200] + [f"t{i}" for i in range(20)],
                 "about": "信号与系统笔记 | signals notes"})
    assert v["topics"][0] == "傅里叶变换 Fourier transform" and len(v["topics"]) == t.MAX_TOPICS
    assert all(0 < len(x) <= 60 for x in v["topics"]) and v["about"] == "信号与系统笔记 | signals notes"
    assert t.clean(None) is None and t.clean({"topics": [], "about": ""}) is None


def test_update_reuses_moved_files_prunes_deleted_ones_and_respects_the_limit():
    root = _tree()
    files = t.course_files(root)
    sha_c = t.file_sha(files["GE/G0191_Face/2023-02/Syllabus/c.pdf"])
    store = {"EEE/G0191_Face/2023-02/Syllabus/c.pdf": {"sha": sha_c, "topics": ["人脸识别 face recognition"], "about": "a"},
             "EEE/gone.pdf": {"sha": "dead", "topics": ["x"], "about": "x"}}
    asked, grants = [], [True, False]

    def ask(block):
        asked.append(block)
        return {"topics": ["卷积 convolution"], "about": "笔记 | notes"}

    def take(n):
        return grants.pop(0) if grants else False
    new, stats = t.update(files, store, ask=ask, take=take, chunk=1)
    assert new["GE/G0191_Face/2023-02/Syllabus/c.pdf"]["topics"] == ["人脸识别 face recognition"]   # moved: no new call
    assert "EEE/gone.pdf" not in new and "EEE/G0191_Face/2023-02/Syllabus/c.pdf" not in new
    assert len(asked) == 1 and stats["done"] == 1 and stats["left"] == 1                          # the limit stopped the rest
    assert "EEE/EEE301_Signals/2023-04/Notes/old.doc" not in new and stats["skipped"] == 1
    again, stats2 = t.update(files, new)                                                          # no Claude: keeps what it has
    assert again == new and stats2["left"] == 1


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
    print(f"ok {len(tests)} tests")
