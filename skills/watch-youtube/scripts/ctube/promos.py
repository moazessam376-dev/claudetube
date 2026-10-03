"""Find likely sponsor, donation and self-promotion segments from the transcript alone.

Works offline (no SponsorBlock or other service). A segment is a run of nearby paragraphs that
mention promotion, containing at least one strong cue, so a single "link in the description"
inside a lesson does not count.
"""
import re

_STRONG = re.compile(
    r"sponsored by|this video is sponsored|for sponsoring|for supporting this video|today'?s sponsor"
    r"|use (?:my |the )?code (?-i:[A-Z0-9]{3,})\b|promo code|\d+ ?% off\b|percent off\b"
    r"|please (?:\w+ ){0,2}donat|make a donation|join the course|my (?:new )?course"
    r"|my (?:new )?academy|patreon|become a (?:patron|member)|check out my",
    re.I,
)
_WEAK = re.compile(
    r"sponsor|donat|(?<!of )\bcourses?\b|\bacademy\b|discount|\bfund"
    r"|link (?:\w+ ){0,3}(?:below|beneath|underneath|in the description)"
    r"|click (?:on )?(?:that|the link)|support (?:the|this|my) channel|\bmerch\b",
    re.I,
)
_PROMO_TITLE = re.compile(r"\b(sponsor\w*|ad|ads|advert\w*|promo\w*|patreon|donat\w*|merch)\b", re.I)

MIN_SCORE = 4  # total cue score a run needs to count as a segment
MAX_GAP = 1  # cue-less paragraphs allowed inside one run


def score(text: str) -> "tuple[int, int]":
    """(strong cue count, total score) for one paragraph."""
    strong = len(_STRONG.findall(text))
    return strong, 2 * strong + len(_WEAK.findall(text))


def find(paras, end_time: float, chapters=()) -> "list[tuple[float, float]]":
    """Likely promo segments as (start, end) seconds.

    paras: [(start_seconds, text)] in time order. A segment ends where the next paragraph starts
    (or at end_time). Chapters whose title names a sponsor/ad are segments too.
    """
    segs = []
    run, gap = [], 0
    for i, (_, text) in enumerate(paras):
        strong, sc = score(text)
        if sc:
            run.append((i, strong, sc))
            gap = 0
        elif run:
            gap += 1
            if gap > MAX_GAP:
                segs += _close(run, paras, end_time)
                run, gap = [], 0
    segs += _close(run, paras, end_time)
    for k, c in enumerate(chapters):
        if _PROMO_TITLE.search(c.get("title", "")):
            nxt = chapters[k + 1]["start_time"] if k + 1 < len(chapters) else end_time
            segs.append((float(c["start_time"]), float(nxt)))
    return _merge(segs)


def _close(run, paras, end_time):
    if not run or not any(s for _, s, _ in run) or sum(sc for *_, sc in run) < MIN_SCORE:
        return []
    first, last = run[0][0], run[-1][0]
    end = paras[last + 1][0] if last + 1 < len(paras) else end_time
    return [(float(paras[first][0]), float(end))]


def _merge(segs):
    out = []
    for s, e in sorted(segs):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def inside(t: float, segs) -> bool:
    return any(s <= t < e for s, e in segs)
