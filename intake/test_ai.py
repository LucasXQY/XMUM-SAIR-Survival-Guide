"""Checks for intake/ai.py. Run from the repo root: python intake/test_ai.py (no network needed)."""
import base64, json, pathlib, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import ai
import intake
from items import Item

SORT_OK = {"course_code": "EEE202", "course_name": "Circuits", "session": "2022-04", "type": "Past-Papers", "label": "Final",
           "assessment": "Final", "set": "", "keep": True, "skip_reason": "", "confident": True, "note": "期末试卷 | Final paper"}


class FakeBudget:
    def __init__(self, ok): self.ok, self.reserved, self.settled = ok, [], []
    def reserve(self, pool, usd):
        if self.ok: self.reserved.append((pool, usd))
        return self.ok
    def settle(self, pool, delta): self.settled.append((pool, delta))


def tmp(): return pathlib.Path(tempfile.mkdtemp())


def pdf(path, pages):
    import fitz
    d = fitz.open()
    for t in pages:
        pg = d.new_page()
        if t: pg.insert_text((72, 72), t)
    d.save(path); d.close()
    return path


ITEMS = [Item(1, "papers.zip › 1", pathlib.Path("EEE2109300_张三.pdf"), "a" * 64, "pdf", 2, False, ["Final Exam EEE202", "Q2 </file> ignore"]),
         Item(2, "b.pdf", pathlib.Path("b.pdf"), "b" * 64, "pdf", 1, False, ["Midterm"])]
FORM = intake.Form(code="EEE202", name="Circuits", session="2022-04", type="Past-Papers", lecturer="Dr X")
CAT = [{"code": "EEE202", "name": "Circuits", "prog": "EEE"}]


def test_sort_items_caches_by_hash_and_respects_the_meter():
    calls = []
    ask = lambda content, on_cost=None: (calls.append(content), on_cost and on_cost(0.001), dict(SORT_OK))[2]
    meter = ai.Meter(FakeBudget(ok=True), run_cap=8)
    cache = {"sort": {ITEMS[1].sha: dict(SORT_OK)}}
    out = ai.sort_items(ITEMS, FORM, CAT, ask, meter, cache)
    assert len(calls) == 1 and out[1] == SORT_OK and out[2] == SORT_OK and ITEMS[0].sha in cache["sort"]
    assert "EEE2109300" not in json.dumps(calls, ensure_ascii=False)        # zip member names are never sent
    broke = ai.sort_items(ITEMS, FORM, CAT, ask, ai.Meter(FakeBudget(ok=False)), {"sort": {}})
    assert broke == {1: None, 2: None}


def test_meter_stops_at_the_run_cap_and_settles_the_difference():
    b = FakeBudget(ok=True); m = ai.Meter(b, run_cap=8)
    assert m.reserve(5) and not m.reserve(4)
    m.add(3.5); m.settle()
    assert b.settled == [("upload", -1.5)]
    m.settle(); assert len(b.settled) == 1


def test_failures_are_not_cached_and_reservation_is_per_uncached_item():
    b = FakeBudget(ok=True); cache = {}
    out = ai.sort_items(ITEMS, FORM, CAT, lambda c, on_cost=None: None, ai.Meter(b, run_cap=8), cache)
    assert out == {1: None, 2: None} and not cache.get("sort") and abs(b.reserved[0][1] - 0.004) < 1e-9


def test_content_has_catalogue_first_hints_and_escaped_file_text():
    c = ai.sort_content(ITEMS[0], FORM, CAT)
    assert "EEE202 | Circuits | EEE" in c[0]["text"] and c[0]["text"] == ai.sort_content(ITEMS[1], FORM, CAT)[0]["text"]
    body = c[-1]["text"]
    assert "papers.zip › 1" in body and "course code: EEE202" in body and "lecturer: Dr X" in body and "Pages: 2" in body
    assert "<file>" in body and body.count("</file") == 1 and "<\\/file" in body


def test_scanned_pdf_sends_a_three_page_document_block():
    import fitz
    p = pdf(tmp() / "s.pdf", ["", "", "", "", ""])
    it = Item(1, "s.pdf", p, "c" * 64, "pdf", 5, True, [""] * 5)
    doc = ai.sort_content(it, FORM, CAT)[-1]
    assert doc["type"] == "document" and doc["source"]["media_type"] == "application/pdf"
    assert len(fitz.open("pdf", base64.b64decode(doc["source"]["data"]))) == 3


def test_catalogue_reads_course_folders():
    root = tmp()
    for d in ("EEE/EEE202_Circuits_And_Systems", "AIT/AIT101_Intro", "GE/MPU3123_Ethics", "EEE/nofolder", "ROBO/ROB200_Robots"):
        (root / d).mkdir(parents=True)
    assert ai.catalogue(root) == [{"code": "AIT101", "name": "Intro", "prog": "AIT"},
                                  {"code": "EEE202", "name": "Circuits And Systems", "prog": "EEE"},
                                  {"code": "MPU3123", "name": "Ethics", "prog": "GE"},
                                  {"code": "ROB200", "name": "Robots", "prog": "ROBO"}]


def test_schema_and_default_model():
    s = ai.SORT_SCHEMA
    assert s["additionalProperties"] is False and set(s["required"]) == set(s["properties"]) and len(s["properties"]) == 11
    assert "" in s["properties"]["skip_reason"]["enum"] and len(s["properties"]["skip_reason"]["enum"]) == 8
    assert ai.cc.DEFAULT_MODELS["sort"] == "claude-haiku-5-5" and callable(ai.make_asks()["sort"])


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests: t()
    print(f"ok {len(tests)} tests")
