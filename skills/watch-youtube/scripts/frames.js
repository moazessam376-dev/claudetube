// ClaudeTube Chrome fallback, frames: run on the youtube.com/watch tab (Claude in Chrome → javascript_tool).
// A tab the agent drives is usually a background tab, and Chrome never loads video in a hidden tab.
// So this adds a button that opens the video in a small popup window (a real window, so it is visible
// and plays), then draws frames from the popup's <video> into a contact sheet shown over this tab,
// where one screenshot captures up to 9 frames.
//
//   1. run this file                      → returns where to click
//   2. click that point (computer left_click)  → popup opens
//   3. await window.__ctubeFrames.sheet([1700, 1800, ...])   (seconds, up to rows*cols per call)
//      then take a screenshot of this tab
//   4. window.__ctubeFrames.close()       → closes the popup and removes the overlay
(() => {
  const vid = new URL(location.href).searchParams.get("v");
  const fmt = (s) => {
    s = Math.floor(s);
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    const p = (n) => String(n).padStart(2, "0");
    return h ? `${h}:${p(m)}:${p(x)}` : `${m}:${p(x)}`;
  };
  const api = (window.__ctubeFrames = window.__ctubeFrames || {});

  api.ready = () => {
    const w = api.win;
    if (!w || w.closed) return false;
    try {
      const v = w.document.querySelector("video");
      return !!(v && v.readyState >= 2 && w.document.querySelector("#movie_player")?.seekTo);
    } catch (e) {
      return false;
    }
  };

  // times: seconds; grid: "3x3" (sheet) or "1x1" (one full-resolution frame for reading exact values)
  api.sheet = async (times, grid = "3x3") => {
    if (!api.ready()) return "popup not ready: click the 'ClaudeTube: open player' button first (or wait a second and retry)";
    const [cols, rows] = grid.split("x").map(Number);
    const w = api.win, d = w.document, v = d.querySelector("video"), p = d.querySelector("#movie_player");
    const wait = (ms) => new Promise((r) => w.setTimeout(r, ms)); // the popup's timers: this tab's are throttled
    const seek = (T) => Promise.race([
      new Promise((r) => {
        const f = () => {
          if (v.readyState >= 2 && !v.seeking && Math.abs(v.currentTime - T) < 1.5) { v.removeEventListener("seeked", f); r(true); }
        };
        v.addEventListener("seeked", f);
        p.seekTo(T, true);
      }),
      wait(8000).then(() => false),
    ]);
    p.mute();
    p.pauseVideo();
    const one = cols * rows === 1;
    const W = one ? v.videoWidth : 640, H = one ? v.videoHeight : 360;
    const c = document.createElement("canvas");
    c.width = W * cols;
    c.height = H * rows;
    const g = c.getContext("2d");
    g.fillStyle = "#000";
    g.fillRect(0, 0, c.width, c.height);
    const legend = [];
    for (const [i, T] of times.slice(0, cols * rows).entries()) {
      const ok = await seek(T);
      await wait(150);
      const x = (i % cols) * W, y = Math.floor(i / cols) * H;
      g.drawImage(v, x, y, W, H);
      g.fillStyle = "rgba(0,0,0,.7)";
      g.fillRect(x, y, 150, 34);
      g.fillStyle = "#ff0";
      g.font = "bold 26px sans-serif";
      g.fillText(fmt(T), x + 8, y + 26);
      legend.push(`${i + 1}: ${fmt(T)}${ok ? "" : " (seek timed out)"}`);
    }
    p.pauseVideo();
    document.getElementById("ctube-sheet")?.remove();
    const img = new Image();
    img.id = "ctube-sheet";
    img.src = c.toDataURL("image/jpeg", 0.9);
    Object.assign(img.style, {
      position: "fixed", inset: "0", width: "100vw", height: "100vh",
      objectFit: "contain", background: "#000", zIndex: 2147483647,
    });
    document.body.appendChild(img);
    await new Promise((r) => (img.complete ? r() : (img.onload = r)));
    return `sheet ready (${grid}, ${v.videoWidth}x${v.videoHeight} source), take a screenshot now. ${legend.join(" · ")}`;
  };

  api.close = () => {
    document.getElementById("ctube-sheet")?.remove();
    document.getElementById("ctube-open")?.remove();
    if (api.win && !api.win.closed) api.win.close();
    return "closed";
  };

  if (api.ready()) return "popup already open: call window.__ctubeFrames.sheet([...seconds])";
  document.getElementById("ctube-open")?.remove();
  const b = document.createElement("button");
  b.id = "ctube-open";
  b.textContent = "ClaudeTube: open player";
  Object.assign(b.style, {
    position: "fixed", left: "0", top: "0", width: "300px", height: "80px",
    zIndex: 2147483647, fontSize: "20px",
  });
  b.onclick = () => {
    api.win = window.open(`${location.origin}/watch?v=${vid}`, "ctube", "popup,width=960,height=600");
    b.remove();
  };
  document.body.appendChild(b);
  return "click (150, 40) in this tab (computer left_click) to open the player popup, then call window.__ctubeFrames.sheet([...seconds])";
})();
