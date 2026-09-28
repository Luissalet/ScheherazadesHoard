"""Tiny adapter to Prospero's Hoard for an optional "Illustrate scene" action.

If Prospero answers on its default port, a scene can be sent to its studio
image endpoint and the resulting image URL stored on the turn. When
Prospero is absent, `is_available` is false and the caller hides the button
— this app never bundles its own image model.
"""
from __future__ import annotations

import os
from typing import Optional
from urllib.parse import urlsplit

import httpx

PROSPERO_URL = os.environ.get("SCHEHERAZADE_PROSPERO_URL", "http://127.0.0.1:8815").rstrip("/")


def _local_url(base_url: str) -> bool:
    parsed = urlsplit(base_url)
    return parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost") and not parsed.username


async def is_available(base_url: str = PROSPERO_URL, transport: Optional[httpx.BaseTransport] = None) -> bool:
    if not _local_url(base_url):
        return False
    try:
        async with httpx.AsyncClient(transport=transport, trust_env=False, timeout=1.0) as client:
            r = await client.get(f"{base_url}/api/health")
    except httpx.HTTPError:
        return False
    if r.status_code != 200:
        return False
    try:
        return r.json().get("service") == "prosperos-hoard"
    except ValueError:
        return False


def build_prompt(scene_brief: str, location_name: str = "", mood: str = "") -> str:
    parts = [p for p in (location_name, scene_brief, mood) if p]
    return ", ".join(parts)[:800]


async def illustrate_scene(
    scene_brief: str,
    location_name: str = "",
    mood: str = "",
    world_name: str = "",
    base_url: str = PROSPERO_URL,
    transport: Optional[httpx.BaseTransport] = None,
) -> Optional[str]:
    """Ask Prospero to illustrate the scene. Returns an image URL, or None
    if Prospero is not running or the call fails."""
    prompt = build_prompt(scene_brief, location_name, mood)
    if not prompt or not _local_url(base_url):
        return None
    project_name = f"Scheherazade · {world_name or 'Escenas'}"
    try:
        async with httpx.AsyncClient(transport=transport, trust_env=False, timeout=35.0) as client:
            projects = await client.get(f"{base_url}/api/projects", params={"query": project_name, "limit": 50})
            projects.raise_for_status()
            found = next((p for p in projects.json().get("items", []) if p.get("name") == project_name), None)
            if found:
                project_id = found["id"]
            else:
                created = await client.post(f"{base_url}/api/projects", json={"name": project_name})
                created.raise_for_status()
                project_id = created.json()["id"]
            response = await client.post(f"{base_url}/api/agent/studio_generate_image",
                                         params={"project": project_id}, json={"prompt": prompt, "wait_s": 30})
            response.raise_for_status()
            job = response.json().get("job", {})
            for _ in range(3):
                if job.get("state") == "done":
                    assets = job.get("asset_ids") or []
                    return f"{base_url}/api/assets/{assets[0]}/file" if assets else None
                if job.get("state") == "failed" or not job.get("id"):
                    return None
                polled = await client.get(f"{base_url}/api/agent/studio_job",
                                          params={"job_id": job["id"], "wait_s": 30})
                polled.raise_for_status()
                job = polled.json()
    except (httpx.HTTPError, KeyError, ValueError):
        return None
    return None
