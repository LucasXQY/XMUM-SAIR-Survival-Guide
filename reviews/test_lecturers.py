"""Checks for reviews/lecturers.py. Run from the repo root: python reviews/test_lecturers.py (no network)."""
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import lecturers as lc

README = """# EEE406 Power Systems Analysis

| 学期 / Session | 老师 / Lecturer | 考核 / Assessment | 资料来自 / Contributed by | 备注 / Notes |
|---|---|---|---|---|
| [2024-09](2024-09/) |  |  | LucasXQY | [Labs](2024-09/Labs/) |
| [2025-09](2025-09/) | Dr. Someone |  | nsd-chen | |

- 小贴士 / Tips：
"""


def test_known_lecturers_come_from_the_session_table():
    assert lc.readme_lecturers(README) == {"someone"}


def test_add_fills_an_empty_cell_appends_to_a_full_one_or_adds_a_row():
    a = lc.add_lecturer(README, "2024-09", "Abdul Rashid Abdul Rahman")
    assert "| [2024-09](2024-09/) | Abdul Rashid Abdul Rahman |" in a
    b = lc.add_lecturer(README, "2025-09", "Tan Jian Ding")
    assert "| Dr. Someone, Tan Jian Ding |" in b
    c = lc.add_lecturer(README, "2023-04", "New Person").splitlines()
    i = next(k for k, l in enumerate(c) if l.startswith("| 2023-04 |"))
    assert c[i + 1].startswith("| [2024-09]") and lc.NOTE in c[i]                     # sessions stay in order
    assert len(lc._cells(c[i])) == 5                                                    # the note must not add a column
    d = lc.add_lecturer(README, "unknown", "Unsure Person").splitlines()
    assert next(k for k, l in enumerate(d) if l.startswith("| unknown |")) == max(k for k, l in enumerate(d) if l.startswith("|"))
    assert lc.add_lecturer(README, "2025-09", "Dr Someone") == README                  # already there (titles ignored)


def test_wanted_merges_pending_and_ratings_and_drops_what_is_known():
    readmes = {"EEE406": README, "EEE407": README.replace("EEE406", "EEE407")}
    pending = [{"code": "EEE406", "name": "Abdul Rashid Abdul Rahman", "session": "2024-09"}]
    ratings = {"courses": {"EEE406": {"lecturers": {"abdul-rashid-abdul-rahman": {"name": "Abdul Rashid Abdul Rahman"},
                                                   "someone": {"name": "Someone"}}},
                           "EEE407": {"lecturers": {"nornazurah-binti-nazir-ali": {"name": "Nornazurah Binti Nazir Ali"}}},
                           "EEE222": {"lecturers": {"x-y": {"name": "X Y"}}}}}
    add, missing = lc.wanted(pending, ratings, readmes)
    assert add == [{"code": "EEE406", "name": "Abdul Rashid Abdul Rahman", "session": "2024-09"},   # the real session wins
                   {"code": "EEE407", "name": "Nornazurah Binti Nazir Ali", "session": "unknown"}]
    assert missing == [{"code": "EEE222", "name": "X Y", "session": "unknown"}]       # no folder for this course in the repo


def test_pr_body_lists_additions_and_courses_without_a_folder():
    body = lc.pr_body([{"code": "EEE406", "name": "A B", "session": "unknown"}], [{"code": "EEE222", "name": "X Y", "session": "2025-04"}])
    assert "EEE406" in body and "A B" in body and "unknown" in body and "EEE222" in body and "学期" in body


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
