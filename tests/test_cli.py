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
        assert (data / "scheherazade.pid").read_text(encoding="ascii").strip() == str(proc.pid)
        assert (data / "logs" / "app.log").is_file()
        worlds = httpx.post(f"http://127.0.0.1:{PORT}/api/agent/story_worlds", json={}, trust_env=False).json()
        assert worlds[0]["name"] == "El Archipiélago de Sal"
    finally:
        proc.terminate()
        proc.wait(timeout=15)
    if os.name != "nt":  # TerminateProcess on Windows skips the cleanup
        assert not (data / "scheherazade.pid").exists()
