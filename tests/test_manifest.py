"""Validates faustus-plugin.json exactly the way Faustus itself would."""
from __future__ import annotations

from pathlib import Path

from faustus_manifest import check_repo

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_manifest_passes_faustus_validation():
    data = check_repo(REPO_ROOT)
    assert data["id"] == "scheherazade"
    assert data["app"]["health"]["expect"]["service"] == "scheherazades-hoard"
    assert data["mcp"]["transport"] == "stdio"
