import json

import pytest

import claudetube
from ctube import youtube

VID = "z-Xl9tGqH14"
META = {"id": VID, "title": "T", "channel": "C", "duration": 100, "upload_date": "20260101",
        "webpage_url": "u", "chapters": [], "formats": [], "caption": {"file": None}}


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDETUBE_CACHE", str(tmp_path))
    monkeypatch.setattr(claudetube.proc, "need", lambda *b: None)
    return tmp_path


def test_cleanup_all(env, capsys):
    (env / VID).mkdir()
    (env / VID / "x").write_bytes(b"x" * 2_000_000)
    assert claudetube.main(["cleanup", "--all"]) == 0
    assert "freed 2.0 MB" in capsys.readouterr().out
    assert not (env / VID).exists()


def test_frames_rejects_time_beyond_duration(env, monkeypatch, capsys):
    monkeypatch.setattr(youtube, "fetch_info", lambda u, d, lang=None: META)
    monkeypatch.setattr(claudetube.frames, "grab_hd", lambda *a, **k: pytest.fail("must not grab"))
    assert claudetube.main(["frames", VID, "0:30", "5:00"]) == 1
    assert "outside the video" in capsys.readouterr().err


def test_frames_rejects_bad_time(env, monkeypatch, capsys):
    monkeypatch.setattr(youtube, "fetch_info", lambda u, d, lang=None: META)
    assert claudetube.main(["frames", VID, "abc"]) == 1


def test_missing_dependency(monkeypatch, capsys):
    def need(*b):
        raise claudetube.proc.MissingDep("yt-dlp not found")
    monkeypatch.setattr(claudetube.proc, "need", need)
    assert claudetube.main(["info", VID]) == 2


def test_blocked(monkeypatch, capsys):
    def blocked(*a, **k):
        raise youtube.Blocked("Sign in to confirm")
    monkeypatch.setattr(youtube, "fetch_info", blocked)
    assert claudetube.main(["info", VID]) == 3
    assert "BLOCKED" in capsys.readouterr().err


def test_info_without_captions(env, monkeypatch, capsys):
    monkeypatch.setattr(youtube, "fetch_info", lambda u, d, lang=None: META)
    assert claudetube.main(["info", VID]) == 4
    o = capsys.readouterr().out
    assert "# T" in o and "NO_CAPTIONS" in o
    assert (env / VID / "transcript.md").exists()


def test_info_long_video_without_chapters_gets_segments(env, monkeypatch, capsys):
    vdir = env / VID
    vdir.mkdir()
    cap = vdir / "subs.en.json3"
    events = [{"tStartMs": i * 1000, "segs": [{"utf8": f"word{i} and some more words here."}]} for i in range(0, 3600, 2)]
    cap.write_text(json.dumps({"events": events}))
    meta = dict(META, duration=3600, caption={"file": str(cap), "source": "auto", "lang": "en"})
    monkeypatch.setattr(youtube, "fetch_info", lambda u, d, lang=None: (youtube.save_meta(d, meta), meta)[1])
    assert claudetube.main(["info", VID]) == 0
    o = capsys.readouterr().out
    assert "Segment 1 (00:00–10:00)" in o and "--chapter N" in o
    assert not cap.exists()  # raw captions deleted
    assert claudetube.main(["info", VID, "--chapter", "2"]) == 0
    assert capsys.readouterr().out.startswith("### 2. [10:00]")


def _cache_transcript(env, md, duration=4000, chapters=()):
    d = env / VID
    d.mkdir(exist_ok=True)
    meta = dict(META, duration=duration, chapters=list(chapters), caption={"file": "x"})
    (d / "meta.json").write_text(json.dumps(meta))
    (d / "transcript.md").write_text(md, encoding="utf-8")


def _long_md():
    lines = ["# T", "C", "", "## Chapters", "1. [00:00] One", "2. [30:00] Two", "", "## Transcript", "",
             "### 1. [00:00] One"]
    lines += [f"[{m:02d}:00] " + f"lesson step {m} " * 60 for m in range(30)]
    lines += ["", "### 2. [30:00] Two"]
    lines += ["[30:00] This is covered in my course, the link is beneath this video.",
              "[30:30] Join the course with the link below.", "[31:00] Back to the lesson, of course."]
    return "\n".join(lines) + "\n"


def test_info_pages_long_chapter(env, capsys):
    _cache_transcript(env, _long_md(), chapters=[{"start_time": 0, "title": "One"},
                                                 {"start_time": 1800, "title": "Two"}])
    assert claudetube.main(["info", VID]) == 0
    o = capsys.readouterr().out
    assert "Per chapter" in o and "prints in 2 parts" in o and "30:00-31:00" in o
    assert claudetube.main(["info", VID, "--chapter", "1"]) == 0
    p1 = capsys.readouterr().out
    assert len(p1) <= claudetube.PART_CHARS + 200 and "Next: info URL --chapter 1 --part 2" in p1
    assert claudetube.main(["info", VID, "--chapter", "1", "--part", "2"]) == 0
    p2 = capsys.readouterr().out
    assert "[29:00]" in p2 and "Next:" not in p2
    assert claudetube.main(["info", VID, "--chapter", "1", "--part", "3"]) == 1


def test_find(env, capsys):
    _cache_transcript(env, _long_md())
    assert claudetube.main(["find", VID, "lesson step 7 "]) == 0
    o = capsys.readouterr().out
    assert o.startswith("1 paragraph(s) match") and "[07:00] ch1" in o
    assert claudetube.main(["find", VID, "nothing-like-this"]) == 0
    assert "no matches" in capsys.readouterr().out
    assert claudetube.main(["find", VID, "(", "--regex"]) == 1


def test_frames_every_skips_promos(env, monkeypatch, capsys):
    _cache_transcript(env, _long_md(), duration=1900)
    monkeypatch.setattr(claudetube.frames, "grab_hd",
                        lambda get, ts, d, h: {t: d / f"{t}.jpg" for t in ts})
    assert claudetube.main(["frames", VID, "--range", "29:50-31:20", "--every", "30", "--single"]) == 0
    o = capsys.readouterr().out
    assert "skipped 2 frame(s) in likely promo segments: 30:00-31:00" in o
    assert "29:50" in o and "31:20" in o and "30:20" not in o
    assert claudetube.main(["frames", VID, "--range", "29:50-31:20", "--every", "30", "--single",
                            "--keep-promos"]) == 0
    assert "30:20" in capsys.readouterr().out
