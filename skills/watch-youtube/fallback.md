# Chrome fallback (exit code 3: YouTube blocked yt-dlp)

Uses the user's real Chrome through the Claude in Chrome extension, where they are signed in.

1. Open the video's watch page in a new tab.
2. Transcript: run the contents of `scripts/transcript.js` with `javascript_tool`. It returns the
   title, chapters and a compact `[mm:ss] text` transcript (from the caption track, else by
   opening the page's Transcript panel). Long transcripts come in pages: run
   `window.__claudetube.page(1)`, `page(2)`, … as it tells you.
3. Frames: the agent's tab is a background tab, and Chrome never loads video in a hidden tab, so
   seeking its own `<video>` hangs. `scripts/frames.js` plays the video in a small popup window
   instead and draws frames from it into a contact sheet shown over your tab:
   1. Run the contents of `scripts/frames.js` with `javascript_tool`.
   2. `computer` → `left_click` at (150, 40) on the "ClaudeTube: open player" button. Wait ~3 s.
      (A click right after page load can miss; if the next step says "not ready", click again.)
   3. `await window.__ctubeFrames.sheet([1700, 1800, 1900, …])` (seconds, up to 9) → screenshot.
      ~6 s per 9-frame sheet, drawn from the 1080p stream.
   4. Exact values: `await window.__ctubeFrames.sheet([1980], "1x1")` → one full-size frame → screenshot.
   5. When done: `window.__ctubeFrames.close()`.

   Each sheet is a round-trip, so keep the frame budget to **targeted** or a few sheets per
   chapter.
