// ClaudeTube Chrome fallback: run on a youtube.com/watch page (Claude in Chrome → javascript_tool).
// Returns a compact text block: title, duration, chapters, and "[mm:ss] text" transcript lines.
// The full result is also kept in window.__claudetube.text; long transcripts are returned in
// pages; fetch the next one with: window.__claudetube.page(N)
(async () => {
  const PAGE = 40000;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const fmt = (s) => {
    s = Math.floor(s);
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    const p = (n) => String(n).padStart(2, "0");
    return h ? `${h}:${p(m)}:${p(x)}` : `${p(m)}:${p(x)}`;
  };
  const toSec = (t) => t.trim().split(":").reduce((a, b) => a * 60 + Number(b), 0);
  const tsRe = /^\d{1,2}(:\d{2}){1,2}$/;

  const player = document.querySelector("#movie_player");
  const resp = (player && player.getPlayerResponse && player.getPlayerResponse()) || window.ytInitialPlayerResponse || {};
  const vd = resp.videoDetails || {};

  // Chapters: from the page data (only if it belongs to this video), else the rendered markers.
  const chapters = [];
  const seen = new Set();
  const init = window.ytInitialData;
  if (init && init.currentVideoEndpoint?.watchEndpoint?.videoId === vd.videoId) {
    const re = /"chapterRenderer":\{"title":\{"simpleText":"((?:[^"\\]|\\.)*)"\},"timeRangeStartMillis":(\d+)/g;
    for (const m of JSON.stringify(init).matchAll(re)) {
      const time = fmt(+m[2] / 1000);
      if (!seen.has(time)) { seen.add(time); chapters.push(`[${time}] ${JSON.parse(`"${m[1]}"`)}`); }
    }
  }
  if (!chapters.length) for (const el of document.querySelectorAll("ytd-macro-markers-list-item-renderer")) {
    const title = el.querySelector("h4")?.textContent?.trim();
    const time = el.querySelector("#time")?.textContent?.trim();
    if (title && time && tsRe.test(time) && !seen.has(time)) {
      seen.add(time);
      chapters.push(`[${time}] ${title}`);
    }
  }

  // Merge word/line fragments into ~25 s paragraphs.
  const merge = (frags) => {
    const out = [];
    let cur = [], start = null;
    for (const [t, text] of frags) {
      if (cur.length && t - start >= 35) { out.push([start, cur.join(" ")]); cur = []; }
      if (!cur.length) start = t;
      cur.push(text);
      if (t - start >= 20 && /[.?!…]$/.test(text)) { out.push([start, cur.join(" ")]); cur = []; }
    }
    if (cur.length) out.push([start, cur.join(" ")]);
    return out.map(([t, x]) => `[${fmt(t)}] ${x}`);
  };

  let lines = [], source = "";

  // 1) Caption track fetched with the user's own session.
  const tracks = resp.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
  const track =
    tracks.find((t) => t.kind !== "asr" && t.languageCode?.startsWith("en")) ||
    tracks.find((t) => t.kind === "asr") || tracks[0];
  if (track) {
    try {
      const r = await fetch(track.baseUrl + "&fmt=json3", { credentials: "include" });
      const txt = await r.text();
      if (txt) {
        const frags = [];
        for (const ev of JSON.parse(txt).events || []) {
          for (const s of ev.segs || []) {
            const w = (s.utf8 || "").replace(/\s+/g, " ").trim();
            if (w) frags.push([((ev.tStartMs || 0) + (s.tOffsetMs || 0)) / 1000, w]);
          }
        }
        frags.sort((a, b) => a[0] - b[0]);
        lines = merge(frags);
        source = `caption track (${track.languageCode}${track.kind === "asr" ? ", auto" : ""})`;
      }
    } catch (e) { /* fall through to the transcript panel */ }
  }

  // 2) Transcript panel in the page ("In this video" → Transcript, or legacy "Show transcript").
  if (!lines.length) {
    const clickText = (re) => {
      const el = [...document.querySelectorAll("button, tp-yt-paper-button, yt-button-shape button, [role=tab]")]
        .find((b) => re.test((b.innerText || b.getAttribute("aria-label") || "").trim()));
      if (el) el.click();
      return !!el;
    };
    document.querySelector("tp-yt-paper-button#expand, #description-inline-expander #expand")?.click();
    await sleep(300);
    clickText(/^show transcript$/i) || clickText(/^transcript$/i);
    const segSel = "ytd-transcript-segment-renderer, transcript-segment-view-model";
    for (let i = 0; i < 40 && !document.querySelector(segSel); i++) await sleep(250);
    // Generic scrape: each segment has a timestamp-looking node and text.
    const frags = [];
    for (const seg of document.querySelectorAll(segSel)) {
      const parts = seg.innerText.split("\n").map((s) => s.trim()).filter(Boolean);
      const ti = parts.findIndex((p) => tsRe.test(p));
      if (ti < 0) continue;
      const text = parts.filter((_, i) => i !== ti && !/^\d+ (seconds?|minutes?|hours?)/.test(parts[i])).join(" ");
      if (text) frags.push([toSec(parts[ti]), text]);
    }
    if (frags.length) {
      lines = merge(frags);
      source = "transcript panel";
    }
  }

  const head = [
    `# ${vd.title || document.title}`,
    `duration ${fmt(+vd.lengthSeconds || document.querySelector("video")?.duration || 0)} · ${location.href}`,
    chapters.length ? "\n## Chapters\n" + chapters.join("\n") : "",
    `\n## Transcript (${source || "NONE FOUND"})`,
  ].join("\n");
  const text = head + "\n" + lines.join("\n");
  const pages = Math.max(1, Math.ceil(text.length / PAGE));
  window.__claudetube = { text, pages, page: (n) => text.slice(n * PAGE, (n + 1) * PAGE) };
  return pages === 1 ? text : `${text.slice(0, PAGE)}\n\n[page 1/${pages}, next: window.__claudetube.page(1)]`;
})();
