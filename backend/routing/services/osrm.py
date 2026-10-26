"""Driving routes from OSRM."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from django.conf import settings

from . import UpstreamError, get_json, make_session

_session = make_session()


@dataclass
class RawRoute:
    coords: list[tuple[float, float]]  # (lat, lon)
    segment_seconds: list[float] | None
    duration_s: float
    distance_m: float
    roads: list[str]  # main roads, longest first


def _main_roads(legs: list[dict], top: int = 3) -> list[str]:
    by_road: dict[str, float] = defaultdict(float)
    for leg in legs:
        for step in leg.get("steps", []):
            name = step.get("ref") or step.get("name")
            if name:
                # "I 55; US 66" -> "I 55"
                by_road[name.split(";")[0].strip()] += step.get("distance", 0)
    ranked = sorted(by_road.items(), key=lambda kv: kv[1], reverse=True)
    return [name for name, _ in ranked[:top]]


def _parse(route: dict) -> RawRoute:
    coords = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
    seconds: list[float] = []
    for leg in route["legs"]:
        seconds.extend(leg.get("annotation", {}).get("duration", []))
    return RawRoute(
        coords=coords,
        segment_seconds=seconds or None,
        duration_s=route["duration"],
        distance_m=route["distance"],
        roads=_main_roads(route["legs"]),
    )


def fetch_routes(waypoints: list[tuple[float, float]], alternatives: int = 0) -> list[RawRoute]:
    """Routes through ``waypoints`` [(lat, lon), ...]; OSRM may return fewer alternatives than asked."""
    path = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in waypoints)
    params = {
        "overview": "full",
        "geometries": "geojson",
        "annotations": "duration",
        "steps": "true",
        "alternatives": str(alternatives) if alternatives else "false",
    }
    # OSRM reports "no route" and bad input as HTTP 400 with a JSON code.
    data = get_json(
        _session, f"{settings.OSRM_URL}/route/v1/driving/{path}", params, timeout=30, body_on_status=(400,)
    )
    if data.get("code") != "Ok":
        if data.get("code") == "NoRoute":
            return []
        raise UpstreamError(f"Routing failed: {data.get('message') or data.get('code')}")
    return [_parse(r) for r in data.get("routes", [])]
