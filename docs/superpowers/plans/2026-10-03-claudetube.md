# ClaudeTube Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> Execution note: the user pre-approved building after spec review; this plan is executed
> natively by the author in the same session. Test cases are specified exactly; code is written
> TDD-style during execution.

**Goal:** A Claude Code plugin whose skill + stdlib-Python CLI lets Claude read a YouTube video's transcript and any number of frames (as contact sheets) in seconds.

**Architecture:** `skills/watch-youtube/scripts/claudetube.py` is a thin CLI over a small package
`scripts/ctube/` (one module per responsibility). External tools (`yt-dlp`, `ffmpeg`) are invoked
only through `ctube.proc.run`, so everything else is unit-testable offline.

**Tech Stack:** Python ≥ 3.9 stdlib, yt-dlp, ffmpeg, pytest (dev only).

**Spec:** `docs/superpowers/specs/2026-10-03-claudetube-design.md`

## Global Constraints

- Python ≥ 3.9, standard library only at runtime.
- Runtime deps on PATH: `yt-dlp`, `ffmpeg` (also `ffprobe` not required).
- Cache root: `$CLAUDETUBE_CACHE` or `~/.cache/claudetube/<video-id>/`; folders older than 24 h are deleted on every invocation.
- Exit codes: 0 ok, 1 other error, 2 missing dependency, 3 blocked by YouTube, 4 no captions.
- Cookie retry browser: `$CLAUDETUBE_BROWSER` (default `chrome`).
- Default sheet grid 3x3, tile width 640 px; HD default height 720; `frame` default 1080.
- HD seek concurrency 16; scan copy 360p avc1 downloaded with `-N 8 --http-chunk-size 10M`.
- Transcript printed in full only if ≤ 12 000 estimated tokens (chars / 4).

## Review Focus

1. Video with chapters missing → transcript must still render as a single section; `--chapter` errors clearly.
2. Timestamps beyond the video duration or malformed (`1:2:3:4`, `abc`) → clear error, no ffmpeg call.
3. Manual-caption json3 (one seg per event, embedded `\n`) → parsed same as auto captions.
4. Static screencast (no changes) or constant webcam motion → scene mode returns zero/few events, not hundreds.
5. Stale `scan.status` from a killed prefetch → `frames` must not wait forever (timeout + re-download).

---

### Task 1: Scaffold, time utils, cache

**Files:**
- Create: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `LICENSE`, `.gitignore`, `pyproject.toml` (pytest config only)
- Create: `skills/watch-youtube/scripts/ctube/__init__.py`, `ctube/timefmt.py`, `ctube/cache.py`
- Test: `tests/test_timefmt.py`, `tests/test_cache.py`, `tests/conftest.py` (adds scripts dir to sys.path)

**Interfaces — Produces:**
- `timefmt.parse_time(s: str) -> float` — accepts `SS`, `SS.s`, `MM:SS`, `HH:MM:SS`; raises `ValueError` otherwise.
- `timefmt.fmt_time(sec: float) -> str` — `MM:SS` under 1 h, else `H:MM:SS`.
- `timefmt.parse_range(s: str) -> tuple[float, float]` — `"A-B"`; raises if B ≤ A.
- `cache.root() -> Path`, `cache.video_dir(video_id) -> Path` (created), `cache.sweep(max_age_s=86400) -> int` (dirs removed), `cache.remove(video_id) -> int` (bytes freed), `cache.remove_all() -> int`.

Tests: `parse_time("90")==90`, `("1:30")==90`, `("1:02:03")==3723`, `("12.5")==12.5`, raises on `"abc"`, `"1:2:3:4"`, `"-5"`; `fmt_time(65)=="01:05"`, `fmt_time(3723)=="1:02:03"`; `parse_range("1:00-2:00")==(60,120)`, raises on `"2:00-1:00"`; sweep removes a dir with mtime 25 h old and keeps a fresh one; remove returns >0 bytes and deletes dir.

- [ ] Write failing tests → run → implement → pass → commit `feat: scaffold plugin, time utils, cache`

### Task 2: Captions → transcript

**Files:** Create `ctube/captions.py`; Test `tests/test_captions.py`, fixtures `tests/fixtures/auto.json3` (first ~150 events of the real donut video), `tests/fixtures/manual.json3` (hand-written, 4 events with `\n`).

**Interfaces — Produces:**
- `captions.parse_json3(data: dict) -> list[tuple[float, str]]` — word/fragment level `(t_seconds, text)`; skips `"\n"`-only segs; seg time = `(tStartMs + tOffsetMs)/1000`; collapses whitespace; strips `[Music]`-style tags? No — keep them (they carry meaning).
- `captions.paragraphs(frags, min_len=20.0, max_len=35.0) -> list[tuple[float, str]]` — start a new paragraph when current span ≥ min_len and the fragment ends with `.?!`, or span ≥ max_len.
- `captions.render(meta: dict, paras) -> str` — markdown per spec §4.1; chapters from `meta["chapters"]` (`start_time`, `title`), paragraphs grouped under `### N. title` by start time; no chapters → single `## Transcript` section without `###`.
- `captions.chapter_section(md: str, n: int) -> str` — returns `### n.` section text; raises `KeyError` if absent.
- `captions.estimate_tokens(s: str) -> int` — `len(s)//4`.

Tests: fixture auto parses to first fragment `(0.08, "So,")`; no `"\n"` fragments; manual fixture yields lines split on `\n` joined with spaces; paragraphs never exceed max_len span; paragraph text concatenates all fragments (no word lost: joined words == joined paragraph words); render with 2 chapters puts paragraph at t=10 under chapter 1 and t=100 under chapter 2 when chapter 2 starts at 50; render with no chapters has no `###`; chapter_section(…,2) returns only chapter 2.

- [ ] TDD cycle → commit `feat: compact transcript rendering from json3`

### Task 3: Scene detection

**Files:** Create `ctube/scenes.py`; Test `tests/test_scenes.py`.

**Interfaces — Produces:**
- `scenes.detect(frames: Iterable[bytes], w: int, h: int, start: float = 0.0, fps: float = 1.0, grid=(16, 9), pix_thresh=6, noisy_frac=0.4, threshold=…, ) -> list[Event]`
- `Event = namedtuple("Event", "t strength")` — `t` = first stable second after a burst (seconds, absolute).
- `scenes.limit(events, max_n) -> list[Event]` — strongest `max_n`, re-sorted by `t`.
- `scenes.read_raw(stream, w, h) -> Iterator[bytes]` — chunks a raw gray stream into frames.

Tests (synthetic 64x36 gray frames): all-identical → `[]`; a region (cells in bottom-right 4x3) changing every frame + otherwise static → `[]` (masked); full-frame switch at frame 10 then static → one event with `t == start + 11`; a 3-frame burst (frames 10–12 changing) → one event at `t == 13`; burst reaching the end without settling → event at last frame time; `limit` keeps strongest and returns time-sorted.

- [ ] TDD cycle → commit `feat: webcam-robust scene change detection`

### Task 4: Process runner, YouTube access, frames, sheets

**Files:** Create `ctube/proc.py`, `ctube/youtube.py`, `ctube/frames.py`; Test `tests/test_youtube.py`, `tests/test_frames.py`.

**Interfaces — Produces:**
- `proc.run(args: list[str], timeout=None) -> CompletedProcess` (text, captured); `proc.need(*bins)` raises `MissingDep(name)`.
- `youtube.video_id(url_or_id: str) -> str` — handles `watch?v=`, `youtu.be/`, `shorts/`, `live/`, `embed/`, bare 11-char id; raises `ValueError`.
- `youtube.Blocked(Exception)`, `youtube.is_blocked(stderr: str) -> bool` — matches "Sign in to confirm", "not a bot", "HTTP Error 429".
- `youtube.ytdlp(args, url) -> CompletedProcess` — runs, retries once with `--cookies-from-browser $CLAUDETUBE_BROWSER` if blocked, raises `Blocked`.
- `youtube.fetch_info(url, vdir, lang=None) -> dict` — one call `-J --no-simulate --skip-download --write-subs --write-auto-subs --sub-format json3 --sub-langs <pick>`; writes `meta.json`; returns meta incl. `caption_file` or None.
- `youtube.pick_sub_langs(lang) -> str` — default `"en,en-orig,.*-orig"`… implemented as: `lang` given → `f"{lang},{lang}-orig"`; else `"en,en-orig,en-US,en-GB"` then fallback second call with `".*-orig"` if no file produced.
- `youtube.stream_url(url, vdir, height) -> str` — cached in `meta.json` under `streams[str(height)]` with `expire` from the URL's `expire=` param; refreshed when < 5 min left or `force=True`.
- `youtube.start_prefetch(url, vdir)` — detached `Popen` of `claudetube.py _scan URL` (start_new_session); `youtube.download_scan(url, vdir)` writes `scan.status` (`running pid ts` / `done` / `failed msg`) and `scan.mp4`.
- `youtube.ensure_scan(url, vdir, timeout=1800) -> Path` — waits on a running prefetch whose pid is alive; stale/failed → downloads itself.
- `frames.grab_hd(stream_url, times, outdir, workers=16) -> dict[float, Path|None]` — retries failures once via callback that refreshes the URL.
- `frames.grab_local(scan, times, outdir) -> dict[float, Path|None]` — parallel `ffmpeg -ss t -i scan.mp4 -frames:v 1`.
- `frames.layout(times, cols, rows) -> list[list[float]]` — chunks into sheets.
- `frames.build_sheet(paths, cols, rows, tile_w, out) -> Path` — ffmpeg `xstack`/`tile` with black padding for missing cells; `drawtext` labels only if `has_drawtext()`.
- `frames.legend(sheet_path, times, cols) -> str` — `"<path>\n  r1: 01:25 01:30 01:35\n  r2: …"`.

Tests: video_id for 6 URL shapes + bad input; is_blocked positives/negatives; stream expiry parsing from a URL with `expire=1791005546`; layout of 20 times at 3x3 → sheets of 9, 9, 2; legend row formatting; ytdlp retry logic with `proc.run` monkeypatched (first blocked, second ok → ok; both blocked → `Blocked`); ensure_scan with stale pid status re-downloads (monkeypatch download_scan).

- [ ] TDD cycle → commit `feat: youtube access, HD/local frame grabbing, contact sheets`

### Task 5: CLI

**Files:** Create `skills/watch-youtube/scripts/claudetube.py`; Test `tests/test_cli.py`.

Commands per spec §4: `info`, `frames`, `frame`, `cleanup`, hidden `_scan`. Selection validation: times within `[0, duration]`; `--every` > 0; exactly one selection kind. `frames` source choice: `--hd` → HD; scan copy exists or prefetch running → local; else ≤ 24 frames → HD, else ensure_scan then local. `--scenes` always ensure_scan. Prints per-chapter event counts in scene mode.

Tests (monkeypatched youtube/frames): `cleanup --all` on temp cache prints freed bytes, exit 0; `frames` with time beyond duration → exit 1 + message, no grab call; missing dep → exit 2; `Blocked` → exit 3 + `BLOCKED`; info with no caption file → exit 4 + `NO_CAPTIONS` and still writes transcript header.

- [ ] TDD cycle → commit `feat: claudetube CLI`

### Task 6: Live verification + scene threshold tuning

- [ ] Run `info --prefetch` on `z-Xl9tGqH14` and a short video; inspect transcript.md size and readability.
- [ ] Run `--scenes` on chapter 2 of the donut video; tune `threshold` default so events track real UI/state changes (target: tens per 10 min, not hundreds); view sheets.
- [ ] `frame` at 1080 readable; `cleanup` leaves nothing. Add opt-in live test `tests/test_live.py` (`CLAUDETUBE_LIVE=1`).
- [ ] Commit `test: live smoke test; tune scene threshold`

### Task 7: Chrome fallback, SKILL.md, README, benchmark

**Files:** Create `skills/watch-youtube/scripts/transcript.js`, `skills/watch-youtube/SKILL.md`, `README.md`, `bench/README.md`.

- `transcript.js`: async IIFE returning `{title, chapters, lines}`; tries captionTracks json3 fetch, else opens transcript panel and scrapes segments (`ytd-transcript-segment-renderer` and the newer panel's segment elements), scrolling until stable.
- SKILL.md per spec §6 with exact commands, frame-budget decision table, cleanup rule, fallback steps.
- Verify the JS on a real watch page via Claude in Chrome if available; otherwise mark untested in README.
- [ ] Commit `docs: skill, README, benchmark, chrome fallback`; push.
