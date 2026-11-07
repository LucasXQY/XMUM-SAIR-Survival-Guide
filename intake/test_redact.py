"""Checks for intake/redact.py. Run from the repo root: python intake/test_redact.py (no network needed)."""
import json, math, os, pathlib, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fitz
import redact


def tmp(): return pathlib.Path(tempfile.mkdtemp())


def pdf_pages(pages, rotate=0):
    """A PDF with one text line (or lines, split at "\\n") per page; every page rotated by `rotate`."""
    d = fitz.open()
    for t in pages:
        pg = d.new_page()
        if t: pg.insert_text((72, 72), t)
        if rotate: pg.set_rotation(rotate)
    path = tmp() / "in.pdf"; d.save(path); d.close()
    return path


def image_page(rotate=0, mark=True):
    """A "scanned" A4 page: one light-grey image filling the page, with (when `mark`) a dark block, a signature, at
    10–30 % across and 10–20 % down the unrotated page."""
    pix = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 300, 400), 0)
    pix.clear_with(235)
    if mark: pix.set_rect(fitz.IRect(30, 40, 90, 80), (40,))
    d = fitz.open(); pg = d.new_page(width=595, height=842)
    pg.insert_image(pg.rect, pixmap=pix)
    if rotate: pg.set_rotation(rotate)
    path = tmp() / "scan.pdf"; d.save(path); d.close()
    return path


def text(path, page):
    with fitz.open(path) as d: return d[page - 1].get_text()


def _gray(path, page, dpi=40):
    with fitz.open(path) as d: return d[page - 1].get_pixmap(colorspace=fitz.csGRAY, dpi=dpi)


def mean_pixel(path, page, region):
    """Mean grey value (0 black, 255 white) of the page as displayed, over `region` given as fractions of its width and
    height (x0, y0, x1, y1)."""
    pix = _gray(path, page)
    x0, y0, x1, y1 = (int(round(f * n)) for f, n in zip(region, (pix.width, pix.height) * 2))
    vals = [pix.samples[y * pix.stride + x] for y in range(y0, y1) for x in range(x0, x1)]
    return sum(vals) / len(vals)


def black_share(path, page):
    pix = _gray(path, page)
    vals = [pix.samples[y * pix.stride + x] for y in range(pix.height) for x in range(pix.width)]
    return sum(v < 20 for v in vals) / len(vals)


def _text(page, s): return {"page": page, "kind": "text", "text": s, "box": [0, 0, 0, 0], "what": "学号 | student ID"}


def _box(page, b): return {"page": page, "kind": "box", "text": "", "box": b, "what": "签名 | signature"}


# ---- the brief's checks

def test_text_redaction_removes_the_strings():
    p = pdf_pages(["Name: Tan Ah Kow   ID: EEE2109300", "Question 1"]); out = tmp() / "o.pdf"
    r = redact.apply(p, out, [{"page": 1, "kind": "text", "text": "EEE2109300"}, {"page": 1, "kind": "text", "text": "Tan Ah Kow"}])
    assert r.ok and "EEE2109300" not in text(out, 1) and "Tan Ah Kow" not in text(out, 1) and "Question 1" in text(out, 2)
    assert redact.text_gone(out, [{"page": 1, "kind": "text", "text": "EEE2109300"}])
    assert r.out == out and r.box_pages == [] and r.problems == [] and len(r.rects) == 2


def test_a_string_split_across_lines_is_still_removed_or_refused():        # Review Focus 2
    p = pdf_pages(["Name: Tan Ah\nKow"]); out = tmp() / "o.pdf"
    r = redact.apply(p, out, [{"page": 1, "kind": "text", "text": "Tan Ah Kow"}])
    assert (r.ok and all(w not in text(out, 1) for w in ("Tan", "Kow"))) or not r.ok


def test_missing_text_fails_closed_without_echoing_it():
    r = redact.apply(pdf_pages(["Question 1"]), tmp() / "o.pdf", [{"page": 1, "kind": "text", "text": "EEE2109300"}])
    assert not r.ok and "EEE2109300" not in " ".join(r.problems)


def test_box_redaction_blackens_the_pixels_and_is_clamped():
    p = image_page(); out = tmp() / "o.pdf"
    r = redact.apply(p, out, [{"page": 1, "kind": "box", "box": [100, 100, 300, 200]}, {"page": 1, "kind": "box", "box": [-50, 950, 1200, 1100]}])
    assert r.ok and r.box_pages == [1] and mean_pixel(out, 1, (0.12, 0.12, 0.28, 0.18)) < 20 and mean_pixel(out, 1, (0.5, 0.5, 0.6, 0.6)) > 200


def test_cached_rects_reproduce_the_redaction():
    p = pdf_pages(["ID: EEE2109300"]); a, b = tmp() / "a.pdf", tmp() / "b.pdf"
    r = redact.apply(p, a, [{"page": 1, "kind": "text", "text": "EEE2109300"}])
    assert redact.apply(p, b, [], cached_rects=r.rects).ok and "EEE2109300" not in text(b, 1)


# ---- controller rulings: validation, whole-document check, rotation, what is removed, cached rectangles

def test_malformed_redactions_fail_closed_and_write_nothing():
    p = pdf_pages(["ID: EEE2109300", "Question 1"])
    bad = [_text(0, "EEE2109300"), _text(3, "EEE2109300"), _text("1", "EEE2109300"), _text(True, "EEE2109300"),
           _text(1.0, "EEE2109300"), _text(None, "EEE2109300"), dict(_text(1, "EEE2109300"), kind="blur"),
           dict(_text(1, "EEE2109300"), kind=None), _text(1, ""), _text(1, "  \n "), dict(_text(1, ""), text=None),
           {"page": 1, "kind": "text"}, _box(1, [1, 2, 3]), _box(1, [1, 2, 3, 4, 5]), _box(1, ["1", 2, 3, 4]),
           _box(1, [0, 0, math.nan, 10]), _box(1, [0, 0, math.inf, 10]), _box(1, [True, 0, 10, 10]), _box(1, None),
           _box(1, [300, 100, 100, 200]), _box(1, [100, 100, 100, 200]), _box(1, [1100, 0, 1200, 100]),
           {"page": 1, "kind": "box"}, "EEE2109300", None, ["EEE2109300"]]
    for entry in bad:
        out = tmp() / "o.pdf"
        r = redact.apply(p, out, [_text(1, "EEE2109300"), entry])
        assert not r.ok and r.out is None and not out.exists() and r.rects == [] and r.box_pages == [], entry
        assert r.problems and all("redaction #2" in x for x in r.problems), (entry, r.problems)
        assert "EEE2109300" not in json.dumps(r.problems, ensure_ascii=False), entry
    for whole in (None, {"page": 1}, "EEE2109300"):                        # not a list at all
        out = tmp() / "o.pdf"
        r = redact.apply(p, out, whole)
        assert not r.ok and r.out is None and not out.exists() and r.problems and "EEE2109300" not in " ".join(r.problems)


def test_a_string_repeated_on_another_page_fails_the_whole_document():
    p = pdf_pages(["ID: EEE2109300", "Question 1", "Footer EEE2109300"]); out = tmp() / "o.pdf"
    r = redact.apply(p, out, [_text(1, "EEE2109300")])              # the AI named page 1 only
    assert not r.ok and "EEE2109300" not in text(out, 1) and "EEE2109300" in text(out, 3)
    assert any("page 3" in x for x in r.problems) and not any("page 1 " in x for x in r.problems)
    assert "EEE2109300" not in " ".join(r.problems)
    assert not redact.text_gone(out, [_text(1, "EEE2109300")])
    both = redact.apply(p, tmp() / "o2.pdf", [_text(1, "EEE2109300"), _text(3, "EEE2109300")])
    assert both.ok and redact.text_gone(both.out, [_text(1, "EEE2109300")])


def test_text_gone_reads_through_whitespace_and_case():
    gone = lambda page, s: redact.text_gone(pdf_pages(["Question 1", page]), [_text(1, s)])
    assert gone("Question 2", "EEE2109300") and gone("", "EEE2109300")
    assert not gone("ID: EEE 2109300", "EEE2109300")                  # a space inside the ID
    assert not gone("ID: EEE2109\n300", "EEE2109300")                 # a line break inside it
    assert not gone("Name: Tan Ah\nKow", "Tan Ah Kow")
    assert not gone("HEADER TAN AH KOW", "Tan  Ah\tKow")              # another case, other whitespace in the needle
    assert not redact.text_gone(pdf_pages(["x"]), [_text(1, "")]) and not redact.text_gone(tmp() / "none.pdf", [])


def test_the_word_fallback_redacts_each_word_or_refuses():
    d = fitz.open(); pg = d.new_page()
    pg.insert_text((150, 72), "Kow"); pg.insert_text((72, 72), "Tan Ah")     # read as "Kow / Tan Ah": the whole name is not found
    pg.insert_text((72, 120), "Question 1")
    p = tmp() / "in.pdf"; d.save(p); d.close()
    out = tmp() / "o.pdf"
    r = redact.apply(p, out, [_text(1, "Tan Ah Kow")])
    assert r.ok and "Tan" not in text(out, 1) and "Kow" not in text(out, 1) and "Question 1" in text(out, 1)
    r = redact.apply(p, tmp() / "o.pdf", [_text(1, "Tan Ah Kow Binti")])        # a word that is nowhere
    assert not r.ok and any("page 1" in x for x in r.problems) and "Binti" not in " ".join(r.problems)
    r = redact.apply(p, tmp() / "o.pdf", [_text(1, "Li Xu")])                   # no word long enough to search
    assert not r.ok and any("page 1" in x for x in r.problems)


def test_the_word_fallback_checks_every_page():
    d = fitz.open(); pg = d.new_page()
    pg.insert_text((150, 72), "Kow"); pg.insert_text((72, 72), "Tan Ah")
    d.new_page().insert_text((72, 72), "Signed: Kow")
    p = tmp() / "in.pdf"; d.save(p); d.close()
    r = redact.apply(p, tmp() / "o.pdf", [_text(1, "Tan Ah Kow")])
    assert not r.ok and any("page 2" in x for x in r.problems) and "Kow" not in " ".join(r.problems)


def test_text_on_a_rotated_page_is_found_and_removed():
    for rot in (90, 180, 270):
        p = pdf_pages(["ID: EEE2109300 Question 1"], rotate=rot); out = tmp() / "o.pdf"
        r = redact.apply(p, out, [_text(1, "EEE2109300")])
        assert r.ok and "EEE2109300" not in text(out, 1) and "Question 1" in text(out, 1), rot
        x0, y0, x1, y1 = r.rects[0]["rect"]                            # unrotated page space: the text runs along y = 72
        assert x0 < x1 and y0 < 72 < y1 and y1 - y0 < 30 and x0 > 72, (rot, r.rects)


def test_a_box_on_a_rotated_page_lands_where_it_was_seen():
    for rot in (90, 180, 270):
        p = image_page(rotate=rot, mark=False); out = tmp() / "o.pdf"
        r = redact.apply(p, out, [_box(1, [100, 100, 300, 200])])           # as displayed: the top left of the page
        assert r.ok and r.box_pages == [1], rot
        assert mean_pixel(out, 1, (0.12, 0.12, 0.28, 0.18)) < 20, rot
        assert mean_pixel(out, 1, (0.5, 0.5, 0.6, 0.6)) > 200 and mean_pixel(out, 1, (0.7, 0.7, 0.9, 0.9)) > 200, rot
        assert abs(black_share(out, 1) - 0.24 * 0.14) < 0.01, (rot, black_share(out, 1))   # widened 2 % a side, nothing else
    p = image_page(rotate=90, mark=False); out = tmp() / "o.pdf"           # the box ignoring rotation would land at 80–90 % across
    redact.apply(p, out, [_box(1, [100, 100, 300, 200])])
    assert mean_pixel(out, 1, (0.82, 0.12, 0.88, 0.28)) > 200


def test_rotated_pages_with_an_offset_crop_box_are_blacked_where_seen():
    for rot in (0, 90, 180, 270):
        pix = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 300, 400), 0); pix.clear_with(235)
        d = fitz.open(); pg = d.new_page(width=600, height=800)
        pg.insert_image(pg.rect, pixmap=pix)
        pg.insert_text((150, 650), "ID: EEE2109300")
        pg.set_cropbox(fitz.Rect(50, 100, 550, 700)); pg.set_rotation(rot)
        p = tmp() / "in.pdf"; d.save(p); d.close()
        out = tmp() / "o.pdf"
        r = redact.apply(p, out, [_box(1, [100, 100, 300, 200]), _text(1, "EEE2109300")])
        assert r.ok and "EEE2109300" not in text(out, 1), rot
        assert mean_pixel(out, 1, (0.12, 0.12, 0.28, 0.18)) < 20, rot
        pix = _gray(out, 1)                              # no white hole: what was removed is covered in black (but for
        assert sum(v > 245 for v in pix.samples) / len(pix.samples) < 0.001, rot    # a sliver of whole image pixels)


def test_boxes_grow_two_percent_a_side_and_stay_on_the_page():
    inside = [(0.085, 0.15, 0.095, 0.16), (0.305, 0.15, 0.315, 0.16), (0.15, 0.085, 0.16, 0.095), (0.15, 0.205, 0.16, 0.215)]
    outside = [(0.06, 0.15, 0.07, 0.16), (0.33, 0.15, 0.34, 0.16), (0.15, 0.06, 0.16, 0.07), (0.15, 0.23, 0.16, 0.24)]
    for rot in (0, 90):
        p = image_page(rotate=rot, mark=False); out = tmp() / "o.pdf"
        r = redact.apply(p, out, [_box(1, [100, 100, 300, 200]), _box(1, [-50, 950, 1200, 1100])])
        assert r.ok and all(mean_pixel(out, 1, q) < 20 for q in inside) and all(mean_pixel(out, 1, q) > 200 for q in outside), rot
        assert mean_pixel(out, 1, (0.4, 0.935, 0.6, 1.0)) < 20 and mean_pixel(out, 1, (0.4, 0.9, 0.6, 0.92)) > 200, rot  # from 93 %
        assert all(-0.01 <= x0 and x1 <= 595.01 and -0.01 <= y0 and y1 <= 842.01 for x0, y0, x1, y1 in (x["rect"] for x in r.rects)), r.rects


def test_box_redaction_removes_the_image_pixels_not_only_covers_them():
    p = image_page(); out = tmp() / "o.pdf"
    assert redact.apply(p, out, [_box(1, [80, 80, 320, 220])]).ok              # the signature block: 10–30 %, 10–20 %
    with fitz.open(out) as d:
        (xref, *_), = d[0].get_images(full=True)
        pix = fitz.Pixmap(d.extract_image(xref)["image"])
    assert min(pix.pixel(60, 60)) > 200 and min(pix.pixel(200, 300)) > 200      # the dark block is gone from the image itself


def test_rects_hold_no_text_and_reproduce_the_redaction():
    p = pdf_pages(["Name: Tan Ah Kow   ID: EEE2109300", "Question 1"]); a = tmp() / "a.pdf"
    r = redact.apply(p, a, [_text(1, "EEE2109300"), _text(1, "Tan Ah Kow"), _box(2, [500, 500, 600, 600])])
    assert r.ok and r.box_pages == [2] and len(r.rects) == 3
    assert all(set(x) == {"page", "rect"} and len(x["rect"]) == 4 and all(isinstance(v, float) for v in x["rect"]) for x in r.rects)
    flat = json.dumps(r.rects)
    assert "EEE2109300" not in flat and "Tan" not in flat and "text" not in flat
    b = tmp() / "b.pdf"
    again = redact.apply(p, b, [_text(1, "something else entirely")], cached_rects=json.loads(flat))   # redactions are ignored
    assert again.ok and again.rects == r.rects and again.out == b
    assert "EEE2109300" not in text(b, 1) and "Tan Ah Kow" not in text(b, 1) and "Question 1" in text(b, 2)
    assert again.box_pages == [1, 2]                     # which rectangle was a box is not cached: every redacted page
    s = image_page(); c, e = tmp() / "c.pdf", tmp() / "e.pdf"
    box = redact.apply(s, c, [_box(1, [100, 100, 300, 200])])
    assert redact.apply(s, e, [], cached_rects=box.rects).ok and mean_pixel(e, 1, (0.12, 0.12, 0.28, 0.18)) < 20


def test_malformed_cached_rects_fail_closed():
    p = pdf_pages(["ID: EEE2109300"])
    good = redact.apply(p, tmp() / "a.pdf", [_text(1, "EEE2109300")]).rects[0]
    for entry in ({"page": 0, "rect": good["rect"]}, {"page": 2, "rect": good["rect"]}, {"page": "1", "rect": good["rect"]},
                  {"page": 1, "rect": good["rect"][:3]}, {"page": 1, "rect": ["0", 0, 10, 10]}, {"page": 1, "rect": [0, 0, math.nan, 10]},
                  {"page": 1, "rect": [10, 0, 10, 10]}, {"page": 1}, "rect", None):
        out = tmp() / "o.pdf"
        r = redact.apply(p, out, [_text(1, "EEE2109300")], cached_rects=[good, entry])
        assert not r.ok and r.out is None and not out.exists() and any("#2" in x for x in r.problems), entry
    r = redact.apply(p, tmp() / "o.pdf", [], cached_rects={"page": 1})
    assert not r.ok and r.out is None


def test_the_original_is_never_written():
    p = pdf_pages(["Name: Tan Ah Kow   ID: EEE2109300", "Footer EEE2109300"]); before = p.read_bytes()
    redact.apply(p, tmp() / "a.pdf", [_text(1, "EEE2109300"), _text(2, "EEE2109300")])
    redact.apply(p, tmp() / "b.pdf", [_text(1, "EEE2109300")])                           # fails: page 2
    redact.apply(p, tmp() / "c.pdf", [_text(9, "EEE2109300")])                           # malformed
    r = redact.apply(p, p, [_text(1, "EEE2109300"), _text(2, "EEE2109300")])             # out is the original
    assert not r.ok and r.out is None and p.read_bytes() == before
    same = p.parent / ".." / p.parent.name / p.name                                    # the same file, spelled differently
    assert not redact.apply(p, same, [_text(1, "EEE2109300")]).ok and p.read_bytes() == before
    redact.apply(p, p.with_name(p.name.upper()), [_text(1, "EEE2109300")])              # the same file on Windows
    assert p.read_bytes() == before
    link = p.with_name("link.pdf")
    try:
        os.link(p, link)
    except OSError:
        link = None
    if link:                                                                           # a hard link to it
        r = redact.apply(p, link, [_text(1, "EEE2109300"), _text(2, "EEE2109300")])
        assert not r.ok and r.out is None and p.read_bytes() == before


def test_metadata_xmp_and_embedded_files_are_stripped():
    d = fitz.open(); d.new_page().insert_text((72, 72), "ID: EEE2109300")
    d.set_metadata({"author": "Tan Ah Kow", "title": "EEE2109300 final"})
    d.set_xml_metadata("<x:xmpmeta xmlns:x='adobe:ns:meta/'><dc>Tan Ah Kow</dc></x:xmpmeta>")
    d.embfile_add("answers.txt", b"Tan Ah Kow EEE2109300")
    p = tmp() / "in.pdf"; d.save(p); d.close()
    out = tmp() / "o.pdf"
    assert redact.apply(p, out, [_text(1, "EEE2109300")]).ok
    with fitz.open(out) as o:
        assert not any(o.metadata.get(k) for k in ("author", "title", "subject", "keywords", "creator", "producer"))
        assert o.get_xml_metadata() == "" and o.embfile_names() == []
    raw = out.read_bytes()
    assert b"Tan Ah Kow" not in raw and b"EEE2109300" not in raw


def test_unreadable_or_non_pdf_input_fails_closed():
    junk = tmp() / "x.pdf"; junk.write_bytes(b"not a pdf at all")
    png = tmp() / "x.png"; png.write_bytes(fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 10, 10), 0).tobytes("png"))
    d = fitz.open(); d.new_page().insert_text((72, 72), "ID: EEE2109300")
    locked = tmp() / "locked.pdf"; d.save(locked, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o"); d.close()
    for src in (junk, tmp() / "missing.pdf", png, locked):
        out = tmp() / "o.pdf"
        r = redact.apply(src, out, [_text(1, "EEE2109300")])
        assert not r.ok and r.out is None and not out.exists() and r.problems


def test_no_redactions_still_clears_the_metadata():
    d = fitz.open(); d.new_page().insert_text((72, 72), "Question 1"); d.set_metadata({"author": "Tan Ah Kow"})
    p = tmp() / "in.pdf"; d.save(p); d.close()
    out = tmp() / "o.pdf"
    r = redact.apply(p, out, [])
    assert r.ok and r.rects == [] and r.box_pages == [] and "Question 1" in text(out, 1)
    with fitz.open(out) as o:
        assert not o.metadata.get("author")


def test_render_draws_the_pages_as_displayed():
    p = image_page(rotate=90)
    (png,) = redact.render(p, [1])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    pix = fitz.Pixmap(png)
    assert abs(pix.width - 842 * 150 / 72) <= 1 and abs(pix.height - 595 * 150 / 72) <= 1       # landscape: rotation applied
    two = pdf_pages(["a", "b", "c"])
    assert len(redact.render(two, [3, 1], dpi=50)) == 2
    for bad in (0, 4, -1, "1"):
        try:
            redact.render(two, [bad]); assert False, bad
        except ValueError:
            pass


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests: t()
    print(f"ok {len(tests)} tests")
