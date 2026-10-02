"""The one place external programs are run (so tests can stub it)."""
import shutil
import subprocess


class MissingDep(Exception):
    pass


INSTALL_HINT = "install with: brew install yt-dlp ffmpeg   (or: pipx install yt-dlp; apt install ffmpeg)"


def need(*bins):
    for b in bins:
        if not shutil.which(b):
            raise MissingDep(f"{b} not found on PATH — {INSTALL_HINT}")


def run(args, timeout=None) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)


def run_bytes(args, timeout=None) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
