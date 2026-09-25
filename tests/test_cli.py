"""`python -m scheherazades_hoard` as the launchers and Faustus start it."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
PORT = 18865


def _parent_pid(pid: int) -> int | None:
    """Parent of `pid` on Windows (Toolhelp32 snapshot), None elsewhere or if not found."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    try:
        ok = kernel32.Process32First(snap, ctypes.byref(entry))
        while ok:
            if entry.th32ProcessID == pid:
                return int(entry.th32ParentProcessID)
            ok = kernel32.Process32Next(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return None


def test_demo_start_serves_health_writes_pid_and_logs(tmp_path):
    data = tmp_path / "data"
    proc = subprocess.Popen(
        [sys.executable, "-m", "scheherazades_hoard", "--demo", "--no-browser",
         "--port", str(PORT), "--data-dir", str(data)],
        cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        body = None
        for _ in range(100):
            try:
                body = httpx.get(f"http://127.0.0.1:{PORT}/api/health", timeout=0.5, trust_env=False).json()
                break
            except httpx.HTTPError:
                time.sleep(0.1)
        assert body and body["service"] == "scheherazades-hoard" and body["worlds"] == 1
        # the pid of the process that holds the port, for scripts/stop.ps1
        written = int((data / "scheherazade.pid").read_text(encoding="ascii").strip())
        # A Windows venv's python.exe is a launcher that runs the real interpreter as its
        # child: the file then holds the child, which is the one that owns the port.
        assert written == proc.pid or _parent_pid(written) == proc.pid, (written, proc.pid)
        assert (data / "logs" / "app.log").is_file()
        worlds = httpx.post(f"http://127.0.0.1:{PORT}/api/agent/story_worlds", json={}, trust_env=False).json()
        assert worlds[0]["name"] == "El Archipiélago de Sal"
    finally:
        proc.terminate()
        proc.wait(timeout=15)
    if os.name != "nt":  # TerminateProcess on Windows skips the cleanup
        assert not (data / "scheherazade.pid").exists()
