"""Checks for intake/decide.py. Run from the repo root: python intake/test_decide.py (no network needed)."""
import pathlib, sys
from dataclasses import replace

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import decide
import intake
from items import Item

ITEM = Item(1, "a.pdf", pathlib.Path("a.pdf"), "0" * 64, "pdf", 3, False, ["x", "y", "z"])
FORM = intake.Form()
CAT = {"COM107", "COM106"}
SORT_OK = dict(course_code="com107", course_name="Programming", session="2022-04", type="Past-Papers",
               label="Final", assessment="Final", set="A", keep=True, skip_reason="", confident=True, note="")
CLEAN = decide.Check(answers="no", marking_scheme="no", personal_data="no", summary="", notes="")


def S(**kw):
    base = dict(SORT_OK, course_code="COM107")
    base.update(kw)
    return decide.Sort(**base)


def out(s, c, form=FORM):
    d = decide.decide(ITEM, s, c, form, None, None)
    return d.outcome, d.blocking


def test_each_row_of_the_table():
    assert out(S(), CLEAN) == ("commit", False)
    assert out(S(confident=False), CLEAN) == ("inbox", True)
    d = decide.decide(ITEM, S(confident=False, course_code="COM106"), CLEAN, replace(FORM, code="COM107"), None, None)
    assert (d.outcome, d.code, "ai_unsure" in d.flags) == ("commit", "COM107", True)
    d = decide.decide(ITEM, S(course_code="COM106"), CLEAN, replace(FORM, code="COM111"), None, None)
    assert (d.outcome, d.code, "hint_mismatch" in d.flags) == ("commit", "COM106", True)
    assert out(S(keep=False, skip_reason="lecture_slides"), None) == ("skip", False)
    assert out(S(keep=False, confident=False, skip_reason="textbook"), None) == ("maybe_skip", False)
    assert out(S(), replace(CLEAN, answers="yes")) == ("skip", False)
    d = decide.decide(ITEM, S(), replace(CLEAN, answers="unsure"), FORM, None, None)
    assert d.outcome == "commit" and "answers_unsure" in d.flags
    assert out(S(), replace(CLEAN, personal_data="unsure")) == ("review", True)
    assert out(S(), None) == ("review", True)
    assert out(None, None) == ("review", True)
    d = decide.decide(ITEM, S(), CLEAN, FORM, None, "EEE/COM107_x/2022-04/Past-Papers/a.pdf")
    assert d.outcome == "skip" and "EEE/COM107_x" in d.reason


def test_blocking_and_reason_shape():
    cases = [(S(), CLEAN), (S(confident=False), CLEAN), (S(keep=False, skip_reason="textbook"), None), (S(), None),
             (S(keep=False, confident=False, skip_reason="lecture_slides"), None),
             (S(), replace(CLEAN, answers="yes")), (S(), replace(CLEAN, marking_scheme="yes")),
             (S(), replace(CLEAN, personal_data="unsure")), (S(), replace(CLEAN, personal_data="yes")),
             (S(), replace(CLEAN, personal_data="maybe")), (None, None)]
    for s, c in cases:
        d = decide.decide(ITEM, s, c, FORM, None, None)
        assert d.blocking == (d.outcome in ("inbox", "review"))
        assert d.reason.count(" | ") == 1, d.reason
    for ov in ({"skip": True}, {"approved_by": "x"}):
        assert decide.decide(ITEM, S(), CLEAN, FORM, ov, None).reason.count(" | ") == 1
    assert decide.decide(ITEM, S(), CLEAN, FORM, None, "EEE/COM107_x/a.pdf").reason.count(" | ") == 1
    assert decide.decide(ITEM, None, None, FORM, {"approved_by": "x"}, None).reason.count(" | ") == 1
    d = decide.decide(ITEM, S(), CLEAN, FORM, None, None)
    assert (d.k, d.code, d.session, d.type, d.label, d.set) == (1, "COM107", "2022-04", "Past-Papers", "Final", "A")


def test_ai_unsure_uses_form_hints():
    f = replace(FORM, code="COM107", session="2023-09", type="Notes", taken="2020-01")
    d = decide.decide(ITEM, S(confident=False, course_code="COM106", session="2022-04", type="Past-Papers"), CLEAN, f, None, None)
    assert (d.outcome, d.code, d.session, d.type) == ("commit", "COM107", "2023-09", "Notes")
    f = replace(FORM, code="COM107", taken="2020-01")
    d = decide.decide(ITEM, S(confident=False, session="2022-04"), CLEAN, f, None, None)
    assert d.session == "2020-01"


def test_overrides():
    assert decide.decide(ITEM, S(), CLEAN, FORM, {"skip": True}, None).outcome == "skip"
    place = {"code": "COM106", "session": "2021-09", "type": "Notes", "label": "Week3"}
    d = decide.decide(ITEM, S(confident=False), CLEAN, FORM, {"place": place}, None)
    assert (d.outcome, d.code, d.session, d.type, d.label) == ("commit", "COM106", "2021-09", "Notes", "Week3")
    pd_unsure = replace(CLEAN, personal_data="unsure")
    d = decide.decide(ITEM, S(), pd_unsure, FORM, {"place": place}, None)
    assert d.outcome == "review"
    d = decide.decide(ITEM, S(), pd_unsure, FORM, {"approved_by": "LucasXQY"}, None)
    assert d.outcome == "commit" and "approved_by:LucasXQY" in d.flags
    d = decide.decide(ITEM, S(), pd_unsure, FORM, {"place": place, "approved_by": "LucasXQY"}, None)
    assert (d.outcome, d.code, d.session, d.type) == ("commit", "COM106", "2021-09", "Notes")
    assert "approved_by:LucasXQY" in d.flags
    # approve with no course known goes to inbox; it never un-skips
    d = decide.decide(ITEM, None, None, FORM, {"approved_by": "LucasXQY"}, None)
    assert (d.outcome, d.blocking) == ("inbox", True)
    assert decide.decide(ITEM, S(keep=False, skip_reason="textbook"), None, FORM, {"approved_by": "x"}, None).outcome == "skip"
    # keep re-enters the normal path
    skipped = S(keep=False, skip_reason="textbook")
    assert decide.decide(ITEM, skipped, CLEAN, FORM, {"keep": True}, None).outcome == "commit"
    unsure = replace(skipped, confident=False)
    assert decide.decide(ITEM, unsure, CLEAN, FORM, {"keep": True}, None).outcome == "inbox"
    assert decide.decide(ITEM, unsure, CLEAN, replace(FORM, code="COM107", type="Notes"), {"keep": True}, None).outcome == "commit"


def test_hostile_fields_never_shape_a_path():
    s = decide.validate_sort(dict(SORT_OK, course_code="../../x", session="2022/04", type="Exams", label="a/b\\c"), CAT)
    assert s.course_code == "" and s.session == "unknown" and not s.confident and "/" not in s.label and "\\" not in s.label
    s = decide.validate_sort(dict(SORT_OK, skip_reason="whatever", keep=False, label="x" * 80), CAT)
    assert s.skip_reason == "other" and len(s.label) <= 40
    assert decide.validate_sort(None, CAT) is None
    assert decide.validate_sort(dict(SORT_OK), CAT).course_code == "COM107"


def test_checks_fail_closed():
    for bad in ("yes", "Yes", "", "maybe", None):
        d = decide.decide(ITEM, S(), replace(CLEAN, personal_data=bad), FORM, None, None)
        assert (d.outcome, d.blocking) == ("review", True), bad
    for field in ("answers", "marking_scheme"):
        for bad in ("Yes", "", "maybe", None):
            d = decide.decide(ITEM, S(), replace(CLEAN, **{field: bad}), FORM, None, None)
            assert d.outcome == "review", (field, bad)
    assert decide.decide(ITEM, S(), replace(CLEAN, marking_scheme="yes"), FORM, None, None).outcome == "skip"
    d = decide.decide(ITEM, S(), replace(CLEAN, personal_data="maybe"), FORM, {"approved_by": "LucasXQY"}, None)
    assert d.outcome == "commit"


def test_unsure_marking_scheme_is_flagged_not_held_back():
    d = decide.decide(ITEM, S(), replace(CLEAN, marking_scheme="unsure"), FORM, None, None)
    assert (d.outcome, d.blocking, "marking_unsure" in d.flags) == ("commit", False, True)


def test_decision_name_follows_the_course():
    f = replace(FORM, code="COM107", name="Programming Fundamentals")
    d = decide.decide(ITEM, S(confident=False, course_code="COM106", course_name="Data Structures"), CLEAN, f, None, None)
    assert (d.code, d.name) == ("COM107", "Programming Fundamentals")
    d = decide.decide(ITEM, S(course_name="Programming"), CLEAN, f, None, None)
    assert d.name == "Programming"
    place = {"code": "EEE999", "session": "2021-09", "type": "Notes"}
    d = decide.decide(ITEM, S(course_name="Programming"), CLEAN, f, {"place": place}, None)
    assert (d.code, d.name) == ("EEE999", "")


def test_any_failed_field_makes_the_sort_unsure():
    assert not decide.validate_sort(dict(SORT_OK, session="2022/04"), CAT).confident
    s = decide.validate_sort(dict(SORT_OK, session="2022/04"), CAT)
    assert s.session == "unknown"
    assert not decide.validate_sort(dict(SORT_OK, label="a/b"), CAT).confident
    assert not decide.validate_sort(dict(SORT_OK, assessment="a..b"), CAT).confident
    assert not decide.validate_sort(dict(SORT_OK, set="a\\b"), CAT).confident
    assert decide.validate_sort(dict(SORT_OK, label="Week 3 notes", session="unknown"), CAT).confident


def test_file_name_guards_its_inputs():
    for args in (("../..", "2022-04", "Notes"), ("COM107", "2022-04\n", "Notes"), ("COM107", "2022-04", "Exams"),
                 ("COM107\n", "2022-04", "Notes"), ("COM107", "2022/04", "Notes")):
        try:
            decide.file_name(*args, "x", "", "pdf", set())
        except ValueError:
            continue
        raise AssertionError(args)


def test_session_rule():
    hint = replace(FORM, code="COM107", session="2023-09", taken="2023-09")
    assert decide.resolve_session(S(session="unknown"), hint) == "2023-09"
    assert decide.resolve_session(S(session="unknown"), replace(FORM, code="COM107", session="", taken="2024-04")) == "2024-04"
    assert decide.resolve_session(S(session="unknown", course_code="COM106"), hint) == "unknown"
    assert decide.resolve_session(S(session="2022-04"), hint) == "2022-04"


def test_file_names_follow_contributing():
    t = set()
    assert decide.file_name("COM107", "2022-04", "Past-Papers", "Final", "A", "pdf", t) == "COM107_202204_Final_SetA_Question.pdf"
    assert decide.file_name("COM107", "2022-04", "Past-Papers", "Final", "A", "pdf", t) == "COM107_202204_Final_SetA_Question_2.pdf"
    assert decide.file_name("EEE202", "unknown", "Notes", "", "", "pdf", t) == "EEE202_unknown_Notes.pdf"
    assert decide.file_name("COM103", "2022-04", "Labs", "Lab2_Manual", "", "docx", t) == "COM103_202204_Lab2_Manual.docx"
    assert decide.file_name("EEE202", "unknown", "Past-Papers", "", "", "pdf", t) == "EEE202_unknown_PastPaper_Question.pdf"
    assert decide.file_name("EEE202", "unknown", "Exam-Review", "", "", "pdf", t) == "EEE202_unknown_ExamReview.pdf"
    assert decide.file_name("COM107", "2022-04", "Past-Papers", "Final_Question", "SetB", "pdf", t) == "COM107_202204_Final_SetB_Question.pdf"


def test_past_papers_label_prefers_assessment():
    d = decide.decide(ITEM, S(assessment="Midterm", label="Scan1"), CLEAN, FORM, None, None)
    assert d.label == "Midterm"
    d = decide.decide(ITEM, S(assessment="", label="Scan1"), CLEAN, FORM, None, None)
    assert d.label == "Scan1"
    d = decide.decide(ITEM, S(type="Notes", assessment="Midterm", label="Week3"), CLEAN, FORM, None, None)
    assert d.label == "Week3"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
