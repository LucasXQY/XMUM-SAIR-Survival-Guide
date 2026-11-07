"""Checks for intake/dedupe.py and its effect in decide(). Run from the repo root: python intake/test_dedupe.py (no network)."""
import pathlib, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import dedupe
import decide
import intake
from items import Item

A = "Final Examination COM107 Circuits April 2022 Question 1 find the current"
CLEAN = decide.Check(answers="no", marking_scheme="no", personal_data="no", summary="", notes="")
SORT = decide.Sort("COM107", "Circuits", "2022-04", "Past-Papers", "Final", "Final", "", True, "", True, "")


def pdf(path, text):
    import fitz
    d = fitz.open()
    pg = d.new_page()
    if text:
        pg.insert_textbox(fitz.Rect(40, 40, 550, 800), text)
    d.save(str(path)); d.close()
    return path


def item(text, scanned=False, k=1):
    return Item(k, "a.pdf", pathlib.Path("a.pdf"), "0" * 64, "pdf", 1, scanned, [text] if text else [])


def repo():
    root = pathlib.Path(tempfile.mkdtemp())
    course = root / "EEE" / "COM107_Circuits"
    (course / "Past-Papers").mkdir(parents=True)
    return root, course


def test_similarity_bands():
    assert dedupe.classify(dedupe.similarity(A, A)) == "same"
    assert dedupe.classify(dedupe.similarity(A, A.replace("April", "September").replace("current", "voltage"))) == "ask"
    assert dedupe.classify(dedupe.similarity(A, "Lab manual for oscilloscopes")) == "different"
    assert dedupe.classify(0.9) == "same" and dedupe.classify(0.6) == "ask" and dedupe.classify(0.59) == "different"
    assert dedupe.similarity("", A) == 0.0


def test_normalise_keeps_words_of_two_or_more_characters():
    assert dedupe.normalise("Q1: A b2 -- Find the I (current)!") == ["q1", "b2", "find", "the", "current"]


def test_candidates_skip_scans_and_look_only_in_the_course_folder():
    root, course = repo()
    first = pdf(course / "Past-Papers" / "COM107_202204_Final_Question.pdf", A)
    other = root / "EEE" / "COM108_X"; other.mkdir()
    pdf(other / "COM108_202204_Final_Question.pdf", A)
    pdf(course / "Past-Papers" / "COM107_202204_Lab_Manual.pdf", "Lab manual for oscilloscopes")
    (course / "Past-Papers" / "broken.pdf").write_bytes(b"not a pdf")
    it = item(A)
    got = dedupe.candidates(it, course)
    assert [g[0] for g in got] == ["EEE/COM107_Circuits/Past-Papers/" + first.name] and got[0][1] >= 0.9
    assert dedupe.candidates(it, course, root) == got
    assert dedupe.candidates(item(A, scanned=True), course) == [] and dedupe.candidates(item(""), course) == []
    assert dedupe.candidates(it, None) == []


def test_candidates_best_first():
    root, course = repo()
    pdf(course / "Past-Papers" / "b.pdf", A.replace("April", "September").replace("current", "voltage"))
    pdf(course / "Past-Papers" / "a.pdf", A)
    got = dedupe.candidates(item(A), course)
    assert [p.split("/")[-1] for p, _ in got] == ["a.pdf", "b.pdf"] and got[0][1] > got[1][1]


def test_next_set_and_next_version():
    root, course = repo()
    d = course / "Past-Papers"
    assert dedupe.next_set(course, "COM107", "2022-04", "Final") == "B"
    (d / "COM107_202204_Final_Question.pdf").write_text("x")
    assert dedupe.next_set(course, "COM107", "2022-04", "Final") == "B"
    (d / "COM107_202204_Final_SetB_Question.pdf").write_text("x")
    assert dedupe.next_set(course, "COM107", "2022-04", "Final") == "C"
    (d / "COM107_202204_Midterm_SetC_Question.pdf").write_text("x")      # another assessment: ignored
    assert dedupe.next_set(course, "COM107", "2022-04", "Final") == "C"
    assert dedupe.next_set(course, "COM107", "unknown", "Final") == "B"
    assert dedupe.next_version(course, "COM107", "2022-04", "Syllabus") == 2
    (d / "COM107_202204_Syllabus.pdf").write_text("x")
    assert dedupe.next_version(course, "COM107", "2022-04", "Syllabus") == 2
    (d / "COM107_202204_Syllabus_v2.pdf").write_text("x")
    assert dedupe.next_version(course, "COM107", "2022-04", "Syllabus") == 3


def test_decide_variant_set_for_past_papers():
    d = decide.decide(item(A), SORT, CLEAN, intake.Form(), None, None, {"set": "B"})
    assert d.outcome == "commit" and d.set == "B" and "new_set" in d.flags and d.label == "Final"
    assert decide.file_name(d.code, d.session, d.type, d.label, d.set, "pdf", set()) == "COM107_202204_Final_SetB_Question.pdf"


def test_decide_variant_version_and_other_types():
    d = decide.decide(item(A), SORT, CLEAN, intake.Form(), None, None, {"version": 2})
    assert d.label == "Final_v2" and d.set == "" and "new_version" in d.flags
    syl = decide.Sort("COM107", "Circuits", "2022-04", "Syllabus", "Syllabus", "", "", True, "", True, "")
    d = decide.decide(item(A), syl, CLEAN, intake.Form(), None, None, {"version": 3})
    assert decide.file_name(d.code, d.session, d.type, d.label, d.set, "pdf", set()) == "COM107_202204_Syllabus_v3.pdf"
    d = decide.decide(item(A), syl, CLEAN, intake.Form(), None, None, {"set": "B"})
    assert d.label == "Syllabus_SetB"


def test_decide_variant_ignored_unless_committed_or_inbox_and_positional_compatible():
    d = decide.decide(item(A), SORT, CLEAN, intake.Form(), {"skip": True}, None, {"set": "B"})
    assert d.outcome == "skip" and "new_set" not in d.flags
    d = decide.decide(item(A), SORT, CLEAN, intake.Form(), None, "EEE/x.pdf", {"set": "B"})
    assert d.outcome == "skip" and "EEE/x.pdf" in d.reason
    d = decide.decide(item(A), SORT, None, intake.Form(), None, None, {"set": "B"})
    assert d.outcome == "review" and d.set == "" and "new_set" not in d.flags
    d = decide.decide(item(A), SORT, CLEAN, intake.Form(), None, None)
    assert d.set == "" and d.label == "Final" and not {"new_set", "new_version"} & set(d.flags)


def test_candidates_cache_reads_each_pdf_once():
    import fitz
    root, course = repo()
    pdf(course / "Past-Papers" / "a.pdf", A)
    pdf(course / "Past-Papers" / "b.pdf", "Lab manual for oscilloscopes")
    opens, real = [], fitz.open
    fitz.open = lambda *a, **k: (opens.append(a), real(*a, **k))[1]
    try:
        cache = {}
        first = dedupe.candidates(item(A), course, cache=cache)
        n = len(opens)
        assert n == 2 and len(cache) == 2
        assert dedupe.candidates(item(A), course, cache=cache) == first and len(opens) == n
    finally:
        fitz.open = real


def test_chinese_only_pages_match():
    zh = "期末考试 电路分析 第一题 求电流"
    assert dedupe.normalise(zh)[:2] == ["期", "末"] and dedupe.classify(dedupe.similarity(zh, zh)) == "same"
    assert dedupe.classify(dedupe.similarity(zh, "实验手册 示波器使用")) == "different"


def test_long_labels_keep_their_suffix_and_metacharacters_are_safe():
    long = "A" * 40
    srt = decide.Sort("COM107", "C", "2022-04", "Notes", long, "", "", True, "", True, "")
    d = decide.decide(item(A), srt, CLEAN, intake.Form(), None, None, {"version": 2})
    assert d.label.endswith("_v2") and len(d.label) <= decide.LABEL_MAX and d.label != long
    d = decide.decide(item(A), srt, CLEAN, intake.Form(), None, None, {"set": "B"})
    assert d.label.endswith("_SetB") and len(d.label) <= decide.LABEL_MAX
    root, course = repo()
    name = decide.file_name("COM107", "2022-04", "Notes", "Lab(2)+", "", "pdf", set())
    (course / name).write_text("x")
    assert dedupe.next_version(course, "COM107", "2022-04", "Lab(2)+") == 2
    assert dedupe.next_set(course, "COM107", "2022-04", "Lab(2)+") == "B"


def test_bad_variants_are_ignored():
    for v in ({"version": "x"}, {"version": 1}, {"version": True}, {"set": "AB"}, {"set": "1"}, {"set": 5}, "B", []):
        d = decide.decide(item(A), SORT, CLEAN, intake.Form(), None, None, v)
        assert d.set == "" and d.label == "Final" and not {"new_set", "new_version"} & set(d.flags), v


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
