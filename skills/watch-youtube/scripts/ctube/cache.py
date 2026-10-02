"""Per-video working folders under one cache root, with a 24 h sweep."""
import os
import shutil
import time
from pathlib import Path

MAX_AGE_S = 24 * 3600


def root() -> Path:
    r = Path(os.environ.get("CLAUDETUBE_CACHE") or Path.home() / ".cache" / "claudetube")
    r.mkdir(parents=True, exist_ok=True)
    return r


def video_dir(video_id: str) -> Path:
    d = root() / video_id
    d.mkdir(parents=True, exist_ok=True)
    os.utime(d)
    return d


def _size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _rm(p: Path) -> int:
    n = _size(p)
    shutil.rmtree(p, ignore_errors=True)
    return n


def sweep(max_age_s: float = MAX_AGE_S) -> int:
    """Delete video folders not touched for max_age_s. Returns how many were removed."""
    cutoff = time.time() - max_age_s
    removed = 0
    for d in root().iterdir():
        if d.is_dir() and d.stat().st_mtime < cutoff:
            _rm(d)
            removed += 1
    return removed


def remove(video_id: str) -> int:
    """Delete one video's folder. Returns bytes freed."""
    d = root() / video_id
    return _rm(d) if d.is_dir() else 0


def remove_all() -> int:
    return sum(_rm(d) if d.is_dir() else 0 for d in root().iterdir())
