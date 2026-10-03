# ClaudeTube design spec

**Date:** 2026-10-03
**Repo:** `moazessam376-dev/claudetube` (public, MIT)
**Status:** Approved (reviewed 2026-10-03)

## 1. Goal

Let Claude "watch" a YouTube video as fast and cheaply as possible while understanding its full
context: transcript + chapters first, then exactly as many frames as the video needs (zero to
many hundreds), chosen by Claude per video.

Built-in browsers get blocked by YouTube's bot checks, and browser screenshots cost one
round-trip per frame. ClaudeTube moves the work to a local CLI (`yt-dlp` + `ffmpeg`) and packs
frames into contact sheets so Claude reads many frames per image.

**Success criteria**

- Transcript + chapters for any captioned video in < 15 s.
- Contact sheets of hundreds of frames in seconds once the local low-res "scan copy" exists;
  the copy downloads in the background while Claude reads the transcript
  (measured: 4h19m video → 2m42s / 364 MB; a 20-min video → ~10–20 s / ~30 MB).
- HD frames (for reading exact values) by streamed seek: ~3.3 s for one, ~0.45 s/frame
  amortised at 24 in parallel, no full download.
- Scene-change detection robust to webcam overlays and cursor motion.
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
| 1 HD seek / 48 HD seeks at 24 parallel | 3.3 s / 21.5 s |
| Tile 12 frames into one sheet | 0.06 s |
| Scene scan by streaming through ffmpeg (single connection) | 4m41s per **10 min**: throttled, rejected |
| `yt-dlp -f 134 -N 8 --http-chunk-size 10M` (360p, full video) | 2m42s, 364 MB |
| Local scene detect on that file (`fps=1,scale=160,select=scene`) | 37 s |

Conclusions: random-access seeks on the stream work but cost ~0.45 s/frame even in parallel;
continuous decoding through the stream is throttled. A 3×3 sheet is shown to Claude at ~1568 px
wide, so each tile is ~520 px, so a 360p source (640 px) loses almost nothing there. Therefore:
sheets come from a temporary local 360p "scan copy" (instant extraction); HD streamed seeks are
reserved for frames where small text/values must be read.

Naive `select='gt(scene,0.02)'` found 4354 "changes" in 4h: the presenter's webcam overlay and
cursor keep the scene score high. Scene detection needs masking of constantly-changing regions
(§4.3).

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

### 4.1 `info <url> [--chapter N] [--lang L] [--prefetch]`

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

The raw json3 file is deleted after parsing. Only one caption track is downloaded (manual subs
in the requested/original language, else the `-orig` auto track, else `en`).

`--prefetch` starts the scan-copy download (§4.3 step 1) as a detached background process and
returns immediately; its progress/completion is recorded in `scan.status`. SKILL.md uses it
whenever the goal is visual (e.g. following a tutorial), so the download overlaps with Claude
reading the transcript.

### 4.2 `frames <url> <selection> [--grid CxR] [--height H] [--single]`

Selection (exactly one):

- `T1 T2 T3 …`: explicit timestamps.
- `--range A-B --every S`: uniform sampling in a range (range defaults to whole video).
- `--scenes [--range A-B] [--threshold X] [--max N]`: scene-change mode (§4.3).

Frame source:

- **Local (default when the scan copy exists or is being prefetched)**: wait for the prefetch
  to finish if needed, then extract from `scan.mp4` locally (milliseconds per frame).
- **HD (`--hd`, or no scan copy and ≤ 24 frames requested)**: parallel (16 workers)
  `ffmpeg -ss T -i <stream-url> -frames:v 1` at `--height` (default 720; best avc1 ≤ H, else
  any codec ≤ H). If > 24 frames are requested without a scan copy, the CLI downloads the
  scan copy first (cheaper than many seeks).

Output: contact sheets, default `--grid 3x3`, each tile 640 px wide, separated by a thin
padding line. The timestamp is burned into the tile's corner with `drawtext` only when ffmpeg
supports it: the default Homebrew ffmpeg does **not** (checked 2026-10-03), so the stdout
legend is the primary tile→timestamp mapping and burn-in is a bonus. Sheets are written in
time order as `sheet_<start>_<end>.jpg`.
`--single` writes individual frames instead of sheets.

Stdout: one line per sheet: path + the timestamps of its tiles in reading order. Claude then
reads the sheet images with its Read tool.

Guidance baked into SKILL.md: 3×3 for scanning/following shape changes (~200 tokens/frame);
2×2 or `frame` for reading small UI text and exact values.

### 4.3 Scene-change mode

1. Ensure the scan copy: if `scan.mp4` is not cached (and no prefetch is running), download the
   360p avc1 format (fallback: lowest format ≥ 240p) with `yt-dlp -N 8 --http-chunk-size 10M`.
2. Decode `scan.mp4` (optionally `-ss A -to B`) with
   `-vf fps=1,scale=64:36,format=gray -f rawvideo -` and read the frames in Python (stdlib).
3. Per frame, compare to the previous frame on a 16×9 grid of cells; a cell "changed" if its mean
   absolute difference exceeds a pixel threshold.
4. **Mask noisy cells:** cells that change in > 40 % of frames over the analysed range (webcam
   overlay, animated corners) are ignored.
5. Score each second = fraction of unmasked cells changed. A **change event** is a burst of
   consecutive seconds with score ≥ `--threshold` (default tuned on the test video during
   implementation); its timestamp is the first stable second after the burst (the settled
   screen), its strength is the summed score.
6. If `--max N` is exceeded, keep the N strongest events, then re-sort by time.
7. Build sheets from the scan copy (or HD seeks with `--hd`).

The scan copy stays in the cache until `cleanup` (or the 24 h sweep) so Claude can scan several
ranges without re-downloading.

Stdout additionally reports how many changes were found per chapter, so Claude can budget.

### 4.4 `frame <url> <t> [--height 1080]`

One full-resolution frame, path printed. For reading exact numbers, menus, code.

### 4.5 `cleanup [<url> | --all]`

Removes that video's folder, or the whole cache. Prints bytes freed.

### 4.6 Error handling and exit codes

| Situation | Behaviour | Exit |
|---|---|---|
| `yt-dlp`/`ffmpeg` missing | print install command | 2 |
| Bot check / "Sign in to confirm" | retry once with `--cookies-from-browser`, only if the user opted in via `$CLAUDETUBE_BROWSER` | n/a |
| Still blocked | print `BLOCKED` + reason, SKILL.md switches to Chrome fallback | 3 |
| No captions | write metadata + chapters, print `NO_CAPTIONS` | 4 |
| Stream URL expired / HTTP 403 on seek | refresh URL once, retry failed frames | n/a |
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

## 6. SKILL.md: the watching strategy

Trigger: any request to watch, summarize, learn from, or follow a YouTube video.

1. **Always transcript first.** `info` (with `--prefetch` if the goal is visual). For long
   videos, read chapter by chapter as needed.
2. **Decide the frame budget for this video and this goal** (the core judgement):
   - *None*: podcasts, interviews, talks, talking heads, or when the question is answerable
     from speech.
   - *Targeted*: slides/diagrams referenced in speech ("as you can see here"); grab those
     timestamps.
   - *Dense*: tutorials the user wants to reproduce (software, crafts, code on screen):
     `--scenes` over the relevant chapters (sheets from the local scan copy), plus
     `frame --height 1080` wherever an exact value, shortcut or setting must be read and the
     transcript doesn't state it.
   - *Uniform*: visual content without speech cues (montages, gameplay): `--every`.
3. Batch: one `frames` call per chapter/range, never one call per frame.
4. For "follow this tutorial": produce a numbered step list (action, exact values, expected
   result + timestamp) before acting; re-check frames only when a result doesn't match.
5. Always `cleanup` when done.
6. If exit code 3: switch to the Chrome fallback (§5).

## 7. Testing

- `pytest`, offline: json3 parsing and rolling-caption de-duplication (fixture trimmed from the
  test video), paragraph merging, chapter assignment, time parsing/formatting, grid layout and
  legend, scene detection on synthetic gray frames (noisy-cell masking, burst → settled
  timestamp, `--max` selection), cache TTL sweep.
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
