"""The one place external programs are run (so tests can stub it)."""
import os
import shutil
import subprocess
import sys

WINDOWS = sys.platform == "win32"


class MissingDep(Exception):
    pass


if WINDOWS:
    INSTALL_HINT = "install with: winget install yt-dlp.yt-dlp Gyan.FFmpeg   (or: scoop install yt-dlp ffmpeg)"
else:
    INSTALL_HINT = "install with: brew install yt-dlp ffmpeg   (or: pipx install yt-dlp; apt install ffmpeg)"


def need(*bins):
    for b in bins:
        if not shutil.which(b):
            raise MissingDep(f"{b} not found on PATH — {INSTALL_HINT}")


def run(args, timeout=None) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, stdin=subprocess.DEVNULL)


def run_bytes(args, timeout=None) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)


def alive(pid) -> bool:
    """Is process `pid` running? (On Windows os.kill(pid, 0) would terminate it.)"""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if WINDOWS:
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def spawn_detached(args, log):
    """Start a background process that outlives this one."""
    kw = dict(stdout=log, stderr=log, stdin=subprocess.DEVNULL)
    if not WINDOWS:
        return subprocess.Popen(args, start_new_session=True, **kw)
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:  # escape the caller's job object so the download survives the shell exiting
        return subprocess.Popen(args, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kw)
    except OSError:
        return subprocess.Popen(args, creationflags=flags, **kw)


def kill_tree(pid):
    """Stop `pid` and its children (the yt-dlp it started)."""
    if WINDOWS:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
    else:
        import signal
        os.killpg(pid, signal.SIGTERM)
