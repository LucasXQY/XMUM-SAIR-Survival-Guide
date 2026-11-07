"""Checks for intake/commands.py. Run from the repo root: python intake/test_commands.py (no network needed)."""
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import commands


def test_commands_parse_and_permission():
    cmds, errs = commands.parse("thanks!\n/place #3 com107 2022-04 Past-Papers Final\n/skip #4\n/keep #5\n/approve #2\n/retry\n/place #x COM107")
    assert [(c.kind, c.k) for c in cmds] == [("place", 3), ("skip", 4), ("keep", 5), ("approve", 2), ("retry", None)]
    assert cmds[0].args == {"code": "COM107", "session": "2022-04", "type": "Past-Papers", "label": "Final"} and len(errs) == 1
    assert commands.parse("/place #1 ../x 2022-04 Notes")[0] == []
    assert commands.authorized("OWNER") and commands.authorized("MEMBER") and commands.authorized("COLLABORATOR")
    assert not commands.authorized("CONTRIBUTOR") and not commands.authorized("NONE")


def test_only_command_lines_count_and_unknown_words_are_silent():
    cmds, errs = commands.parse("  /SKIP #2 because it is junk\nplease /skip #9\n/lgtm\n/deploy now\n/Retry")
    assert [(c.kind, c.k) for c in cmds] == [("skip", 2), ("retry", None)] and errs == []


def test_k_must_be_a_positive_integer():
    for line in ("/skip #0", "/skip 3", "/skip #-1", "/skip #1a", "/skip", "/keep #", "/approve #x"):
        cmds, errs = commands.parse(line)
        assert cmds == [] and len(errs) == 1, line
        assert " | " in errs[0]


def test_place_validation():
    ok = lambda s: commands.parse(s)[0]
    assert ok("/place #1 EEE202 unknown Notes")[0].args == {"code": "EEE202", "session": "unknown", "type": "Notes"}
    assert ok("/place #1 eee202 2022-04 Notes My_Label.v2")[0].args["label"] == "My_Label.v2"
    for bad in ("/place #1 EEE202 2022/04 Notes", "/place #1 EEE202 2022-04 Notebooks", "/place #1 EEE202 2022-04",
                "/place #1 EEE202 2022-04 Notes a/b", "/place #1 EEE202 2022-04 Notes a\\b",
                "/place #1 EEE202 2022-04 Notes a..b", "/place #1 EEE202 2022-04 Notes " + "x" * 41,
                "/place #1 ../../etc 2022-04 Notes", "/place #1 EEE202 2022-13x Notes", "/place #1"):
        cmds, errs = commands.parse(bad)
        assert cmds == [] and len(errs) == 1, bad
    # errors never echo the arguments
    _, errs = commands.parse("/place #4 ../../secret EEE2109300 Notes")
    assert "secret" not in errs[0] and "EEE2109300" not in errs[0] and "#4" in errs[0]


def test_merge_each_command():
    P = commands.Command
    base = {"keep": True, "approved_by": "a"}
    r = commands.merge(base, P("skip", 1, {}), "bob")
    assert r == {"skip": True, "approved_by": "a"} and base == {"keep": True, "approved_by": "a"}
    assert commands.merge({"skip": True}, P("keep", 1, {}), "bob") == {"keep": True}
    place = {"code": "COM107", "session": "2022-04", "type": "Notes", "label": "L"}
    r = commands.merge(None, P("place", 1, dict(place)), "bob")
    assert r == {"place": place}
    assert commands.merge({"skip": True}, P("approve", 1, {}), "bob") == {"skip": True, "approved_by": "bob"}
    src = {"keep": True}
    r = commands.merge(src, P("retry", None, {}), "bob")
    assert r == src and r is not src
    assert commands.merge(None, P("retry", None, {}), "bob") == {}
    nolabel = commands.merge(None, P("place", 1, {"code": "X1000", "session": "unknown", "type": "Notes"}), "b")
    assert nolabel["place"] == {"code": "X1000", "session": "unknown", "type": "Notes"}


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok {len(tests)} tests")
