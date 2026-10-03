import json
import subprocess

import pytest

from ctube import youtube

VID = "z-Xl9tGqH14"


@pytest.mark.parametrize("s", [
    VID,
    f"https://www.youtube.com/watch?v={VID}&t=30s",
    f"youtube.com/watch?v={VID}",
    f"https://youtu.be/{VID}?si=abc",
    f"https://www.youtube.com/shorts/{VID}",
    f"https://www.youtube.com/live/{VID}",
    f"https://www.youtube.com/embed/{VID}",
    f"https://m.youtube.com/watch?v={VID}",
])
def test_video_id(s):
    assert youtube.video_id(s) == VID


@pytest.mark.parametrize("s", ["https://vimeo.com/123", "hello", "https://www.youtube.com/@channel"])
def test_video_id_rejects(s):
    with pytest.raises(ValueError):
        youtube.video_id(s)


def test_is_blocked():
    assert youtube.is_blocked("ERROR: [youtube] x: Sign in to confirm you're not a bot.")
    assert youtube.is_blocked("HTTP Error 429: Too Many Requests")
    assert not youtube.is_blocked("ERROR: Video unavailable")


def test_url_expiry():
    assert youtube.url_expiry("https://r.googlevideo.com/videoplayback?expire=1791005546&ei=x") == 1791005546


def _cp(rc, err=""):
    return subprocess.CompletedProcess([], rc, stdout="{}", stderr=err)


def test_ytdlp_retries_with_cookies_when_opted_in(monkeypatch):
    monkeypatch.setenv("CLAUDETUBE_BROWSER", "chrome")
    calls = []
    results = iter([_cp(1, "Sign in to confirm you're not a bot"), _cp(0)])
    monkeypatch.setattr(youtube.proc, "run", lambda a, **k: calls.append(a) or next(results))
    youtube.ytdlp(["-J"], "u")
    assert "--cookies-from-browser" in calls[1] and "--cookies-from-browser" not in calls[0]


def test_ytdlp_never_reads_cookies_by_default(monkeypatch):
    monkeypatch.delenv("CLAUDETUBE_BROWSER", raising=False)
    calls = []
    monkeypatch.setattr(youtube.proc, "run",
                        lambda a, **k: calls.append(a) or _cp(1, "Sign in to confirm you're not a bot"))
    with pytest.raises(youtube.Blocked):
        youtube.ytdlp(["-J"], "u")
    assert len(calls) == 1 and "--cookies-from-browser" not in calls[0]


def test_ytdlp_raises_blocked(monkeypatch):
    monkeypatch.setattr(youtube.proc, "run", lambda a, **k: _cp(1, "Sign in to confirm you're not a bot"))
    with pytest.raises(youtube.Blocked):
        youtube.ytdlp(["-J"], "u")


def test_ytdlp_other_error(monkeypatch):
    monkeypatch.setattr(youtube.proc, "run", lambda a, **k: _cp(1, "ERROR: Video unavailable"))
    with pytest.raises(RuntimeError):
        youtube.ytdlp(["-J"], "u")


F = [
    {"format_id": "134", "height": 360, "vcodec": "avc1.4d401e", "ext": "mp4", "url": "a", "size": 364},
    {"format_id": "396", "height": 360, "vcodec": "av01.0.01M.08", "ext": "mp4", "url": "b", "size": 209},
    {"format_id": "298", "height": 720, "vcodec": "avc1.4d4020", "ext": "mp4", "url": "c", "size": 1540},
    {"format_id": "398", "height": 720, "vcodec": "av01.0.05M.08", "ext": "mp4", "url": "d", "size": 874},
    {"format_id": "299", "height": 1080, "vcodec": "avc1.64002a", "ext": "mp4", "url": "e", "size": 2878},
]


def test_choose_hd_prefers_avc1_at_height():
    assert youtube.choose_hd(F, 720)["format_id"] == "298"
    assert youtube.choose_hd(F, 1080)["format_id"] == "299"
    assert youtube.choose_hd(F, 200)["format_id"] in ("134", "396")


def test_choose_scan_smallest_360():
    assert youtube.choose_scan(F, "av01")["format_id"] == "396"


def test_choose_scan_prefers_codec_then_smallest():
    assert youtube.choose_scan(F, "avc1")["format_id"] == "134"
    assert youtube.choose_scan(F, "vp09")["format_id"] == "396"  # codec absent -> smallest 360p


def test_scan_codec_env_override(monkeypatch):
    monkeypatch.setenv("CLAUDETUBE_SCAN_CODEC", "vp09")
    assert youtube.scan_codec() == "vp09"


def test_pick_caption_prefers_manual_then_orig(tmp_path):
    for k in ("en", "en-orig", "es-orig"):
        (tmp_path / f"subs.{k}.json3").write_text("{}")
    assert youtube.pick_caption(tmp_path, {"subtitles": {"en": []}})[1:] == ("manual", "en")
    assert youtube.pick_caption(tmp_path, {"subtitles": {}})[2] == "en-orig"
    assert youtube.pick_caption(tmp_path, {}, lang="es")[2] == "es-orig"


def test_pick_caption_none(tmp_path):
    assert youtube.pick_caption(tmp_path, {}) == (None, None, None)


def test_ensure_scan_redownloads_when_prefetch_died(tmp_path, monkeypatch):
    (tmp_path / "scan.status").write_text(json.dumps({"state": "running", "pid": 999999}))
    called = []
    monkeypatch.setattr(youtube, "download_scan", lambda u, d: called.append(1) or d / "scan.mp4")
    assert youtube.ensure_scan("u", tmp_path) == tmp_path / "scan.mp4"
    assert called == [1]


def test_ensure_scan_uses_finished_file(tmp_path, monkeypatch):
    (tmp_path / "scan.mp4").write_bytes(b"x")
    (tmp_path / "scan.status").write_text(json.dumps({"state": "done"}))
    monkeypatch.setattr(youtube, "download_scan", lambda u, d: pytest.fail("should not download"))
    assert youtube.ensure_scan("u", tmp_path) == tmp_path / "scan.mp4"
