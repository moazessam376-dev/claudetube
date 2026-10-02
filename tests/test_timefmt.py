import pytest
from ctube.timefmt import parse_time, fmt_time, parse_range


@pytest.mark.parametrize("s,v", [("90", 90), ("1:30", 90), ("1:02:03", 3723), ("12.5", 12.5), ("00:05", 5)])
def test_parse_time(s, v):
    assert parse_time(s) == v


@pytest.mark.parametrize("s", ["abc", "1:2:3:4", "-5", "", "1:75"])
def test_parse_time_rejects(s):
    with pytest.raises(ValueError):
        parse_time(s)


def test_fmt_time():
    assert fmt_time(65) == "01:05"
    assert fmt_time(3723) == "1:02:03"
    assert fmt_time(0.4) == "00:00"


def test_parse_range():
    assert parse_range("1:00-2:00") == (60, 120)
    with pytest.raises(ValueError):
        parse_range("2:00-1:00")
    with pytest.raises(ValueError):
        parse_range("1:00")
