# ClaudeTube

**Let Claude watch YouTube fast.** Transcript and chapters first, then exactly the frames the
goal needs (none, a few, or hundreds), packed into contact sheets so Claude reads 9 frames per
image.

Built-in agent browsers often get stopped by YouTube's bot checks, and screenshotting a video
in a browser costs one round-trip per frame. ClaudeTube does the work locally with `yt-dlp` and
`ffmpeg` instead. Nothing is downloaded in full except, when scanning, a throwaway low-res copy
that is deleted afterwards.

## Install (Claude Code plugin)

```
/plugin marketplace add moazessam376-dev/claudetube
/plugin install claudetubeskim@claudetube
```

Requirements: Python 3.9+, plus `yt-dlp` and `ffmpeg` on your PATH:

```
brew install yt-dlp ffmpeg        # macOS
pipx install yt-dlp && sudo apt install ffmpeg   # Linux
winget install yt-dlp.yt-dlp Gyan.FFmpeg          # Windows
```

Then just ask: *"watch https://youtu.be/… and follow the tutorial in Blender"*. The
`watch-youtube` skill takes it from there.

## What runs on your machine

The skill has Claude run local commands: `python …/claudetube.py`, which calls `yt-dlp` and
`ffmpeg`. It starts a background download of a low-res copy of the video when scanning, and writes
only to its cache folder (`~/.cache/claudetube/`, deleted after 24 h). It makes no network requests
except to YouTube, and collects nothing. See [PRIVACY.md](PRIVACY.md).

## What it does

| Command | What you get |
|---|---|
| `claudetube.py info URL [--prefetch]` | Title, chapters, and a compact `[mm:ss]` transcript merged into ~25 s paragraphs, split by chapter (`--chapter N`, long chapters page with `--part K`). Lists likely sponsor/donation segments. |
| `claudetube.py find URL TERM … [--regex]` | Transcript lines mentioning a word or number, with timestamps and chapter. |
| `claudetube.py frames URL 1:25 4:10 …` | Frames at those times, as 3x3 contact sheets plus a legend mapping each tile to its timestamp. |
| `claudetube.py frames URL --range A-B --every S` | Uniform sampling. |
| `claudetube.py frames URL --scenes [--range A-B] [--max N]` | One frame per *settled* on-screen change, with webcam overlays and cursor jitter ignored, spread across the range. Skips likely promo segments (`--keep-promos` to include). Reports change counts per chapter. |
| `claudetube.py frame URL T` | One full 1080p frame for reading exact values. |
| `claudetube.py cleanup URL` / `--all` | Deletes cached data. Anything older than 24 h is swept automatically. |

Exit codes: `0` ok · `1` error · `2` missing yt-dlp/ffmpeg · `3` blocked by YouTube (the skill
switches to the Chrome-extension fallback) · `4` no captions.

## Measured speed

On a MacBook with a home connection, using Blender Guru's *Beginner Blender Tutorial (2026)*
(4h19m, 8 chapters):

| Step | Time |
|---|---|
| Transcript + chapters (`info`) | 9.9 s |
| 9 HD frames → 1 sheet (streamed seeks, no download) | 4.6 s |
| One 1080p frame | 2.4 s |
| Scan copy download (360p AV1, 209 MB, runs in the background during `info --prefetch`) | ~2 min |
| Scene detection on one 31-min chapter + 90 frames → 10 sheets | 9.1 s |
| 121 frames every 5 s over 10 min → 14 sheets | 2.9 s |
| Scene detection over the whole 4h19m + 400 frames | 70 s |

On Windows 10 (Intel i5-3570, 2012) with the same video: `info` 7.3 s, 9 HD frames 3.6 s, one
1080p frame 2.4 s, 121 frames every 5 s 2.0 s, scan copy (360p H.264, 364 MB) 2 min, scene
detection on one chapter + 90 frames 13 s, whole video + 400 frames 86 s.

The transcript of the whole 4-hour video is ~68k tokens (~8k per chapter). A 3x3 sheet costs
about 1.8k image tokens, so ~200 tokens per frame.

## How it works

- **One yt-dlp call** gets metadata, chapters, the caption track (json3) and every stream URL.
  The 5 MB caption file is compacted into paragraphs and deleted.
- **Few frames → HD streamed seeks.** `ffmpeg -ss T -i <stream-url>` fetches only the bytes
  around each timestamp, 16 in parallel.
- **Many frames → local scan copy.** Streaming continuously through ffmpeg is throttled by
  YouTube to about real time, but yt-dlp's parallel chunked download is not. So for dense work
  the smallest 360p stream is downloaded once, and frames come from it instantly. In a 3x3
  sheet each tile is shown ~520 px wide, so 360p loses almost nothing there. The copy is AV1 on
  macOS (smallest) and H.264 elsewhere, because software AV1 decoding was 3.5x slower on an older
  x86 CPU (override with `CLAUDETUBE_SCAN_CODEC=av01|avc1|vp09`).
- **Scene detection** decodes the scan copy at 1 fps to 32x18 grayscale. It masks screen
  regions that change in more than 40 % of frames (the presenter's webcam), and emits one event
  per burst of change, timed at the first settled frame after it.
- **Storage.** Everything lives in `~/.cache/claudetube/<video-id>/` (override with
  `CLAUDETUBE_CACHE`) and is removed by `cleanup` or after 24 h.
- **Bot checks.** If YouTube blocks yt-dlp, the skill switches to the Chrome fallback below. It
  never reads your browser cookies unless you opt in by setting `CLAUDETUBE_BROWSER` (for example
  `chrome`); then it retries once with that browser's YouTube cookies. On macOS that may show a
  Keychain prompt.

## Chrome fallback

If YouTube still blocks yt-dlp, the skill uses your real Chrome through the
[Claude in Chrome](https://claude.ai/chrome) extension. `scripts/transcript.js` reads the title,
chapters and full transcript from the page's Transcript panel in one call (~6 s for a 4-hour
video). `scripts/frames.js` gets frames: Chrome does not load video in a background tab, so it
plays the video in a small popup window and draws frames from it into a 3x3 contact sheet over
the agent's tab, so one screenshot holds 9 frames from the 1080p stream (~6 s per sheet), or one
full-size frame for reading exact values. *Status: verified live on 2026-10-03 (Windows, Chrome).*

## Develop

```
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/pytest                              # offline unit tests
CLAUDETUBE_LIVE=1 .venv/bin/pytest tests/test_live.py   # hits YouTube
```

Design spec: [`docs/superpowers/specs/2026-10-03-claudetube-design.md`](docs/superpowers/specs/2026-10-03-claudetube-design.md)

## License

MIT
