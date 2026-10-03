# Benchmark: follow the Blender donut tutorial

Reference: Claude following the Blender Guru donut tutorial took **35 minutes**
(https://x.com/ronedgecomb/status/2102774358095561139).

## Setup

- Claude Code with the ClaudeTube plugin installed (`/plugin install claudetube@claudetube`)
- Blender running with the Blender MCP server connected
- Model: Opus 5.5, effort **medium**, then repeat at **high**
- Fresh session, empty cache (`claudetube.py cleanup --all`)

## Prompt (use verbatim)

> Watch https://www.youtube.com/watch?v=z-Xl9tGqH14 and follow all 8 parts of the tutorial in
> Blender: model the donut, icing, mug and plate, unwrap and texture everything, scatter the
> sprinkles, light the scene, and finish with a rendered image like the one at the end of the
> video. Use the watch-youtube skill.

This matches the reference run: Opus 5.5 working through all 8 parts of the 2026 single-video
version (4h19m) and ending with a rendered donut.

## Record

| Run | Model / effort | Parts | Watch time (until step list written) | Total time | Frames viewed | Tokens | Result screenshot |
|---|---|---|---|---|---|---|---|
| reference | Opus 5.5 / ? | 1–8 | — | ~35 min | — | — | (in the post) |
| 1 | Opus 5.5 / medium | | | | | | |
| 2 | Opus 5.5 / high | | | | | | |

"Frames viewed" is the sum of frames across all sheets and single frames Claude read; count them
from the `N frames -> …` lines in the transcript.
