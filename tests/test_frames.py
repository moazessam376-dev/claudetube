import shutil

import pytest

from ctube import frames


def test_layout():
    sheets = frames.layout(list(range(20)), 3, 3)
    assert [len(s) for s in sheets] == [9, 9, 2]
    assert sheets[2] == [18, 19]


def test_legend_rows():
    out = frames.legend("s.jpg", [5, 65, 3725, 10], 3, failed={10})
    assert out.splitlines() == ["s.jpg", "     00:05     01:05   1:02:05", "    00:10!"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_build_partial_sheet(tmp_path):
    import subprocess
    imgs = []
    for i, c in enumerate(["red", "green"]):
        p = tmp_path / f"{i}.jpg"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", f"color={c}:s=1280x720",
                        "-frames:v", "1", str(p)], check=True)
        imgs.append(p)
    out = frames.build_sheet(imgs + [None], 2, 2, 320, tmp_path / "sheet.jpg")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                            str(out)], capture_output=True, text=True).stdout.strip()
    assert probe == f"{2 * 320 + 4 + 4},{2 * 180 + 4 + 4}"
