# Chrome fallback (exit code 3: YouTube blocked yt-dlp)

Uses the user's real Chrome through the Claude in Chrome extension, where they are signed in.

1. Open the video's watch page in a new tab.
2. Transcript: run the contents of `scripts/transcript.js` with `javascript_tool`. It returns the
   title, chapters and a compact `[mm:ss] text` transcript (from the caption track, else by
   opening the page's Transcript panel). Long transcripts come in pages: run
   `window.__claudetube.page(1)`, `page(2)`, … as it tells you.
3. Frames: for each timestamp, run
   `(v => new Promise(r => { v.pause(); v.addEventListener('seeked', r, {once: true}); v.currentTime = T; }))(document.querySelector('video'))`
   and then take a screenshot. Each frame is a round-trip, so keep the frame budget to
   **targeted**: only the timestamps the transcript points at.
