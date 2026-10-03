# Privacy policy: ClaudeTube Skim

ClaudeTube Skim runs entirely on your own computer. The author does not operate any server and
does not collect, receive or store any data about you or your use of the plugin.

## What the plugin does on your machine

- It runs `yt-dlp` and `ffmpeg` locally to fetch the YouTube video you ask about (metadata,
  captions, a low-resolution copy of the video, and individual frames). These requests go directly
  from your computer to YouTube, as when you watch a video yourself.
- It never reads your browser cookies by default. Only if you set `CLAUDETUBE_BROWSER` yourself
  (for example `chrome`) and YouTube blocks a request, `yt-dlp` reads that browser's YouTube
  cookies locally and retries once. They are sent only to YouTube.
- Everything it downloads is stored in `~/.cache/claudetube/` (or `CLAUDETUBE_CACHE`). It is
  deleted by `claudetube.py cleanup` and automatically after 24 hours.
- Transcripts and frames it produces are read by Claude in your session, under your Claude
  account's own terms and privacy settings.

## Contact

Questions: https://github.com/moazessam376-dev/claudetube/issues
