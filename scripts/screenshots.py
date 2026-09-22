#!/usr/bin/env python3
"""Capture a handful of PNG screenshots of the running app for the README.

Usage:
    python scripts/screenshots.py [base_url]

Assumes a server is already running (e.g. `python -m scheherazades_hoard
--demo --no-browser --port 18860`) and reachable at base_url (default
http://127.0.0.1:18860). Uses the Playwright chromium browser that is
already installed on this machine (PLAYWRIGHT_BROWSERS_PATH) -- it never
calls `playwright install`.

Saves PNGs under docs/media/ (English interface, plus the Play screen in
Spanish for README.es.md), quantizing with Pillow if any file lands above
~400KB.
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
    """Keep it a PNG: quantize to a 256-colour palette if it is too big."""
    if path.stat().st_size <= MAX_BYTES:
        return
    try:
        from PIL import Image
    except ImportError:
        return
    with Image.open(path) as img:
        small = img.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    small.save(path, "PNG", optimize=True)


def shoot(page, base_url: str, lang: str, suffix: str = "") -> None:
    """The four README views, with the interface in `lang`."""
    page.add_init_script(f"localStorage.setItem('scheherazade.lang', '{lang}')")
    page.goto(base_url, wait_until="networkidle")
    page.wait_for_selector(".grid-cards, .empty-state", timeout=10000)
    if not suffix:
        page.screenshot(path=str(OUT_DIR / "01-worlds.png"))

    # Play screen of the demo world.
    page.click(".grid-cards .card .btn-primary")
    page.wait_for_selector(".play-layout", timeout=10000)
    page.wait_for_selector(".chip", timeout=10000)  # the scene's cast has loaded
    time.sleep(0.5)
    page.screenshot(path=str(OUT_DIR / f"02-play{suffix}.png"))
    if suffix:
        return

    # Bible, on a character with relations and established facts.
    page.click("nav >> text=Bible")
    page.wait_for_selector(".bible-layout", timeout=10000)
    page.locator(".entity-list-item", has_text="Marisol Vega").first.click()
    page.wait_for_selector("text=Relations", timeout=10000)
    time.sleep(0.3)
    page.screenshot(path=str(OUT_DIR / "03-bible.png"))

    # Threads & clocks.
    page.click("nav >> text=Threads & clocks")
    page.wait_for_selector(".kanban", timeout=10000)
    time.sleep(0.3)
    page.screenshot(path=str(OUT_DIR / "04-threads.png"))


def main() -> None:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18860"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        exe = _find_chromium_executable()
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        for lang, suffix in (("en", ""), ("es", "-es")):
            page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                                    color_scheme="light")
            shoot(page, base_url, lang, suffix)
            page.close()

        browser.close()

    for png in OUT_DIR.glob("*.png"):
        shrink_if_needed(png)

    for f in sorted(OUT_DIR.iterdir()):
        print(f"{f.name}: {f.stat().st_size} bytes")


if __name__ == "__main__":
    main()
