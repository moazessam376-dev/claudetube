"""YouTube json3 captions -> compact, chaptered markdown transcript."""
import re

from .timefmt import fmt_time

_WS = re.compile(r"\s+")
_SENTENCE_END = (".", "?", "!", "…")


def parse_json3(data: dict) -> "list[tuple[float, str]]":
    """Return caption fragments as (seconds, text), in time order.

    Auto captions carry one word per seg (with tOffsetMs); manual captions carry whole
    lines per event, possibly with embedded newlines. Both become flat fragments.
    """
    frags = []
    for ev in data.get("events", []):
        start = ev.get("tStartMs", 0)
        for seg in ev.get("segs") or []:
            text = _WS.sub(" ", seg.get("utf8", "")).strip()
            if text:
                frags.append(((start + seg.get("tOffsetMs", 0)) / 1000, text))
    frags.sort(key=lambda f: f[0])
    return frags


def paragraphs(frags, min_len: float = 20.0, max_len: float = 35.0, breaks=()) -> "list[tuple[float, str]]":
    """Merge fragments into paragraphs that end on a sentence after min_len, or at max_len.

    A paragraph never spans a time in `breaks` (chapter starts).
    """
    paras, cur, cur_start = [], [], None
    for t, text in frags:
        if cur and (t - cur_start >= max_len or any(cur_start < b <= t for b in breaks)):
            paras.append((cur_start, " ".join(cur)))
            cur = []
        if not cur:
            cur_start = t
        cur.append(text)
        if t - cur_start >= min_len and text.endswith(_SENTENCE_END):
            paras.append((cur_start, " ".join(cur)))
            cur = []
    if cur:
        paras.append((cur_start, " ".join(cur)))
    return paras


def _date(d):
    return f"{d[:4]}-{d[4:6]}-{d[6:]}" if d and len(d) == 8 else (d or "")


def render(meta: dict, paras) -> str:
    chapters = meta.get("chapters") or []
    head = " · ".join(
        x for x in (meta.get("channel"), fmt_time(meta.get("duration") or 0), _date(meta.get("upload_date")),
                    meta.get("webpage_url")) if x
    )
    out = [f"# {meta.get('title', '')}", head, ""]
    if chapters:
        out.append("## Chapters")
        out += [f"{i}. [{fmt_time(c['start_time'])}] {c['title']}" for i, c in enumerate(chapters, 1)]
        out.append("")
    out.append("## Transcript")
    if not paras:
        out.append("(no captions available)")
    ci = -1
    for t, text in paras:
        while chapters and ci + 1 < len(chapters) and t >= chapters[ci + 1]["start_time"]:
            ci += 1
            c = chapters[ci]
            out += ["", f"### {ci + 1}. [{fmt_time(c['start_time'])}] {c['title']}"]
        out.append(f"[{fmt_time(t)}] {text}")
    return "\n".join(out) + "\n"


def chapter_section(md: str, n: int) -> str:
    """Return the '### n.' section of a rendered transcript."""
    m = re.search(rf"^### {n}\. .*?(?=^### |\Z)", md, re.M | re.S)
    if not m:
        raise KeyError(f"no chapter {n}")
    return m.group(0).rstrip() + "\n"


def estimate_tokens(s: str) -> int:
    return len(s) // 4


_PARA = re.compile(r"^\[(\d+(?::\d{2}){1,2})\] (.*)$")
_CHAPTER = re.compile(r"^### (\d+)\. ")


def _secs(stamp: str) -> float:
    s = 0.0
    for part in stamp.split(":"):
        s = s * 60 + int(part)
    return s


def parse_md(md: str) -> "list[tuple[float, str, int]]":
    """Paragraphs of a rendered transcript as (seconds, text, chapter number or 0)."""
    out, ch = [], 0
    for line in md.splitlines():
        m = _CHAPTER.match(line)
        if m:
            ch = int(m.group(1))
            continue
        m = _PARA.match(line)
        if m:
            out.append((_secs(m.group(1)), m.group(2), ch))
    return out


def split_parts(section: str, max_chars: int) -> "list[str]":
    """Split a chapter section into parts of at most ~max_chars, only at line boundaries."""
    parts, cur, size = [], [], 0
    for line in section.rstrip("\n").split("\n"):
        if cur and size + len(line) + 1 > max_chars:
            parts.append("\n".join(cur) + "\n")
            cur, size = [], 0
        cur.append(line)
        size += len(line) + 1
    if cur:
        parts.append("\n".join(cur) + "\n")
    return parts


def search(paras, terms, regex: bool = False, width: int = 90) -> "list[tuple[float, int, str]]":
    """Paragraphs matching any term (case-insensitive) as (seconds, chapter, snippet).

    The snippet keeps `width` characters on each side of every match, joined with '...'.
    """
    pats = [re.compile(t if regex else re.escape(t), re.I) for t in terms]
    hits = []
    for t, text, ch in paras:
        spans = sorted(m.span() for p in pats for m in p.finditer(text))
        if not spans:
            continue
        windows = []
        for a, b in spans:
            a, b = max(0, a - width), min(len(text), b + width)
            if windows and a <= windows[-1][1]:
                windows[-1] = (windows[-1][0], max(windows[-1][1], b))
            else:
                windows.append((a, b))
        snippet = " ... ".join(text[a:b].strip() for a, b in windows)
        if windows[0][0] > 0:
            snippet = "..." + snippet
        if windows[-1][1] < len(text):
            snippet += "..."
        hits.append((t, ch, snippet))
    return hits
