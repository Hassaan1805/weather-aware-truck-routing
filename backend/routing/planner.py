"""Trip planning: routes -> checkpoints -> weather at ETA -> risk -> recommendation."""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from django.core.cache import cache

from . import geo, recommend
from .risk import Risk, assess
from .services import osrm, weather

ROUTE_COUNT = 3
ROUTE_CACHE_SECONDS = 6 * 3600  # roads don't change; lets checkpoint-spacing changes skip OSRM
HEATMAP_HOURS = 48
MAX_DETOUR_RATIO = 1.6  # generated alternatives may be at most this much longer
MAX_OVERLAP = 0.85  # ...and must share less than this fraction of road with others
ROUTE_NAMES = "ABC"


class NoRouteError(Exception):
    pass


def forecast_start(departure: datetime) -> datetime:
    """The whole UTC hour at or before departure; hourly forecasts are indexed from it."""
    return departure.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def forecast_hours(trip_seconds: float) -> int:
    """Hours of forecast to request: the 0-48h slider window or the whole trip, whichever is longer."""
    return max(HEATMAP_HOURS, math.ceil(trip_seconds / 3600)) + 2


# --- routes -----------------------------------------------------------------


def _footprint(coords: list[tuple[float, float]]) -> set[tuple[float, float]]:
    return {(round(lat, 2), round(lon, 2)) for lat, lon in coords}


def _overlap(candidate: osrm.RawRoute, others: list[osrm.RawRoute]) -> float:
    cells = _footprint(candidate.coords)
    taken = set().union(*(_footprint(o.coords) for o in others))
    return len(cells & taken) / max(len(cells), 1)


def _detour_routes(
    origin: tuple[float, float], dest: tuple[float, float], base: osrm.RawRoute
) -> list[osrm.RawRoute]:
    """Extra alternatives forced through waypoints offset to either side of the fastest route."""
    straight = geo.haversine_mi(*origin, *dest)
    mid = base.coords[len(base.coords) // 2]
    heading = geo.bearing_deg(*origin, *dest)
    candidates = []
    for frac in (0.15, 0.3):
        offset = min(max(straight * frac, 15), 120)
        for side in (90, -90):
            candidates.append(geo.offset_point(mid[0], mid[1], heading + side, offset))

    def fetch(via):
        try:
            return osrm.fetch_routes([origin, via, dest])
        except Exception:  # one failed detour shouldn't sink the whole plan
            return []

    with ThreadPoolExecutor(max_workers=4) as pool:
        return [r for routes in pool.map(fetch, candidates) for r in routes[:1]]


def find_routes(origin: tuple[float, float], dest: tuple[float, float]) -> list[osrm.RawRoute]:
    """Up to three distinct routes, fastest first.

    OSRM often returns fewer than three alternatives, so the rest are made by
    routing through waypoints off to each side of the fastest route.
    """
    key = f"routes:{origin[0]:.5f},{origin[1]:.5f}:{dest[0]:.5f},{dest[1]:.5f}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    routes = osrm.fetch_routes([origin, dest], alternatives=ROUTE_COUNT)
    if not routes:
        raise NoRouteError("No drivable route was found between these places.")

    if len(routes) < ROUTE_COUNT:
        base = routes[0]
        extras = sorted(_detour_routes(origin, dest, base), key=lambda r: r.duration_s)
        for extra in extras:
            if len(routes) >= ROUTE_COUNT:
                break
            if extra.distance_m > base.distance_m * MAX_DETOUR_RATIO:
                continue
            if _overlap(extra, routes) >= MAX_OVERLAP:
                continue
            routes.append(extra)

    routes = routes[:ROUTE_COUNT]
    cache.set(key, routes, ROUTE_CACHE_SECONDS)
    return routes


# --- checkpoints & risk -------------------------------------------------------


def _risk_segments(track: geo.Track, checkpoints: list[dict]) -> list[dict]:
    """Split the polyline into runs coloured by the nearest checkpoint's risk."""
    bounds = [(a["mile"] + b["mile"]) / 2 for a, b in zip(checkpoints, checkpoints[1:])]
    segments: list[dict] = []
    ci = 0
    for coord, mile in zip(track.coords, track.cum_miles):
        while ci < len(bounds) and mile > bounds[ci]:
            ci += 1
        level = checkpoints[ci]["risk"]
        point = [round(coord[0], 5), round(coord[1], 5)]
        if segments and segments[-1]["risk"] == level:
            segments[-1]["coords"].append(point)
        else:
            if segments:  # share the boundary vertex so runs connect
                segments[-1]["coords"].append(point)
            segments.append({"risk": level, "coords": [point]})
    return segments


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_tracks(raw_routes: list[osrm.RawRoute]) -> list[geo.Track]:
    return [geo.build_track(r.coords, r.segment_seconds, r.duration_s) for r in raw_routes]


def corridor_lines(tracks: list[geo.Track]) -> list[list[tuple[float, float]]]:
    """Thinned route lines the client sends back to fetch the corridor heatmap."""
    return [
        geo.simplify([(round(lat, 5), round(lon, 5)) for lat, lon in geo.thin_track(t).coords], 300)
        for t in tracks
    ]


def plan_trip(
    origin: dict, destination: dict, departure: datetime, load_lb: float, interval_mi: int
) -> dict:
    o = (origin["lat"], origin["lon"])
    d = (destination["lat"], destination["lon"])
    raw_routes = find_routes(o, d)
    tracks = build_tracks(raw_routes)
    samples = [geo.sample_checkpoints(t, interval_mi) for t in tracks]

    start = forecast_start(departure)
    hours = forecast_hours(max(t.total_seconds for t in tracks))
    offset_s = (departure - start).total_seconds()
    flat = [(s.lat, s.lon) for route in samples for s in route]
    forecasts = iter(weather.fetch_hourly(flat, start, hours))

    routes = []
    scores = []
    for idx, (raw, track, route_samples) in enumerate(zip(raw_routes, tracks, samples)):
        checkpoints = []
        for s in route_samples:
            wx = next(forecasts).at(round((offset_s + s.seconds) / 3600))
            a = assess(wx["wind_mph"], wx["rain_in_hr"], wx["snow_in_hr"], load_lb)
            checkpoints.append(
                {
                    "mile": round(s.mile, 1),
                    "lat": round(s.lat, 5),
                    "lon": round(s.lon, 5),
                    "eta": _iso(departure + timedelta(seconds=s.seconds)),
                    "hours_from_departure": round(s.seconds / 3600, 2),
                    "covers_miles": round(s.covers_miles, 2),
                    "weather": {k: round(v, 2) for k, v in wx.items()},
                    "risk": a.level.key,
                    "risk_score": int(a.level),
                    "factors": {"wind": a.wind.key, "rain": a.rain.key, "snow": a.snow.key},
                    "load_applied": a.load_applied,
                    "reasons": a.reasons,
                }
            )

        drawn = geo.thin_track(track)
        levels = [(Risk[c["risk"].upper()], c["covers_miles"]) for c in checkpoints]
        sc = recommend.score(levels, track.total_seconds)
        scores.append(sc)
        miles_by_risk = {lvl.key: 0.0 for lvl in Risk}
        for lvl, miles in levels:
            miles_by_risk[lvl.key] += miles

        routes.append(
            {
                "id": idx,
                "name": f"Route {ROUTE_NAMES[idx]}",
                "via": raw.roads,
                "distance_miles": round(track.total_miles, 1),
                "duration_hours": round(track.total_seconds / 3600, 2),
                "arrival": _iso(departure + timedelta(seconds=track.total_seconds)),
                "max_risk": max(lvl for lvl, _ in levels).key,
                "avg_risk": round(sc.avg_risk, 3),
                "miles_by_risk": {k: round(v, 1) for k, v in miles_by_risk.items()},
                "severe_or_worse_miles": round(sc.severe_miles, 1),
                "geometry": [[round(lat, 5), round(lon, 5)] for lat, lon in drawn.coords],
                # Vertex times let the map place the truck at any slider hour.
                "geometry_hours": [round(s / 3600, 3) for s in drawn.cum_seconds],
                "risk_segments": _risk_segments(drawn, checkpoints),
                "checkpoints": checkpoints,
            }
        )

    order = recommend.rank(scores)
    best = order[0]
    # Explain the trade-off against the fastest route when we passed it over,
    # otherwise against the runner-up.
    fastest = min(range(len(scores)), key=lambda i: scores[i].duration_s)
    other = fastest if fastest != best else (order[1] if len(order) > 1 else None)
    explanation = recommend.explain(
        scores[best],
        scores[other] if other is not None else None,
        routes[best]["name"],
        routes[other]["name"] if other is not None else "",
    )
    for rank_pos, idx in enumerate(order, start=1):
        routes[idx]["rank"] = rank_pos

    warnings = []
    if scores[best].no_travel_miles > 0:
        warnings.append(
            "Every route crosses No Travel conditions at this departure time. Consider delaying the trip."
        )
    elif scores[best].severe_miles > 0:
        warnings.append("Every route has some Severe weather. Drive with caution or consider a later departure.")
    if len(routes) < ROUTE_COUNT:
        warnings.append(f"Only {len(routes)} distinct route(s) could be found for this trip.")

    return {
        "origin": origin,
        "destination": destination,
        "departure": _iso(departure),
        "load_weight_lb": load_lb,
        "interval_miles": interval_mi,
        "recommended_route_id": best,
        "recommendation": explanation,
        "warnings": warnings,
        "routes": routes,
        "corridor": corridor_lines(tracks),
    }
