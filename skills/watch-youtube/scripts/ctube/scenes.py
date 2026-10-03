"""Scene-change detection on tiny grayscale frames, robust to webcam overlays.

Frames come from ffmpeg as raw 8-bit gray (e.g. 32x18, one per second). Each pixel of
such a frame is the area-average of a screen region, so "pixel changed" means "that region
of the screen changed". Regions that change in most frames (a presenter's webcam, an
animated corner) are masked out; what's left is real on-screen state change.
"""
from collections import namedtuple

Event = namedtuple("Event", "t strength")


def split_raw(data: bytes, w: int, h: int) -> "list[bytes]":
    n = w * h
    return [data[i:i + n] for i in range(0, len(data) - n + 1, n)]


def detect(frames, w, h, start=0.0, fps=1.0, pix_thresh=8, noisy_frac=0.4,
           threshold=0.03, settle=2, max_burst=15) -> "list[Event]":
    """Return one Event per burst of screen change, timed at the settled screen after it.

    threshold:  fraction of unmasked regions that must change for a second to count as change
    settle:     quiet seconds needed to close a burst
    max_burst:  a burst longer than this many changed frames is split (long continuous edits)
    """
    n = w * h
    changed = [
        [abs(a - b) > pix_thresh for a, b in zip(prev, cur)]
        for prev, cur in zip(frames, frames[1:])
    ]
    if not changed:
        return []
    freq = [sum(c[k] for c in changed) / len(changed) for k in range(n)]
    keep = [k for k in range(n) if freq[k] <= noisy_frac]
    if len(keep) < n / 2:  # most of the screen is "noisy": that's the content, not an overlay
        keep = list(range(n))
    scores = [sum(c[k] for k in keep) / len(keep) for c in changed]

    def t_of(frame_idx):
        return start + frame_idx / fps

    events, strength, length, quiet, last = [], 0.0, 0, 0, None
    for i, s in enumerate(scores):
        k = i + 1  # scores[i] is the change from frame i to frame k
        if s >= threshold:
            strength += s
            length += 1
            quiet = 0
            last = k
            if length >= max_burst:
                events.append(Event(t_of(k), strength))
                strength, length = 0.0, 0
        elif last is not None and length:
            quiet += 1
            if quiet >= settle:
                events.append(Event(t_of(last + 1), strength))
                strength, length, quiet = 0.0, 0, 0
    if length:
        events.append(Event(t_of(min(last + 1, len(frames) - 1)), strength))
    return events


def limit(events, max_n: int, start=None, end=None) -> "list[Event]":
    """Keep max_n events spread over the range, in time order.

    The range [start, end) is cut into max_n equal slices and the strongest event of each
    non-empty slice is kept, so quiet stretches still get frames. Slots left by empty slices go
    to the strongest remaining events anywhere.
    """
    if len(events) <= max_n:
        return list(events)
    if max_n <= 0:
        return []
    lo = events[0].t if start is None else start
    hi = events[-1].t + 1 if end is None else end
    width = max(hi - lo, 1e-9) / max_n
    best = {}
    for e in events:
        k = min(max(int((e.t - lo) / width), 0), max_n - 1)
        if k not in best or e.strength > best[k].strength:
            best[k] = e
    kept = set(best.values())
    rest = sorted((e for e in events if e not in kept), key=lambda e: e.strength, reverse=True)
    kept.update(rest[:max_n - len(kept)])
    return sorted(kept, key=lambda e: e.t)
