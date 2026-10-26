"""Place search via Photon (OpenStreetMap data, no API key)."""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.core.cache import cache

from . import get_json, make_session

_session = make_session()


class PlaceNotFound(Exception):
    pass


def _label(props: dict) -> str:
    parts = [props.get("name"), props.get("city"), props.get("state"), props.get("country")]
    seen: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return ", ".join(seen)


def search(query: str, limit: int = 5) -> list[dict]:
    query = query.strip()
    if not query:
        return []
    key = "geo:" + hashlib.sha1(f"{query.lower()}|{limit}".encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached

    data = get_json(_session, settings.GEOCODER_URL, {"q": query, "limit": limit, "lang": "en"})
    results = []
    for feature in data.get("features", []):
        lon, lat = feature["geometry"]["coordinates"][:2]
        results.append({"label": _label(feature.get("properties", {})), "lat": lat, "lon": lon})
    cache.set(key, results, 24 * 3600)
    return results


def resolve(query: str) -> dict:
    """Best match for a free-text place."""
    results = search(query, limit=1)
    if not results:
        raise PlaceNotFound(f"Could not find a place called '{query}'.")
    return results[0]
