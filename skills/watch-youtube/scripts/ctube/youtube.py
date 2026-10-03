"""Everything that talks to YouTube via yt-dlp: metadata, captions, stream URLs, scan copy."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import proc

_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_BLOCK_MARKERS = ("sign in to confirm", "not a bot", "http error 429", "too many requests")


class Blocked(Exception):
    pass


def video_id(s: str) -> str:
    s = s.strip()
    if _ID.match(s):
        return s
    u = urlparse(s if "//" in s else "https://" + s)
    host = (u.hostname or "").lower()
    if host.endswith("youtu.be"):
        cand = u.path.strip("/").split("/")[0]
    elif "youtube" in host:
        q = parse_qs(u.query)
        if "v" in q:
            cand = q["v"][0]
        else:
            parts = u.path.strip("/").split("/")
            cand = parts[1] if len(parts) > 1 and parts[0] in ("shorts", "live", "embed", "v") else ""
    else:
        cand = ""
    if not _ID.match(cand):
        raise ValueError(f"not a YouTube video URL or id: {s!r}")
    return cand


def watch_url(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


def is_blocked(stderr: str) -> bool:
    low = (stderr or "").lower()
    return any(m in low for m in _BLOCK_MARKERS)


def ytdlp(args, url) -> subprocess.CompletedProcess:
    """Run yt-dlp; if YouTube blocks us, retry once with the user's browser cookies."""
    base = ["yt-dlp", "--no-warnings", "--no-progress"]
    r = proc.run(base + args + [url])
    if r.returncode != 0 and is_blocked(r.stderr):
        browser = os.environ.get("CLAUDETUBE_BROWSER", "chrome")
        r = proc.run(base + ["--cookies-from-browser", browser] + args + [url])
        if r.returncode != 0 and is_blocked(r.stderr):
            raise Blocked(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "blocked")
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {r.stderr.strip()[-500:]}")
    return r


# ---------- metadata + captions ----------

def _trim_formats(formats):
    out = []
    for f in formats or []:
        if f.get("vcodec") in (None, "none") or f.get("acodec") not in (None, "none"):
            continue
        if f.get("protocol") != "https" or not f.get("height") or not f.get("url"):
            continue
        out.append({k: f.get(k) for k in ("format_id", "height", "vcodec", "ext", "url")}
                   | {"size": f.get("filesize") or f.get("filesize_approx") or 0})
    return out


def url_expiry(url: str) -> float:
    m = re.search(r"[?&/]expire[=/](\d+)", url)
    return float(m.group(1)) if m else time.time() + 3 * 3600


def pick_caption(vdir: Path, info: dict, lang=None):
    """Choose the best downloaded caption file: manual > original-language auto > English auto."""
    files = {p.name[len("subs."):-len(".json3")]: p for p in vdir.glob("subs.*.json3")}
    manual = set((info.get("subtitles") or {}).keys())
    order = []
    if lang:
        order += [lang, f"{lang}-orig"]
    order += [k for k in files if k in manual and k.startswith("en")]
    order += sorted(k for k in files if k.endswith("-orig"))
    order += ["en"] + sorted(files)
    for k in order:
        if k in files:
            return files[k], ("manual" if k in manual else "auto"), k
    return None, None, None


def fetch_info(url: str, vdir: Path, lang=None) -> dict:
    """One yt-dlp call: metadata + caption download. Writes and returns meta.json content."""
    langs = f"{lang},{lang}-orig" if lang else "en,en-orig,.*-orig"
    r = ytdlp(["-J", "--no-simulate", "--skip-download", "--write-subs", "--write-auto-subs",
               "--sub-format", "json3", "--sub-langs", langs, "-o", str(vdir / "subs.%(ext)s")], url)
    info = json.loads(r.stdout)
    cap, source, cap_lang = pick_caption(vdir, info, lang)
    meta = {k: info.get(k) for k in ("id", "title", "channel", "duration", "upload_date", "webpage_url")}
    meta["chapters"] = [{"start_time": c["start_time"], "title": c["title"]} for c in info.get("chapters") or []]
    meta["formats"] = _trim_formats(info.get("formats"))
    meta["formats_fetched"] = time.time()
    meta["caption"] = {"file": str(cap) if cap else None, "source": source, "lang": cap_lang}
    save_meta(vdir, meta)
    return meta


def save_meta(vdir: Path, meta: dict):
    (vdir / "meta.json").write_text(json.dumps(meta))


def load_meta(vdir: Path):
    p = vdir / "meta.json"
    return json.loads(p.read_text()) if p.exists() else None


def refresh_formats(url: str, vdir: Path, meta: dict) -> dict:
    r = ytdlp(["-J", "--skip-download"], url)
    meta["formats"] = _trim_formats(json.loads(r.stdout).get("formats"))
    meta["formats_fetched"] = time.time()
    save_meta(vdir, meta)
    return meta


def choose_hd(formats, height: int):
    """Best format at or below `height`, preferring H.264 (fastest to seek/decode)."""
    cands = [f for f in formats if f["height"] <= height] or sorted(formats, key=lambda f: f["height"])[:1]
    if not cands:
        return None
    return max(cands, key=lambda f: (f["height"], f["vcodec"].startswith("avc1"), -f["size"]))


def scan_codec() -> str:
    """Codec preferred for the scan copy. AV1 is the smallest download, but software AV1 decode is
    ~3.5x slower than H.264 on older x86 CPUs (measured on an i5-3570), and scene detection decodes
    the whole range. Macs decode AV1 fast, so they keep the smaller file."""
    return os.environ.get("CLAUDETUBE_SCAN_CODEC") or ("av01" if sys.platform == "darwin" else "avc1")


def choose_scan(formats, codec=None):
    """Smallest 360p stream in the preferred codec, else smallest 360p (fallback: nearest height in
    240..480, then anything smallest)."""
    codec = codec or scan_codec()
    for ok in (lambda h: h == 360, lambda h: 240 <= h <= 480, lambda h: True):
        cands = [f for f in formats if ok(f["height"]) and f["size"]] or [f for f in formats if ok(f["height"])]
        if cands:
            return min(cands, key=lambda f: (not f["vcodec"].startswith(codec), f["size"] or 1 << 62,
                                             abs(f["height"] - 360)))
    return None


def stream_url(url: str, vdir: Path, height: int, force=False) -> str:
    meta = load_meta(vdir) or fetch_info(url, vdir)
    f = choose_hd(meta["formats"], height)
    if force or f is None or url_expiry(f["url"]) - time.time() < 300:
        meta = refresh_formats(url, vdir, meta)
        f = choose_hd(meta["formats"], height)
    if f is None:
        raise RuntimeError("no downloadable video stream found")
    return f["url"]


# ---------- scan copy (low-res local file for scene detection + fast sheets) ----------

def scan_file(vdir: Path):
    files = [p for p in vdir.glob("scan.*") if p.suffix in (".mp4", ".webm", ".mkv")]
    return files[0] if files else None


def _status(vdir: Path):
    p = vdir / "scan.status"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def _set_status(vdir: Path, **st):
    (vdir / "scan.status").write_text(json.dumps(st))


def _alive(pid) -> bool:
    return proc.alive(pid)


def download_scan(url: str, vdir: Path) -> Path:
    _set_status(vdir, state="running", pid=os.getpid(), started=time.time())
    try:
        meta = load_meta(vdir) or fetch_info(url, vdir)
        f = choose_scan(meta["formats"])
        fmt = f["format_id"] if f else "worstvideo[height>=240]/worstvideo"
        try:
            ytdlp(["-f", fmt, "-N", "8", "--http-chunk-size", "10M", "-o", str(vdir / "scan.%(ext)s")], url)
        except RuntimeError:  # stale format list: refresh once
            meta = refresh_formats(url, vdir, meta)
            f = choose_scan(meta["formats"])
            ytdlp(["-f", f["format_id"] if f else "worstvideo", "-N", "8", "--http-chunk-size", "10M",
                   "-o", str(vdir / "scan.%(ext)s")], url)
    except Exception as e:
        _set_status(vdir, state="failed", error=str(e)[-300:])
        raise
    p = scan_file(vdir)
    _set_status(vdir, state="done" if p else "failed")
    if not p:
        raise RuntimeError("scan download produced no file")
    return p


def start_prefetch(url: str, vdir: Path, cli: Path):
    """Start the scan-copy download in a detached background process."""
    if scan_file(vdir):
        return
    st = _status(vdir)
    if st and st.get("state") == "running" and _alive(st.get("pid")):
        return
    log = open(vdir / "scan.log", "w", encoding="utf-8")
    p = proc.spawn_detached([sys.executable, str(cli), "_scan", url], log)
    _set_status(vdir, state="running", pid=p.pid, started=time.time())


def prefetch_running(vdir: Path) -> bool:
    st = _status(vdir)
    return bool(st and st.get("state") == "running" and _alive(st.get("pid")))


def ensure_scan(url: str, vdir: Path, timeout: float = 1800, poll: float = 0.5) -> Path:
    """Return the local scan copy, waiting for a running prefetch or downloading it now."""
    deadline = time.time() + timeout
    while True:
        st = _status(vdir)
        if st and st.get("state") == "done" and scan_file(vdir):
            return scan_file(vdir)
        if not (st and st.get("state") == "running" and _alive(st.get("pid"))):
            return download_scan(url, vdir)
        if time.time() > deadline:
            raise RuntimeError("timed out waiting for the background scan download")
        time.sleep(poll)
