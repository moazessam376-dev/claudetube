"""Frame extraction (HD streamed seeks or local scan copy) and contact-sheet building via ffmpeg."""
import functools
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import proc
from .timefmt import fmt_time

HD_WORKERS = 16
LOCAL_WORKERS = 8


@functools.lru_cache(maxsize=1)
def has_drawtext() -> bool:
    r = proc.run(["ffmpeg", "-hide_banner", "-filters"])
    return " drawtext " in r.stdout


def _label_filter(t: float) -> str:
    txt = fmt_time(t).replace(":", r"\:")
    return (f"drawtext=text='{txt}':x=10:y=10:fontsize=h/18:fontcolor=white:"
            f"box=1:boxcolor=black@0.65:boxborderw=6")


def _grab(src: str, t: float, out: Path, width=None) -> bool:
    vf = []
    if width:
        vf.append(f"scale={width}:-2")
    args = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1", "-q:v", "3"]
    if has_drawtext():
        r = proc.run(args + ["-vf", ",".join(vf + [_label_filter(t)]), str(out)], timeout=120)
        if r.returncode == 0 and out.exists():
            return True
    r = proc.run(args + (["-vf", ",".join(vf)] if vf else []) + [str(out)], timeout=120)
    return r.returncode == 0 and out.exists() and out.stat().st_size > 0


def _name(outdir: Path, t: float, tag: str) -> Path:
    return outdir / f"f_{tag}_{int(round(t * 1000)):010d}.jpg"


def grab_many(src: str, times, outdir: Path, workers: int, tag: str, width=None):
    """Grab one frame per time from src (URL or file). Returns {t: Path or None}."""
    outdir.mkdir(parents=True, exist_ok=True)

    def one(t):
        p = _name(outdir, t, tag)
        if p.exists() and p.stat().st_size:
            return t, p
        return t, (p if _grab(src, t, p, width) else None)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return dict(ex.map(one, times))


def grab_hd(get_url, times, outdir: Path, height: int, width=None):
    """Streamed seeks against the HD stream. get_url(force) returns a (possibly refreshed) URL."""
    res = grab_many(get_url(False), times, outdir, HD_WORKERS, f"h{height}", width)
    failed = [t for t, p in res.items() if p is None]
    if failed:  # most often an expired URL (403): refresh once and retry
        res.update(grab_many(get_url(True), failed, outdir, HD_WORKERS, f"h{height}", width))
    return res


def grab_local(scan: Path, times, outdir: Path):
    return grab_many(str(scan), times, outdir, LOCAL_WORKERS, "s")


def tiny_frames(scan: Path, start=None, end=None, w=32, h=18) -> bytes:
    """Decode the scan copy to raw 1 fps grayscale frames of w x h (for scene detection)."""
    args = ["ffmpeg", "-nostdin", "-loglevel", "error"]
    if start is not None:
        args += ["-ss", f"{start:.3f}"]
    if end is not None:
        args += ["-to", f"{end:.3f}"]
    args += ["-i", str(scan), "-vf", f"fps=1,scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"]
    r = proc.run_bytes(args)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {r.stderr.decode(errors='replace')[-300:]}")
    return r.stdout


def layout(times, cols: int, rows: int):
    per = cols * rows
    return [list(times[i:i + per]) for i in range(0, len(times), per)]


def build_sheet(paths, cols: int, rows: int, tile_w: int, out: Path) -> Path:
    """Tile images (None = black cell) into one cols x rows sheet."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        black = None
        for i, p in enumerate(paths):
            dst = td / f"{i:04d}.jpg"
            if p is None:
                if black is None:
                    black = td / "black.jpg"
                    proc.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                              f"color=black:s={tile_w}x{tile_w * 9 // 16}", "-frames:v", "1", str(black)])
                shutil.copy(black, dst)
            else:
                shutil.copy(p, dst)
        vf = (f"scale={tile_w}:{tile_w * 9 // 16}:force_original_aspect_ratio=decrease,"
              f"pad={tile_w}:{tile_w * 9 // 16}:(ow-iw)/2:(oh-ih)/2,"
              f"tile={cols}x{rows}:padding=4:margin=2:color=white")
        r = proc.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-framerate", "1",
                      "-i", str(td / "%04d.jpg"), "-vf", vf, "-frames:v", "1", "-q:v", "3", str(out)])
        if r.returncode != 0 or not out.exists():
            raise RuntimeError(f"sheet build failed: {r.stderr[-300:]}")
    return out


def legend(path: Path, times, cols: int, failed=()) -> str:
    lines = [str(path)]
    for i in range(0, len(times), cols):
        row = [fmt_time(t) + ("!" if t in failed else "") for t in times[i:i + cols]]
        lines.append("  " + "  ".join(f"{x:>8}" for x in row))
    return "\n".join(lines)
