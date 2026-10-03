# Benchmark: follow the Blender donut tutorial

Reference: Claude following the Blender Guru donut tutorial took **35 minutes**
(https://x.com/ronedgecomb/status/2102774358095561139).

## Setup

- Claude Code with the ClaudeTube plugin installed (`/plugin install claudetube@claudetube`)
- Blender running with the Blender MCP server connected
- Model: Opus 5.5, effort **medium**, then repeat at **high**
- Fresh session, empty cache (`claudetube.py cleanup --all`)

## Prompt (use verbatim)

> Watch https://www.youtube.com/watch?v=z-Xl9tGqH14 and follow Part 1 and Part 2 of the tutorial
> in Blender until you have the same donut as the video at the end of Part 2. Use the
> watch-youtube skill.

Change the parts to match whatever the reference run covered, and record which parts you used.

## Record

| Run | Model / effort | Parts | Watch time (until step list written) | Total time | Frames viewed | Tokens | Result screenshot |
|---|---|---|---|---|---|---|---|
| reference | ? | ? | — | 35 min | — | — | — |
| 1 | Opus 5.5 / medium | | | | | | |
| 2 | Opus 5.5 / high | | | | | | |

"Frames viewed" is the sum of frames across all sheets and single frames Claude read; count them
from the `N frames -> …` lines in the transcript.
