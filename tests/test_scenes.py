from ctube.scenes import Event, detect, limit, split_raw

W, H = 32, 18
N = W * H


def frame(v=0, patch=None):
    """A flat frame of value v, optionally with a bottom-right 6x4 patch of value patch."""
    px = bytearray([v]) * N
    if patch is not None:
        for y in range(H - 4, H):
            for x in range(W - 6, W):
                px[y * W + x] = patch
    return bytes(px)


def test_static_video_has_no_events():
    assert detect([frame(50)] * 30, W, H) == []


def test_constant_webcam_motion_is_masked():
    frames = [frame(50, patch=(i * 40) % 250) for i in range(60)]
    assert detect(frames, W, H) == []


def test_single_switch_gives_settled_timestamp():
    frames = [frame(50)] * 10 + [frame(200)] * 20
    ev = detect(frames, W, H, start=100.0)
    assert [e.t for e in ev] == [111.0]


def test_burst_reports_first_stable_frame():
    frames = [frame(50)] * 10 + [frame(100), frame(150), frame(200)] + [frame(200)] * 10
    assert [e.t for e in detect(frames, W, H)] == [13.0]


def test_burst_at_end_reports_last_frame():
    frames = [frame(50)] * 10 + [frame(60 + 20 * i) for i in range(5)]
    assert [e.t for e in detect(frames, W, H)] == [14.0]


def test_long_burst_is_split():
    frames = [frame(0)] * 5 + [frame(i % 2 * 200) for i in range(40)] + [frame(0)] * 5
    ev = detect(frames, W, H, max_burst=15)
    assert len(ev) == 3


def test_webcam_plus_real_switch():
    frames = [frame(50, patch=(i * 40) % 250) for i in range(20)] + [frame(200, patch=(i * 40) % 250) for i in range(20)]
    assert [e.t for e in detect(frames, W, H)] == [21.0]


def test_limit_keeps_strongest_sorted_by_time():
    ev = [Event(1, 0.5), Event(2, 3.0), Event(3, 1.0), Event(4, 2.0)]
    assert limit(ev, 2) == [Event(2, 3.0), Event(4, 2.0)]
    assert limit(ev, 10) == ev


def test_split_raw_drops_partial_frame():
    assert split_raw(b"\0" * (N * 2 + 5), W, H) == [b"\0" * N] * 2
