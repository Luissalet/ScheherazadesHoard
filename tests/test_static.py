"""The SPA file server must never serve anything outside frontend/dist."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scheherazades_hoard.api import create_app

PORT = 18861


@pytest.fixture()
def client(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("TOP SECRET", encoding="utf-8")
    app = create_app(tmp_path / "data", static_dir=dist, port=PORT)
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}") as c:
        yield c


def test_serves_built_assets_and_spa_fallback(client):
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert "spa" in client.get("/worlds/abc/play").text


@pytest.mark.parametrize("path", [
    "/assets/..%2f..%2fsecret.txt",
    "/..%2fsecret.txt",
    "/%2e%2e/secret.txt",
    "/assets/%2e%2e/%2e%2e/secret.txt",
    "/assets/..%5c..%5csecret.txt",
])
def test_path_traversal_never_escapes_dist(client, path):
    r = client.get(path)
    assert "TOP SECRET" not in r.text


def test_absolute_path_is_not_served(client, tmp_path):
    secret = (tmp_path / "secret.txt").as_posix()
    r = client.get("/" + secret)  # "//tmp/.../secret.txt"
    assert "TOP SECRET" not in r.text


def test_data_dir_database_is_not_served(client):
    r = client.get("/..%2fdata%2fscheherazade.db")
    assert r.headers["content-type"].startswith("text/html")
    assert b"SQLite" not in r.content


def test_unknown_api_route_is_json_404_not_html(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["error"] == "not_found"


def test_ui_cannot_be_framed_by_a_web_page(client):
    r = client.get("/")
    csp = r.headers["content-security-policy"]
    assert "frame-ancestors 'self' http://127.0.0.1:* http://localhost:*" == csp.strip()
    assert r.headers["x-content-type-options"] == "nosniff"
