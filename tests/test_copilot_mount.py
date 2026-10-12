"""The shared assistant panel is mounted ahead of the SPA catch-all and injected into the page."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scheherazades_hoard.api import create_app

PORT = 18862


@pytest.fixture()
def client(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><head></head><body>spa</body></html>", encoding="utf-8")
    app = create_app(tmp_path / "data", static_dir=dist, port=PORT)
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}") as c:
        yield c


def test_copilot_routes_answer_instead_of_the_spa(client):
    info = client.get("/api/copilot/info")
    assert info.status_code == 200
    assert info.json().get("app_id") == "scheherazade" or "scheherazade" in info.text
    launcher = client.get("/api/copilot/launcher.js")
    assert launcher.status_code == 200
    assert "javascript" in launcher.headers["content-type"]


def test_launcher_is_injected_into_the_page(client):
    assert "/api/copilot/launcher.js" in client.get("/").text
