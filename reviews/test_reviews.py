"""Checks for reviews/reviews.py. Run from the repo root: python reviews/test_reviews.py (no network)."""
import json, pathlib, subprocess, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import reviews as rv

BODY = """### 课程代码 | Course code

com107

### 老师 | Lecturer

Dr. Chua Ming Yam

### 年份 | Year

2022

### 学期 | Term

04

### 其他学期 | Other session (YYYY-MM)

_No response_

### 课程质量 | Course quality

4

### 老师质量 | Instructor quality

5

### 难度 | Difficulty

3

### 作业量 | Work required

2

### 学到多少 | Amount learned

4

### 沟通 | Communication

不评 | Skip

### 找得到老师 | Instructor access

_No response_

### 是否推荐 | Would recommend

5

### 确认 | Confirm

- [x] {confirm}
"""


def _body(**over):
    b = BODY.format(confirm=rv.CONFIRM)
    for k, v in over.items():
        b = b.replace(k, v)
    return b


def test_parse_and_validate():
    r = rv.parse_review(_body())
    assert (r.code, r.lecturer, r.session, r.confirmed) == ("COM107", "Dr. Chua Ming Yam", "2022-04", True)
    assert r.scores == {"course": 4, "instructor": 5, "difficulty": 3, "work": 2, "learned": 4, "recommend": 5}
    assert rv.validate(r) == []
    bad = rv.parse_review(_body(com107="nope").replace("- [x]", "- [ ]").replace("\n4\n", "\n9\n"))
    problems = rv.validate(bad)
    assert len(problems) == 3 and all(" | " in p for p in problems), problems
    assert any("Course code" in p for p in problems) and any("Confirm" in p for p in problems)
    none = rv.parse_review("### 课程代码 | Course code\n\nCOM107\n\n### 老师 | Lecturer\n\nX\n\n### 确认 | Confirm\n\n- [x] " + rv.CONFIRM + "\n")
    assert any("至少" in p for p in rv.validate(none))


def test_session_from_year_and_term_dropdowns():
    assert rv.parse_review(_body()).session == "2022-04"
    other = rv.parse_review(_body().replace("\n04\n", "\n" + rv.TERM_OTHER + "\n")
                            .replace("Other session (YYYY-MM)\n\n_No response_", "Other session (YYYY-MM)\n\n2021-11"))
    assert other.session == "2021-11" and rv.validate(other) == []
    bad = rv.parse_review(_body().replace("\n04\n", "\n" + rv.TERM_OTHER + "\n")
                          .replace("Other session (YYYY-MM)\n\n_No response_", "Other session (YYYY-MM)\n\nNov 2021"))
    assert any("Other session" in p for p in rv.validate(bad))
    none = rv.parse_review(_body().replace("\n2022\n", "\n_No response_\n").replace("\n04\n", "\n_No response_\n"))
    assert none.session == "" and rv.validate(none) == []                                   # the session is optional
    assert rv.TERMS == ("02", "04", "09") and rv.FIELDS["year"] == "年份 | Year" and rv.FIELDS["term"] == "学期 | Term"


def test_lecturer_key_merges_spellings():
    assert rv.lecturer_key("Dr. Chua Ming Yam") == rv.lecturer_key("chua  ming yam") == "chua-ming-yam"
    assert rv.lecturer_key("Puan Maryani Ahmad") == "maryani-ahmad" and rv.lecturer_key("Prof. Ng Zi Neng") == "ng-zi-neng"


def test_record_upserts_per_voter_and_aggregates_with_threshold():
    data = pathlib.Path(tempfile.mkdtemp())
    r = rv.parse_review(_body())
    rv.record(data, r, "voter-a", "2026-11-05T10:00:00Z")
    rv.record(data, rv.parse_review(_body().replace("\n4\n\n### 老师质量", "\n2\n\n### 老师质量")), "voter-a", "2026-11-05T11:00:00Z")  # same voter again
    rv.record(data, r, "voter-b", "2026-11-05T12:00:00Z")
    f = data / "votes" / "COM107" / "chua-ming-yam.json"
    saved = json.loads(f.read_text(encoding="utf-8"))
    assert set(saved["votes"]) == {"voter-a", "voter-b"} and saved["votes"]["voter-a"]["scores"]["course"] == 2
    agg = rv.aggregate(data)
    entry = agg["courses"]["COM107"]["lecturers"]["chua-ming-yam"]
    assert entry["n"] == 2 and entry["name"] == "Chua Ming Yam" and "course" not in entry        # below MIN_N: count only
    rv.record(data, r, "voter-c", "2026-11-05T13:00:00Z")
    entry = rv.aggregate(data)["courses"]["COM107"]["lecturers"]["chua-ming-yam"]
    assert entry["n"] == 3 and entry["course"] == 3.3 and entry["instructor"] == 5.0 and entry["communication"] is None
    assert entry["counts"]["course"] == 3 and entry["counts"]["communication"] == 0
    rv.record(data, rv.parse_review(_body().replace("Dr. Chua Ming Yam", "Someone Else")), "voter-a", "2026-11-05T09:00:00Z")   # older vote, other lecturer
    rv.record(data, rv.parse_review(_body().replace("Dr. Chua Ming Yam", "Someone Else")), "voter-d", "2026-11-05T14:00:00Z")
    course = rv.aggregate(data)["courses"]["COM107"]
    assert course["all"]["n"] == 4 and course["all"]["course"] == 3.5                     # one vote per voter per course, latest wins
    assert set(course["lecturers"]) == {"chua-ming-yam", "someone-else"} and "course" not in course["lecturers"]["someone-else"]


def test_voter_hash_is_stable_and_salted():
    assert rv.voter_hash(123, "s") == rv.voter_hash(123, "s") != rv.voter_hash(123, "t") != rv.voter_hash(124, "t")
    assert len(rv.voter_hash(1, "x")) == 24


def test_cli_dry_run_records_and_writes_ratings():
    w = pathlib.Path(tempfile.mkdtemp())
    (w / "form.md").write_text(_body(), encoding="utf-8")
    for voter in ("a", "b", "c"):
        r = subprocess.run([sys.executable, str(pathlib.Path(__file__).parent / "reviews.py"), "--dry-run", "--form", str(w / "form.md"),
                            "--data", str(w / "data"), "--voter", voter, "--out", str(w / "ratings.json")],
                           capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr
    agg = json.loads((w / "ratings.json").read_text(encoding="utf-8"))
    assert agg["courses"]["COM107"]["lecturers"]["chua-ming-yam"]["n"] == 3 and "generated" in agg
    (w / "bad.md").write_text(_body().replace("- [x]", "- [ ]"), encoding="utf-8")
    r = subprocess.run([sys.executable, str(pathlib.Path(__file__).parent / "reviews.py"), "--dry-run", "--form", str(w / "bad.md"),
                        "--data", str(w / "data"), "--voter", "d", "--out", str(w / "ratings.json")], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and "Confirm" in r.stdout


def test_remove_source_deletes_or_falls_back():
    """A recorded issue is deleted with the delete token; without it, or when GitHub refuses, it is closed and locked."""
    calls = []

    def fake_gh(*args, token=None, input=None):
        calls.append((args, token))
        if "graphql" in args and token == "weak":
            raise RuntimeError("github-actions does not have the correct permissions to execute `DeleteIssue`")
        return ""
    real, rv.gh = rv.gh, fake_gh
    try:
        assert rv.remove_source(5, "o/r", "I_kwabc", "strong", wait=0) is True
        args, token = calls[-1]
        assert token == "strong" and "deleteIssue" in " ".join(args) and "id=I_kwabc" in args and len(calls) == 1
        calls.clear()
        assert rv.remove_source(5, "o/r", "I_kwabc", "", wait=0) is False
        assert [a[:2] for a, _ in calls] == [("issue", "close"), ("issue", "lock")]
        calls.clear()
        assert rv.remove_source(5, "o/r", "I_kwabc", "weak", wait=0) is False
        assert [a[:2] for a, _ in calls][-2:] == [("issue", "close"), ("issue", "lock")]
    finally:
        rv.gh = real


def test_sweep_decision():
    """Closed review issues: recorded ones go at once (the vote is safe in the private repo); a form that failed stays
    a week so its author can read why; anything the bot never answered is left alone."""
    from datetime import datetime, timezone
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    recorded = [rv.RECORDED + "：COM107 · Chua Ming Yam。…"]
    failed = [rv.NOT_RECORDED + "，这次没有登记 | Not recorded yet …"]
    assert rv.sweep_decision("2026-11-19T23:00:00Z", recorded, now)
    assert not rv.sweep_decision("2026-11-19T23:00:00Z", failed, now) and rv.sweep_decision("2026-11-12T00:00:00Z", failed, now)
    assert not rv.sweep_decision("2026-11-01T00:00:00Z", [], now) and not rv.sweep_decision("2026-11-01T00:00:00Z", ["thanks!"], now)
    assert rv.recorded_reply("COM107", "Dr. Chua Ming Yam", True).startswith(rv.RECORDED) and "删除" in rv.recorded_reply("COM107", "X", True)


def test_new_lecturers_are_noted_with_their_session():
    """A lecturer the site does not list for this course goes on the pending list (reviews/lecturers.py turns it into a PR)."""
    class State:
        def __init__(self):
            self.data, self.writes = {}, 0
        def read(self):
            return self.data, "sha"
        def write(self, data, sha, message):
            self.data, self.writes = data, self.writes + 1
    st = State()
    r = rv.parse_review(_body())                                   # COM107, Dr. Chua Ming Yam, 2022-04
    assert rv.note_new_lecturer(r, known={("COM107", "chua-ming-yam")}, state=st) is False and st.writes == 0
    other = rv.parse_review(_body().replace("Dr. Chua Ming Yam", "Prof. New Person"))
    assert rv.note_new_lecturer(other, known={("COM107", "chua-ming-yam")}, state=st) is True
    assert st.data == {"items": [{"code": "COM107", "name": "New Person", "session": "2022-04"}]}
    assert rv.note_new_lecturer(other, known=set(), state=st) is False and st.writes == 1      # noted once
    nosess = rv.parse_review(_body().replace("Dr. Chua Ming Yam", "Third One").replace("\n2022\n", "\n_No response_\n"))
    rv.note_new_lecturer(nosess, known=set(), state=st)
    assert st.data["items"][-1]["session"] == "unknown"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
