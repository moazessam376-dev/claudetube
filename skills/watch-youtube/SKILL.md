---
name: watch-youtube
description: Watch a YouTube video fast: transcript and chapters first, then exactly the frames the goal needs, packed into contact sheets. Use when given a YouTube link, or asked to watch, summarize, learn from, or follow along with a YouTube video or tutorial.
---

# Watch YouTube

`CT` below means `python3 <this skill's base directory>/scripts/claudetube.py` (on Windows use
`python`; `python3` there may be the Microsoft Store stub). It needs `yt-dlp`
and `ffmpeg`; on exit code 2 relay its install command to the user.

Speed comes from three habits: **transcript first**, a deliberate **frame budget**, and
**batching** (one command per range, and every sheet of a batch read in one turn with parallel
Read calls).

## 1. Transcript first

```
CT info URL [--prefetch]
```

- Add `--prefetch` whenever the goal is visual (following a tutorial, UI, art, anything "show
  me"). It starts a background download of a low-res scan copy so later frames are instant.
- Short videos print in full. Long ones print the chapter list with token counts; read the
  chapters the goal needs with `CT info URL --chapter N` (several chapters → parallel calls).
  Long chapters print in parts; the output ends with the `--part K` command for the next one.
- It also lists likely sponsor, donation and self-promotion segments. `--scenes` and `--every`
  skip them automatically (`--keep-promos` to include them).
- Done when you know what happens when: you can name the timestamps where the screen matters.

## 2. Choose the frame budget

| Video + goal | Budget | Command |
|---|---|---|
| Talk, podcast, interview, explainer where speech carries it | **none** | no frames |
| Speech points at visuals ("as you can see", slides, a diagram, a result) | **targeted** | `CT frames URL 4:10 7:35 …` |
| Tutorial to reproduce (software, code, craft) | **dense** | `CT frames URL --scenes --range A-B --max N` per chapter |
| Visual content without speech cues (montage, gameplay, demo reel) | **uniform** | `CT frames URL --range A-B --every S` |

- `--scenes` returns one frame per settled on-screen change (webcam overlays and cursor motion
  are ignored) and reports how many changes each chapter has. Start with `--max 30`–`60` per
  chapter; raise it where the transcript is vague and the screen is busy. Frames are spread
  over the whole range, so quiet stretches still get covered.
- Sheets are 3x3 by default (~200 tokens per frame). They show shapes, layouts, menus and
  on-screen shortcut overlays well; small text such as numeric fields needs step 3.
- Done when every timestamp you named in step 1 is covered by a sheet you have read.

## 3. Read exact values

```
CT find URL "roughness" "0.12"            # transcript lines that mention it, with timestamps
CT find URL '\d+\.\d+' --regex            # every decimal number said in the video
CT frame URL 33:00                        # one 1080p frame
CT frames URL 33:00 33:05 --grid 2x2      # 2x2 sheet from the HD stream
```

Use this wherever an exact number, setting, shortcut or line of code must be copied. Search the
transcript first to find where it is mentioned, then grab HD frames at those timestamps if the
transcript does not say the value. Done when every value you will act on came from the transcript
or an HD frame.

## 4. Follow along (tutorials)

Before acting, write a numbered step list: action, exact values, expected result, timestamp.
Work chapter by chapter: watch chapter N (steps 1–3), do it, then move on, so the scan copy and
your context stay focused. When a result does not match, re-check frames around that step's
timestamp before improvising.

## 5. Clean up

```
CT cleanup URL
```

Run it when the task is done. (Data older than 24 h is also deleted automatically.)

## Exit codes

`0` ok · `1` error (message on stderr) · `2` missing yt-dlp/ffmpeg · `3` **blocked by YouTube**
→ follow [fallback.md](fallback.md) · `4` no captions → the video has no transcript; rely on
`--scenes` / `--every` frames.
