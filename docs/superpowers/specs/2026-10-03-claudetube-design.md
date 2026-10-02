# ClaudeTube — Design Spec

**Date:** 2026-10-03
**Repo:** `moazessam376-dev/claudetube` (public, MIT)
**Status:** Draft for review

## 1. Goal

Let Claude "watch" a YouTube video as fast and cheaply as possible while understanding its full
context: transcript + chapters first, then exactly as many frames as the video needs (zero to
many hundreds), chosen by Claude per video.

Built-in browsers get blocked by YouTube's bot checks, and browser screenshots cost one
round-trip per frame. ClaudeTube moves the work to a local CLI (`yt-dlp` + `ffmpeg`) and packs
frames into contact sheets so Claude reads many frames per image.

**Success criteria**

- Transcript + chapters for any captioned video in < 15 s.
- Any set of N HD frames in ≈ N × 0.5 s / 8 (parallel streamed seeks), no full download.
- Scene-change scan of a whole video bounded by download of a throwaway low-res copy
  (measured: 4h19m video → 2m42s download + 37s local scan; a 20-min video → seconds).
- Nothing left on disk after `cleanup`; nothing older than 24 h ever survives a run.
- Benchmark: Opus 5.5 (medium/high) follows the Blender Guru donut tutorial
  significantly faster than the 35-minute reference run
  (https://x.com/ronedgecomb/status/2102774358095561139).

**Non-goals (v1):** Whisper transcription for caption-less videos, an MCP server, non-YouTube sites
(yt-dlp may work on them incidentally, but they are untested and unsupported).

## 2. Measured feasibility (2026-10-03, on the author's Mac)

Test video: *Beginner Blender Tutorial (2026)*, `z-Xl9tGqH14`, 4h19m, 8 chapters.

| Operation | Result |
|---|---|
| `yt-dlp` transcript (json3) + chapters + stream URL, no cookies | 7.7 s |
| 12 HD frames via parallel `ffmpeg -ss T -i <stream-url>` seeks | 5.9 s, ~1 MB total |
| Tile 12 frames into one sheet | 0.06 s |
| Scene scan by streaming through ffmpeg (single connection) | 4m41s per **10 min** — throttled, rejected |
| `yt-dlp -f 134 -N 8 --http-chunk-size 10M` (360p, full video) | 2m42s, 364 MB |
| Local scene detect on that file (`fps=1,scale=160,select=scene`) | 37 s |

Conclusions: random-access seeks on the stream are fast; continuous decoding through the stream is
throttled. So scanning uses a temporary low-res download; reading uses HD seeks.

Raw json3 captions for this video are 5.4 MB, so the transcript must be compacted before Claude
reads it.

## 3. Packaging

The repo is a Claude Code plugin **and** its own marketplace:

```
claudetube/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── skills/watch-youtube/
│   ├── SKILL.md
│   └── scripts/
│       ├── claudetube.py      # single file, Python ≥ 3.9 stdlib only
│       └── transcript.js      # Chrome-extension fallback
├── tests/                     # pytest, offline by default
├── bench/README.md            # benchmark protocol + results table
├── docs/superpowers/specs/    # this spec
├── README.md
└── LICENSE                    # MIT
```

Install:

```
/plugin marketplace add moazessam376-dev/claudetube
/plugin install claudetube@claudetube
```

Runtime dependencies: `yt-dlp` and `ffmpeg` on PATH. The CLI checks for them and prints the
install command (`brew install yt-dlp ffmpeg` / `pipx install yt-dlp`) if missing.

## 4. CLI: `claudetube.py`

All commands take a YouTube URL or bare video id. Times accept `SS`, `MM:SS`, `HH:MM:SS`.
Working data lives in `$CLAUDETUBE_CACHE` (default `~/.cache/claudetube/<video-id>/`).
Every invocation first deletes any video folder whose mtime is older than 24 h.

### 4.1 `info <url> [--chapter N] [--lang en]`

One `yt-dlp` call (`--skip-download --write-subs --write-auto-subs --sub-format json3`,
`--print` for metadata). Prefers manual subs over auto subs, and the original-language track.

Writes `transcript.md`:

```
# <title>
channel · duration · upload date · url

## Chapters
1. [00:00] Part 1 The Basics
2. [28:16] Part 2 Basic Modelling
...

## Transcript
### 1. Part 1 The Basics
[00:00] merged text … (paragraphs of ~20–30 s, split on sentence ends, de-duplicated
auto-caption rolling text)
...
```

Also writes `meta.json` (title, duration, chapters, stream URL + expiry, caption source).

Stdout: if the transcript is ≤ ~12k tokens (estimated as chars / 4) it prints the whole file;
otherwise it prints the header + chapter list + per-chapter token estimates, and the path, so
Claude reads with `--chapter N` (prints only that chapter's section).

The raw json3 file is deleted after parsing.

### 4.2 `frames <url> <selection> [--grid CxR] [--height H] [--single]`

Selection (exactly one):

- `T1 T2 T3 …` — explicit timestamps.
- `--range A-B --every S` — uniform sampling in a range (range defaults to whole video).
- `--scenes [--range A-B] [--threshold X] [--max N]` — scene-change mode (§4.3).

Frames are pulled by parallel (8 workers) `ffmpeg -ss T -i <stream-url> -frames:v 1` at
`--height` (default 720; picks the best avc1 ≤ H, falling back to any codec ≤ H).

Output: contact sheets, default `--grid 3x3`, each tile 640 px wide, timestamp burned into
the tile's corner with `drawtext` (if ffmpeg lacks drawtext, no burn-in; the legend below still
gives the mapping). Sheets are written in time order as `sheet_<start>_<end>.jpg`.
`--single` writes individual frames instead of sheets.

Stdout: one line per sheet: path + the timestamps of its tiles in reading order. Claude then
reads the sheet images with its Read tool.

Guidance baked into SKILL.md: 3×3 for scanning/following shape changes (~200 tokens/frame);
2×2 or `frame` for reading small UI text and exact values.

### 4.3 Scene-change mode

1. If `scan.mp4` is not in the cache, download the lowest avc1 format ≥ 240p (prefer 360p)
   with `yt-dlp -N 8 --http-chunk-size 10M`.
2. Run `ffmpeg -i scan.mp4 [-ss A -to B] -vf "fps=1,scale=160:-1,select='gt(scene,X)',showinfo"`
   and parse `pts_time` from showinfo to get change timestamps. Default threshold tuned on the
   test video during implementation (screen recordings change subtly; expect ~0.02–0.05).
3. Collapse changes closer than 2 s together (keep the later one, i.e. the settled screen).
4. If `--max N` is exceeded, keep the N highest-scoring changes, then re-sort by time.
5. Grab those timestamps as HD frames via §4.2 and build sheets.
6. Delete `scan.mp4` right after detection unless `--keep-scan` is given (lets Claude scan
   several ranges without re-downloading).

Stdout additionally reports how many changes were found per chapter, so Claude can budget.

### 4.4 `frame <url> <t> [--height 1080]`

One full-resolution frame, path printed. For reading exact numbers, menus, code.

### 4.5 `cleanup [<url> | --all]`

Removes that video's folder, or the whole cache. Prints bytes freed.

### 4.6 Error handling and exit codes

| Situation | Behaviour | Exit |
|---|---|---|
| `yt-dlp`/`ffmpeg` missing | print install command | 2 |
| Bot check / "Sign in to confirm" | retry once with `--cookies-from-browser chrome` (browser overridable via `$CLAUDETUBE_BROWSER`) | — |
| Still blocked | print `BLOCKED` + reason, SKILL.md switches to Chrome fallback | 3 |
| No captions | write metadata + chapters, print `NO_CAPTIONS` | 4 |
| Stream URL expired / HTTP 403 on seek | refresh URL once, retry failed frames | — |
| Any single frame still failing | skip it, list it as failed in stdout | 0 |
| Other errors | message on stderr | 1 |

## 5. Chrome-extension fallback (`transcript.js`)

Used only when the CLI exits 3. Runs in the user's real Chrome via the Claude in Chrome
extension (`javascript_tool`) on the video's watch page:

1. Try the caption track from `ytInitialPlayerResponse.captions…captionTracks[].baseUrl` +
   `&fmt=json3`, fetched same-origin with the user's session; return compact `[mm:ss] text` lines.
2. If that returns empty, open the "In this video → Transcript" panel (or legacy "Show
   transcript") and scrape the segment elements, scrolling the list until complete.
3. Return chapters from the page as well.

Frames in fallback mode: seek `video.currentTime = t`, wait for `seeked`, screenshot. Slower;
SKILL.md tells Claude to keep the frame count minimal here.

## 6. SKILL.md — the watching strategy

Trigger: any request to watch, summarize, learn from, or follow a YouTube video.

1. **Always transcript first.** `info`. For long videos, read chapter by chapter as needed.
2. **Decide the frame budget for this video and this goal** (the core judgement):
   - *None* — podcasts, interviews, talks, talking heads, or when the question is answerable
     from speech.
   - *Targeted* — slides/diagrams referenced in speech ("as you can see here"); grab those
     timestamps.
   - *Dense* — tutorials the user wants to reproduce (software, crafts, code on screen):
     `--scenes` over the relevant chapters, plus `frame --height 1080` wherever an exact value,
     shortcut or setting must be read and the transcript doesn't state it.
   - *Uniform* — visual content without speech cues (montages, gameplay): `--every`.
3. Batch: one `frames` call per chapter/range, never one call per frame.
4. For "follow this tutorial": produce a numbered step list (action, exact values, expected
   result + timestamp) before acting; re-check frames only when a result doesn't match.
5. Always `cleanup` when done.
6. If exit code 3: switch to the Chrome fallback (§5).

## 7. Testing

- `pytest`, offline: json3 parsing and rolling-caption de-duplication (fixture trimmed from the
  test video), paragraph merging, chapter assignment, time parsing/formatting, grid layout and
  legend, scene-change collapsing and `--max` selection, cache TTL sweep.
- External calls (`yt-dlp`, `ffmpeg`) wrapped in one small module-level runner so tests can
  stub them.
- Opt-in live smoke test (`CLAUDETUBE_LIVE=1`): `info`, `frames` with 3 timestamps, `--scenes`
  on a short public video, `cleanup`, asserting the cache folder is gone.

## 8. Benchmark (`bench/README.md`)

- Video: Blender Guru *Beginner Blender Tutorial (2026)* (`z-Xl9tGqH14`), or the specific
  part(s) used in the reference run.
- Setup: Claude Code + ClaudeTube plugin + Blender MCP, Opus 5.5 at medium and at high.
- Prompt: fixed text given in the file.
- Record: total wall time, "watch" time (until the step list exists), number of frames
  viewed, tokens, final render screenshot. Reference: 35 min.
