"""Checks for site/build.py. Run from the repo root: python site/test_build.py"""
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
ROOT = pathlib.Path(__file__).resolve().parents[1]
import build


def test_parse_taken():
    t = build.parse_taken("| 2022-04 | [COM107](COM107_Circuits_and_Devices/) | x |\n"
                          "| 2022-02 | [COM107](COM107_Circuits_and_Devices/) | x |\n"
                          "| 2022-04 | COM999 | x |\n")
    assert t["COM107"] == ["2022-02", "2022-04"] and t["COM999"] == ["2022-04"]


def test_parse_lecturers_link_and_plain():
    md = ("# X\n\n| 学期 / Session | 老师 / Lecturer | 考核 | 来自 | 备注 |\n|---|---|---|---|---|\n"
          "| [2022-04](2022-04/) | Chua Ming Yam |  | L | n |\n"
          "| 2025-04 | Dr. A |  | J | n |\n"
          "| 2026-09 |  |  | J | n |\n")
    assert build.parse_lecturers(md) == {"2022-04": "Chua Ming Yam", "2025-04": "Dr. A"}


def test_scan_real_repo():
    courses = build.scan(ROOT)
    assert len(courses) == 58 and {c.prog for c in courses} == {"EEE"}
    c = next(c for c in courses if c.code == "COM107")
    assert c.name == "Circuits and Devices" and c.path == "EEE/COM107_Circuits_and_Devices"
    assert list(c.sessions) == ["2022-04"]
    assert list(c.sessions["2022-04"]) == ["Past-Papers", "Tutorials", "Handbooks"]
    assert len(c.sessions["2022-04"]["Tutorials"]) == 5
    assert c.taken_in == ["2022-04"] and c.lecturers["2022-04"] == "Chua Ming Yam"
    files = build.all_files(courses)
    assert len(files) == 482 and all((ROOT / f.path).is_file() for f in files)
    com110 = next(c for c in courses if c.code == "COM110")
    assert list(com110.sessions) == ["2026-09", "2025-04"]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
