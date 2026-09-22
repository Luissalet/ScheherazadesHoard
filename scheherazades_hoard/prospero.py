"""Tiny adapter to Prospero's Hoard for an optional "Illustrate scene" action.

If Prospero answers on its default port, a scene can be sent to its studio
image endpoint and the resulting image URL stored on the turn. When
Prospero is absent, `is_available` is false and the caller hides the button
— this app never bundles its own image model.
"""
from __future__ import annotations

from typing import Optional

import httpx

PROSPERO_URL = "http://127.0.0.1:8815"


async def is_available(base_url: str = PROSPERO_URL, transport: Optional[httpx.BaseTransport] = None) -> bool:
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
    base_url: str = PROSPERO_URL,
    transport: Optional[httpx.BaseTransport] = None,
) -> Optional[str]:
    """Ask Prospero to illustrate the scene. Returns an image URL, or None
    if Prospero is not running or the call fails."""
    prompt = build_prompt(scene_brief, location_name, mood)
    if not prompt:
        return None
    try:
        async with httpx.AsyncClient(transport=transport, trust_env=False, timeout=30.0) as client:
            r = await client.post(f"{base_url}/api/agent/studio_generate_image", json={"prompt": prompt})
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        body = r.json()
    except ValueError:
        return None
    return body.get("image_url") or body.get("url")
