#!/usr/bin/env python3
"""ClaudeTube: let Claude watch YouTube fast.

  info    URL [--chapter N] [--lang L] [--prefetch]   transcript + chapters (compact markdown)
  frames  URL T1 T2 ... | --range A-B --every S | --scenes [--range A-B] [--max N]
          [--grid CxR] [--hd] [--height H] [--single]  contact sheets of many frames
  frame   URL T [--height 1080]                        one full-resolution frame
  cleanup [URL | --all]                                delete cached data

Exit codes: 0 ok, 1 error, 2 missing yt-dlp/ffmpeg, 3 blocked by YouTube, 4 no captions.
"""
import argparse
import json
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ctube import cache, captions, frames, proc, scenes, youtube  # noqa: E402
from ctube.timefmt import fmt_time, parse_range, parse_time  # noqa: E402

FULL_PRINT_TOKENS = 12000
SEGMENT_S = 600  # synthetic chapter length for long videos without chapters
HD_SEEK_LIMIT = 24  # more frames than this without a scan copy -> download the scan copy instead


class _ReaderGone(Exception):
    """stdout's reader closed the pipe (Windows has no SIGPIPE; it raises EINVAL/EPIPE instead)."""


def out(*a):
    try:
        print(*a, flush=True)
    except OSError as e:
        raise _ReaderGone() from e


def _ctx(url):
    vid = youtube.video_id(url)
    return vid, youtube.watch_url(vid), cache.video_dir(vid)


def _meta(url, vdir):
    return youtube.load_meta(vdir) or youtube.fetch_info(url, vdir)


# ---------- info ----------

def _summary(md: str, path: Path) -> str:
    head = md.split("## Transcript")[0].rstrip()
    lines = [head, "", f"Transcript is long (~{captions.estimate_tokens(md)} tokens). Per chapter:"]
    n = 1
    while True:
        try:
            sec = captions.chapter_section(md, n)
        except KeyError:
            break
        lines.append(f"  {n}. ~{captions.estimate_tokens(sec)} tokens")
        n += 1
    lines += ["", f"Read a chapter with: info URL --chapter N   (full file: {path})"]
    return "\n".join(lines)


def cmd_info(a):
    vid, url, vdir = _ctx(a.url)
    md_path = vdir / "transcript.md"
    meta = youtube.load_meta(vdir)
    if a.lang or not (meta and md_path.exists()):
        meta = youtube.fetch_info(url, vdir, a.lang)
        cap = meta["caption"]["file"]
        paras = []
        if cap:
            frags = captions.parse_json3(json.loads(Path(cap).read_text(encoding="utf-8")))
            if not meta["chapters"] and frags and frags[-1][0] > SEGMENT_S * 3 / 2:
                end = meta.get("duration") or frags[-1][0]
                meta["chapters"] = [
                    {"start_time": s, "title": f"Segment {i + 1} ({fmt_time(s)}–{fmt_time(min(s + SEGMENT_S, end))})"}
                    for i, s in enumerate(range(0, int(end), SEGMENT_S))
                ]
                meta["synthetic_chapters"] = True
                youtube.save_meta(vdir, meta)
            paras = captions.paragraphs(frags, breaks=[c["start_time"] for c in meta["chapters"]])
        for p in vdir.glob("subs.*.json3"):
            p.unlink()
        md_path.write_text(captions.render(meta, paras), encoding="utf-8")
    if a.prefetch:
        youtube.start_prefetch(url, vdir, Path(__file__).resolve())
    md = md_path.read_text(encoding="utf-8")
    if a.chapter:
        out(captions.chapter_section(md, a.chapter))
    elif captions.estimate_tokens(md) <= FULL_PRINT_TOKENS:
        out(md)
    else:
        out(_summary(md, md_path))
    if a.prefetch:
        out("(scan copy downloading in the background for fast frames)")
    if not meta["caption"]["file"]:
        out("NO_CAPTIONS: this video has no captions. Rely on frames (frames --scenes / --every).")
        return 4
    return 0


# ---------- frames ----------

def _times(a, meta, url, vdir):
    dur = float(meta.get("duration") or 0)
    rng = parse_range(a.range) if a.range else (0.0, dur)
    if a.scenes:
        scan = youtube.ensure_scan(url, vdir)
        raw = frames.tiny_frames(scan, *(rng if a.range else (None, None)))
        evs = scenes.detect(scenes.split_raw(raw, 32, 18), 32, 18, start=rng[0],
                            threshold=a.threshold)
        kept = scenes.limit(evs, a.max)
        out(f"scene changes found: {len(evs)}; showing {len(kept)}"
            + ("" if len(kept) == len(evs) else f" strongest (raise --max to see more)"))
        chapters = meta.get("chapters") or []
        if chapters and evs:
            for i, c in enumerate(chapters):
                end = chapters[i + 1]["start_time"] if i + 1 < len(chapters) else float("inf")
                n = sum(c["start_time"] <= e.t < end for e in evs)
                if n:
                    out(f"  ch{i + 1} {c['title']}: {n}")
        return [e.t for e in kept]
    if a.every:
        if a.every <= 0:
            raise ValueError("--every must be > 0")
        ts, t = [], rng[0]
        while t <= rng[1]:
            ts.append(t)
            t += a.every
        return ts
    if a.times:
        return [parse_time(t) for t in a.times]
    raise ValueError("give timestamps, --range A-B --every S, or --scenes")


def _check_times(ts, meta):
    dur = float(meta.get("duration") or 0)
    bad = [t for t in ts if t < 0 or (dur and t > dur)]
    if bad:
        raise ValueError(f"time(s) outside the video (0–{fmt_time(dur)}): {', '.join(fmt_time(t) for t in bad)}")
    return sorted(set(min(t, max(dur - 0.5, 0)) if dur else t for t in ts))


def _hd_getter(url, vdir, height):
    return lambda force: youtube.stream_url(url, vdir, height, force=force)


def cmd_frames(a):
    vid, url, vdir = _ctx(a.url)
    meta = _meta(url, vdir)
    try:
        cols, rows = (int(x) for x in a.grid.lower().split("x"))
    except ValueError:
        raise ValueError(f"bad --grid {a.grid!r} (want e.g. 3x3)") from None
    ts = _check_times(_times(a, meta, url, vdir), meta)
    if not ts:
        out("no frames selected")
        return 0
    detail = a.hd or cols <= 2
    # Local scan copy when it's ready (instant) or when there are too many frames for HD seeks;
    # a few frames while the prefetch is still running are faster as HD seeks than waiting.
    scan_ready = youtube.scan_file(vdir) and not youtube.prefetch_running(vdir)
    use_local = not detail and (scan_ready or a.scenes or len(ts) > HD_SEEK_LIMIT)
    fdir = vdir / "frames"
    if use_local:
        got = frames.grab_local(youtube.ensure_scan(url, vdir), ts, fdir)
    else:
        got = frames.grab_hd(_hd_getter(url, vdir, a.height), ts, fdir, a.height)
    failed = {t for t, p in got.items() if p is None}
    if a.single:
        for t in ts:
            out(f"{fmt_time(t):>8}  {got[t] or 'FAILED'}")
        return 0
    tile_w = 640 if cols >= 3 else 960
    sdir = vdir / "sheets"
    sdir.mkdir(exist_ok=True)
    groups = frames.layout(ts, cols, rows)
    out(f"{len(ts)} frames -> {len(groups)} sheet(s), {cols}x{rows}, read left-to-right, top-to-bottom"
        + (" (! = frame failed, black tile)" if failed else ""))
    for g in groups:
        name = f"sheet_{int(g[0]):06d}_{int(g[-1]):06d}_{cols}x{rows}{'_hd' if not use_local else ''}.jpg"
        g_rows = min(rows, -(-len(g) // cols))  # no empty rows on a partly filled sheet
        p = frames.build_sheet([got[t] for t in g], cols, g_rows, tile_w, sdir / name)
        out(frames.legend(p, g, cols, failed))
    return 0


def cmd_frame(a):
    vid, url, vdir = _ctx(a.url)
    meta = _meta(url, vdir)
    (t,) = _check_times([parse_time(a.time)], meta)
    got = frames.grab_hd(_hd_getter(url, vdir, a.height), [t], vdir / "frames", a.height)
    if not got[t]:
        raise RuntimeError(f"could not grab frame at {fmt_time(t)}")
    out(f"{fmt_time(t)}  {got[t]}")
    return 0


# ---------- cleanup / internal ----------

def _stop_prefetch(vdir: Path):
    try:
        st = json.loads((vdir / "scan.status").read_text())
        if st.get("state") == "running" and st.get("pid"):
            if proc.alive(st["pid"]):
                proc.kill_tree(st["pid"])
    except (OSError, ValueError, ProcessLookupError):
        pass


def cmd_cleanup(a):
    if a.all:
        for d in cache.root().iterdir():
            if d.is_dir():
                _stop_prefetch(d)
        freed = cache.remove_all()
    elif a.url:
        vid = youtube.video_id(a.url)
        _stop_prefetch(cache.root() / vid)
        freed = cache.remove(vid)
    else:
        raise ValueError("give a URL or --all")
    out(f"cleaned up, freed {freed / 1e6:.1f} MB")
    return 0


def cmd_scan(a):
    vid, url, vdir = _ctx(a.url)
    youtube.download_scan(url, vdir)
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="claudetube", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("info", help="transcript + chapters")
    s.add_argument("url")
    s.add_argument("--chapter", type=int)
    s.add_argument("--lang")
    s.add_argument("--prefetch", action="store_true", help="download the low-res scan copy in the background")
    s.set_defaults(fn=cmd_info)

    s = sub.add_parser("frames", help="contact sheets of many frames")
    s.add_argument("url")
    s.add_argument("times", nargs="*")
    s.add_argument("--range")
    s.add_argument("--every", type=float)
    s.add_argument("--scenes", action="store_true")
    s.add_argument("--threshold", type=float, default=0.03)
    s.add_argument("--max", type=int, default=45)
    s.add_argument("--grid", default="3x3")
    s.add_argument("--hd", action="store_true", help="frames from the HD stream instead of the scan copy")
    s.add_argument("--height", type=int, default=720)
    s.add_argument("--single", action="store_true", help="individual frames, no sheets")
    s.set_defaults(fn=cmd_frames)

    s = sub.add_parser("frame", help="one full-resolution frame")
    s.add_argument("url")
    s.add_argument("time")
    s.add_argument("--height", type=int, default=1080)
    s.set_defaults(fn=cmd_frame)

    s = sub.add_parser("cleanup", help="delete cached data")
    s.add_argument("url", nargs="?")
    s.add_argument("--all", action="store_true")
    s.set_defaults(fn=cmd_cleanup)

    s = sub.add_parser("_scan")
    s.add_argument("url")
    s.set_defaults(fn=cmd_scan)
    return p


def main(argv=None) -> int:
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # quiet exit when piped into `head`
    for s in (sys.stdout, sys.stderr):  # titles/transcripts are Unicode; Windows pipes default to cp1252
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    a = build_parser().parse_args(argv)
    try:
        cache.sweep()
        if a.cmd != "cleanup":
            proc.need("yt-dlp", "ffmpeg")
        return a.fn(a)
    except _ReaderGone:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())  # silence the exit-time flush
        return 0
    except proc.MissingDep as e:
        print(f"MISSING_DEPENDENCY: {e}", file=sys.stderr)
        return 2
    except youtube.Blocked as e:
        print(f"BLOCKED: YouTube refused yt-dlp ({e}). Use the Chrome-extension fallback in "
              "fallback.md, or ask the user whether to retry with their browser cookies "
              "(they set CLAUDETUBE_BROWSER=chrome themselves).", file=sys.stderr)
        return 3
    except (ValueError, KeyError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
