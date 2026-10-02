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


def limit(events, max_n: int) -> "list[Event]":
    """Keep the max_n strongest events, in time order."""
    if len(events) <= max_n:
        return list(events)
    strongest = sorted(events, key=lambda e: e.strength, reverse=True)[:max_n]
    return sorted(strongest, key=lambda e: e.t)
