"""Parsing and formatting of video timestamps."""


def parse_time(s: str) -> float:
    """Parse SS, SS.s, MM:SS or HH:MM:SS into seconds."""
    parts = s.strip().split(":")
    if not s.strip() or len(parts) > 3:
        raise ValueError(f"bad time: {s!r}")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        raise ValueError(f"bad time: {s!r}") from None
    if any(n < 0 for n in nums) or any(n >= 60 for n in nums[1:]):
        raise ValueError(f"bad time: {s!r}")
    total = 0.0
    for n in nums:
        total = total * 60 + n
    return total


def fmt_time(sec: float) -> str:
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def parse_range(s: str) -> "tuple[float, float]":
    """Parse 'A-B' into (start, end) seconds."""
    if "-" not in s:
        raise ValueError(f"bad range (want A-B): {s!r}")
    a, b = s.split("-", 1)
    start, end = parse_time(a), parse_time(b)
    if end <= start:
        raise ValueError(f"range end must be after start: {s!r}")
    return start, end
