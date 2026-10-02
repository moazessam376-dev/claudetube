import os
import time

from ctube import cache


def test_video_dir_created(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDETUBE_CACHE", str(tmp_path))
    d = cache.video_dir("abc")
    assert d.is_dir() and d.parent == tmp_path


def test_sweep_removes_only_old(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDETUBE_CACHE", str(tmp_path))
    old, new = cache.video_dir("old"), cache.video_dir("new")
    (old / "f").write_text("x")
    past = time.time() - 25 * 3600
    os.utime(old, (past, past))
    assert cache.sweep() == 1
    assert not old.exists() and new.exists()


def test_remove_and_remove_all(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDETUBE_CACHE", str(tmp_path))
    a = cache.video_dir("a")
    (a / "f").write_bytes(b"x" * 100)
    cache.video_dir("b")
    assert cache.remove("a") == 100
    assert not a.exists()
    assert cache.remove("missing") == 0
    cache.remove_all()
    assert list(tmp_path.iterdir()) == []
