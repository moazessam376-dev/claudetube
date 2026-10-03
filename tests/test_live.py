"""Opt-in end-to-end test against real YouTube: CLAUDETUBE_LIVE=1 pytest tests/test_live.py"""
import os
import re

import pytest

import claudetube

pytestmark = pytest.mark.skipif(os.environ.get("CLAUDETUBE_LIVE") != "1", reason="set CLAUDETUBE_LIVE=1")
VID = "jNQXAC9IVRw"  # "Me at the zoo", 19 s


def test_end_to_end(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDETUBE_CACHE", str(tmp_path))
    assert claudetube.main(["info", VID]) == 0
    assert "elephants" in capsys.readouterr().out
    assert claudetube.main(["frames", VID, "0:02", "0:08", "0:15"]) == 0
    sheet = re.search(r"^(/\S+\.jpg)$", capsys.readouterr().out, re.M).group(1)
    assert os.path.getsize(sheet) > 10_000
    assert claudetube.main(["frames", VID, "--scenes"]) == 0
    assert "scene changes found" in capsys.readouterr().out
    assert claudetube.main(["cleanup", VID]) == 0
    assert not (tmp_path / VID).exists()
