"""Weather grid along the trip corridor, for the 0-48 h heatmap.

A regular lat/lon grid covers the routes' bounding box; cells farther than the
corridor half-width from every route are dropped. Each remaining cell gets an
hourly forecast and a load-aware risk level, so the client can scrub through
all 49 frames without another request.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from django.conf import settings

from . import geo
from .planner import HEATMAP_HOURS, forecast_start
from .risk import assess
from .services import weather

CELLS_ALONG_LONGEST_SIDE = 32
DEFAULT_LATTICE_DEG = 0.25  # used when weather snapping is disabled
MIN_HALF_WIDTH_MI = 30


def _grid(corridor: list[list[tuple[float, float]]]) -> tuple[list[tuple[float, float]], float, float]:
    points = [p for line in corridor for p in line]
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    mid_lat = (min(lats) + max(lats)) / 2
    cos_lat = max(math.cos(math.radians(mid_lat)), 0.2)

    # Cells are whole multiples of the weather lattice, so every cell is a
    # lattice point and shares its forecast with nearby route checkpoints.
    # Longitude steps are widened by ~1/cos(lat) to keep cells square-ish on the ground.
    base = settings.WEATHER_GRID_DEG or DEFAULT_LATTICE_DEG
    span = max(max(lats) - min(lats), (max(lons) - min(lons)) * cos_lat)
    spacing_lat = base * max(1, math.ceil(span / CELLS_ALONG_LONGEST_SIDE / base))
    spacing_lon = base * max(1, round(spacing_lat / cos_lat / base))
    half_width_mi = max(MIN_HALF_WIDTH_MI, spacing_lat * 69.0)

    pad_lat = half_width_mi / 69.0
    pad_lon = pad_lat / cos_lat
    lat0 = math.floor((min(lats) - pad_lat) / spacing_lat) * spacing_lat
    lon0 = math.floor((min(lons) - pad_lon) / spacing_lon) * spacing_lon
    lat1, lon1 = max(lats) + pad_lat, max(lons) + pad_lon

    # Equirectangular distance is plenty accurate at corridor scale and much
    # cheaper than haversine for grid x route comparisons.
    route_xy = [(lat * 69.0, lon * 69.0 * cos_lat) for lat, lon in points]
    limit_sq = half_width_mi**2

    cells = []
    n_lat = int((lat1 - lat0) / spacing_lat) + 2
    n_lon = int((lon1 - lon0) / spacing_lon) + 2
    for i in range(n_lat):
        lat = round(lat0 + i * spacing_lat, 4)
        y = lat * 69.0
        for j in range(n_lon):
            lon = round(lon0 + j * spacing_lon, 4)
            x = lon * 69.0 * cos_lat
            if any((y - ry) ** 2 + (x - rx) ** 2 <= limit_sq for ry, rx in route_xy):
                cells.append((lat, lon))
    return cells, spacing_lat, spacing_lon


def corridor_grid(corridor: list[list[tuple[float, float]]]) -> tuple[list[tuple[float, float]], float, float]:
    """Heatmap cells for a corridor, plus the cell size in degrees (lat, lon)."""
    return _grid([geo.simplify(line, 120) for line in corridor])


def corridor_heatmap(corridor: list[list[tuple[float, float]]], departure: datetime, load_lb: float) -> dict:
    cells, spacing_lat, spacing_lon = corridor_grid(corridor)
    start = forecast_start(departure)
    frames = HEATMAP_HOURS + 1
    forecasts = weather.fetch_hourly(cells, start, frames)

    risk, wind, rain, snow = [], [], [], []
    for h in range(frames):
        risk_row, wind_row, rain_row, snow_row = [], [], [], []
        for f in forecasts:
            wx = f.at(h)
            risk_row.append(int(assess(wx["wind_mph"], wx["rain_in_hr"], wx["snow_in_hr"], load_lb).level))
            wind_row.append(round(wx["wind_mph"], 1))
            rain_row.append(round(wx["rain_in_hr"], 3))
            snow_row.append(round(wx["snow_in_hr"], 3))
        risk.append(risk_row)
        wind.append(wind_row)
        rain.append(rain_row)
        snow.append(snow_row)

    return {
        "start": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "hours": [
            (start + timedelta(hours=h)).isoformat().replace("+00:00", "Z") for h in range(frames)
        ],
        "cell_size": [round(spacing_lat, 4), round(spacing_lon, 4)],
        "cells": [[lat, lon] for lat, lon in cells],
        "frames": {"risk": risk, "wind_mph": wind, "rain_in_hr": rain, "snow_in_hr": snow},
    }
