"""Which forecasts a trip needs, so the browser can fetch them itself.

Covers every checkpoint spacing (10/25/50 mi) and the heatmap grid, so after one
prefetch, switching the spacing and loading the heatmap are all cache hits.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from . import geo, planner
from .heatmap import corridor_grid
from .services import weather

INTERVALS_MI = (10, 25, 50)


def weather_needs(origin: dict, destination: dict, departure: datetime) -> dict:
    o = (origin["lat"], origin["lon"])
    d = (destination["lat"], destination["lon"])
    tracks = planner.build_tracks(planner.find_routes(o, d))

    points: list[tuple[float, float]] = []
    for track in tracks:
        for interval in INTERVALS_MI:
            points.extend((s.lat, s.lon) for s in geo.sample_checkpoints(track, interval))
    cells, _, _ = corridor_grid(planner.corridor_lines(tracks))
    points.extend(cells)
    unique = list(dict.fromkeys(weather.snap(lat, lon) for lat, lon in points))

    # Same window the planner and heatmap read: from today's window start to the
    # end of the slider or the trip, whichever is later.
    start = weather.forecast_window_start()
    last_hour = planner.forecast_start(departure) + timedelta(
        hours=planner.forecast_hours(max(t.total_seconds for t in tracks))
    )
    days = min(weather.WINDOW_DAYS, math.ceil((last_hour - start).total_seconds() / 86400) + 1)

    return {
        "origin": origin,
        "destination": destination,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": (start + timedelta(days=days - 1)).strftime("%Y-%m-%d"),
        "open_meteo_params": weather.FIXED_PARAMS,
        "points": [[lat, lon] for lat, lon in unique],
    }
