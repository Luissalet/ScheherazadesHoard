#!/usr/bin/env python3
"""Capture a handful of PNG screenshots of the running app for the README.

Usage:
    python scripts/screenshots.py [base_url]

Assumes a server is already running (e.g. `python -m scheherazades_hoard
--demo --no-browser --port 18860`) and reachable at base_url (default
http://127.0.0.1:18860). Uses the Playwright chromium browser that is
already installed on this machine (PLAYWRIGHT_BROWSERS_PATH) -- it never
calls `playwright install`.

Saves PNGs under docs/media/, downsizing with Pillow if any file lands
above ~400KB.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "docs" / "media"
MAX_BYTES = 400_000


def _find_chromium_executable() -> str | None:
    """Locate the pre-installed chromium binary directly.

    The pinned Playwright *browsers* on this machine may be a slightly
    older revision than the pip package expects. Rather than running
    `playwright install` (forbidden here), we point at whatever chromium
    binary is already present under PLAYWRIGHT_BROWSERS_PATH.
    """
    browsers_root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"))
    if not browsers_root.is_dir():
        return None
    candidates = sorted(browsers_root.glob("chromium-*/chrome-linux/chrome"), reverse=True)
    return str(candidates[0]) if candidates else None


def shrink_if_needed(path: Path) -> None:
    if path.stat().st_size <= MAX_BYTES:
        return
    try:
        from PIL import Image
    except ImportError:
        return
    img = Image.open(path)
    img = img.convert("RGB")
    quality = 85
    while quality >= 40:
        img.save(path.with_suffix(".jpg"), "JPEG", quality=quality, optimize=True)
        jpg = path.with_suffix(".jpg")
        if jpg.stat().st_size <= MAX_BYTES:
            jpg.rename(path.with_suffix(".png"))
            return
        quality -= 15
    # Last resort: leave the PNG as-is (still a valid, if larger, screenshot).
    if path.with_suffix(".jpg").exists():
        path.with_suffix(".jpg").unlink()


def main() -> None:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18860"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        exe = _find_chromium_executable()
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)

        # 1) Worlds list.
        page.goto(base_url, wait_until="networkidle")
        page.wait_for_selector(".grid-cards, .empty-state", timeout=10000)
        page.screenshot(path=str(OUT_DIR / "01-worlds.png"))

        # 2) Open the demo world -> Play screen.
        page.click(".grid-cards .card .btn-primary")
        page.wait_for_selector(".play-layout", timeout=10000)
        time.sleep(0.5)  # let the world_context call settle
        page.screenshot(path=str(OUT_DIR / "02-play.png"))

        # 3) Bible (world entities).
        page.click("text=Biblia >> visible=true", timeout=5000) if page.locator("text=Biblia").count() else page.click("text=Bible")
        page.wait_for_selector(".bible-layout", timeout=10000)
        first_entity = page.locator(".entity-list-item").first
        if first_entity.count():
            first_entity.click()
            time.sleep(0.3)
        page.screenshot(path=str(OUT_DIR / "03-bible.png"))

        # 4) Threads & clocks.
        if page.locator("text=Hilos y relojes").count():
            page.click("text=Hilos y relojes")
        else:
            page.click("text=Threads & clocks")
        page.wait_for_selector(".kanban", timeout=10000)
        page.screenshot(path=str(OUT_DIR / "04-threads.png"))

        browser.close()

    for png in OUT_DIR.glob("*.png"):
        shrink_if_needed(png)

    for f in sorted(OUT_DIR.iterdir()):
        print(f"{f.name}: {f.stat().st_size} bytes")


if __name__ == "__main__":
    main()
