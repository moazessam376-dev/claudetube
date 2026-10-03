import json
from pathlib import Path

import pytest

from ctube import captions

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text())


def test_auto_first_fragment_and_no_newlines():
    frags = captions.parse_json3(load("auto.json3"))
    assert frags[0] == (0.08, "So,")
    assert frags[1] == (0.32, "this")
    assert all(t.strip() and "\n" not in t for _, t in frags)
    assert [t for t, _ in frags] == sorted(t for t, _ in frags)


def test_manual_splits_lines_and_collapses_space():
    frags = captions.parse_json3(load("manual.json3"))
    assert [t for _, t in frags] == ["Welcome back. Today we", "build a donut.", "Press Tab to enter edit mode."]
    assert frags[2][0] == 30.0


def test_paragraphs_keep_every_word_and_respect_max_len():
    frags = captions.parse_json3(load("auto.json3"))
    paras = captions.paragraphs(frags, min_len=20, max_len=35)
    assert " ".join(p for _, p in paras).split() == " ".join(t for _, t in frags).split()
    starts = [t for t, _ in paras]
    assert all(b - a <= 35 + 6 for a, b in zip(starts, starts[1:]))  # +one caption fragment of slack
    assert len(paras) > 3


def test_paragraph_breaks_on_sentence_end_after_min_len():
    frags = [(0, "a."), (5, "b."), (21, "c."), (22, "d")]
    assert captions.paragraphs(frags, min_len=20, max_len=35) == [(0, "a. b. c."), (22, "d")]


def test_paragraph_hard_break_at_max_len():
    frags = [(float(i), "w") for i in range(0, 80, 5)]
    paras = captions.paragraphs(frags, min_len=20, max_len=35)
    assert paras[1][0] == 35.0


META = {"title": "T", "channel": "C", "duration": 200, "webpage_url": "u", "upload_date": "20260101"}


def test_render_groups_by_chapter():
    meta = dict(META, chapters=[{"start_time": 0, "title": "Intro"}, {"start_time": 50, "title": "Build"}])
    md = captions.render(meta, [(10, "hello"), (100, "world")])
    assert "1. [00:00] Intro" in md and "2. [00:50] Build" in md
    intro = captions.chapter_section(md, 1)
    build = captions.chapter_section(md, 2)
    assert "[00:10] hello" in intro and "world" not in intro
    assert "[01:40] world" in build and "hello" not in build


def test_render_without_chapters():
    md = captions.render(dict(META, chapters=None), [(10, "hello")])
    assert "###" not in md and "[00:10] hello" in md
    with pytest.raises(KeyError):
        captions.chapter_section(md, 1)


def test_estimate_tokens():
    assert captions.estimate_tokens("x" * 400) == 100


def test_paragraph_breaks_at_chapter_start():
    frags = [(0, "a"), (5, "b"), (10, "c")]
    assert captions.paragraphs(frags, breaks=[6]) == [(0, "a b"), (10, "c")]


MD = """# T
C

## Transcript

### 1. [00:00] Intro
[00:00] Set the scale to 0.12 and the radius to 1.5.
[00:30] Then add a subdivision surface modifier.

### 2. [01:00] Build
[1:00:05] Change the roughness (0.12) again.
"""


def test_parse_md():
    assert captions.parse_md(MD) == [
        (0.0, "Set the scale to 0.12 and the radius to 1.5.", 1),
        (30.0, "Then add a subdivision surface modifier.", 1),
        (3605.0, "Change the roughness (0.12) again.", 2),
    ]


def test_split_parts_keeps_lines_whole():
    text = "\n".join(f"[00:{i:02d}] " + "x" * 50 for i in range(40)) + "\n"
    parts = captions.split_parts(text, 500)
    assert len(parts) > 1 and "".join(parts) == text
    assert all(len(p) <= 500 for p in parts)
    assert all(p.endswith("\n") for p in parts)


def test_search_literal_and_regex():
    paras = captions.parse_md(MD)
    hits = captions.search(paras, ["0.12"])
    assert [(t, ch) for t, ch, _ in hits] == [(0.0, 1), (3605.0, 2)]
    assert captions.search(paras, ["0x12"]) == []  # '.' is literal unless --regex
    assert len(captions.search(paras, [r"\d+\.\d+"], regex=True)) == 2
    assert captions.search(paras, ["SUBDIVISION"])[0][0] == 30.0


def test_search_snippet_ellipses():
    paras = [(0.0, "a" * 200 + " needle " + "b" * 200, 1)]
    (_, _, snip), = captions.search(paras, ["needle"], width=10)
    assert snip.startswith("...") and snip.endswith("...") and "needle" in snip
