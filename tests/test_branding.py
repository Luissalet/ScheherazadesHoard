"""Regression test for usability report #7: the app must ship its own
icon rather than a generic one — a favicon, an `<link rel="icon">` that
points at it, and a mention in both READMEs, so this never silently
regresses to "no favicon, a generic header icon" again.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_favicon_file_exists_and_is_a_valid_svg():
    favicon = REPO_ROOT / "frontend" / "public" / "favicon.svg"
    assert favicon.exists(), "frontend/public/favicon.svg is missing"
    content = favicon.read_text(encoding="utf-8")
    assert content.strip().startswith("<svg")
    assert "viewBox" in content


def test_index_html_links_the_favicon():
    index = (REPO_ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'rel="icon"' in index
    assert "favicon.svg" in index


def test_sidebar_brand_icon_is_not_a_generic_lucide_icon():
    sidebar = (REPO_ROOT / "frontend" / "src" / "components" / "Sidebar.tsx").read_text(encoding="utf-8")
    brand_block = sidebar.split("sidebar-brand-icon", 1)[1][:600]
    assert "<Feather" not in brand_block, "the brand icon must not fall back to a generic lucide glyph"
    assert "<svg" in brand_block


def test_readmes_show_the_icon():
    for name in ("README.md", "README.es.md"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert "favicon.svg" in text, f"{name} does not reference the app icon"
