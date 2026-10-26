"""Hourly forecasts from Open-Meteo, snapped to a lattice, batched and cached.

Open-Meteo hourly precipitation values are totals for the preceding hour, which
is exactly the in/hr rate the risk rules use. Rain is reported in mm and
snowfall in cm, and both are converted to inches here.

Quota: the free API counts every location in a request as one call (about 600
per minute). Two things keep a trip well inside that:

* Lookups snap to a ``WEATHER_GRID_DEG`` lattice (0.25° by default, about the
  GFS model grid). Nearby checkpoints, all three checkpoint spacings and the
  heatmap cells (which sit on the same lattice) share one forecast.
* Each lattice point is fetched once for a fixed window starting today, so
  replanning with another departure time or load reuses the cache.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.cache import cache

from . import UpstreamError, get_json, make_session

_session = make_session()

BATCH_SIZE = 100  # locations per request; keeps the URL well under length limits
MAX_WORKERS = 4
WINDOW_DAYS = 12  # 7-day departure limit + 48 h slider + a long trip; < 14 days = 1 call each
MM_PER_INCH = 25.4
CM_PER_INCH = 2.54


@dataclass
class Forecast:
    """Hourly series for one location; index 0 is the requested start hour (UTC)."""

    wind_mph: list[float]
    gust_mph: list[float]
    rain_in: list[float]
    snow_in: list[float]

    def at(self, hour_index: int) -> dict:
        i = min(max(hour_index, 0), len(self.wind_mph) - 1)
        return {
            "wind_mph": self.wind_mph[i],
            "gust_mph": self.gust_mph[i],
            "rain_in_hr": self.rain_in[i],
            "snow_in_hr": self.snow_in[i],
        }

    def window(self, offset: int, hours: int) -> Forecast:
        end = offset + hours
        if offset < 0 or end > len(self.wind_mph):
            raise UpstreamError("The forecast doesn't reach that far ahead. Pick an earlier departure.")
        return Forecast(
            self.wind_mph[offset:end], self.gust_mph[offset:end], self.rain_in[offset:end], self.snow_in[offset:end]
        )


def snap(lat: float, lon: float, grid_deg: float | None = None) -> tuple[float, float]:
    """Nearest point on the weather lattice (unchanged when the lattice is disabled)."""
    g = settings.WEATHER_GRID_DEG if grid_deg is None else grid_deg
    if g <= 0:
        return round(lat, 3), round(lon, 3)
    return round(round(lat / g) * g, 4), round(round(lon / g) * g, 4)


def _num(values: list | None, n: int, scale: float = 1.0) -> list[float]:
    values = values or []
    out = [(v or 0.0) / scale for v in values[:n]]
    return out + [0.0] * (n - len(out))


def forecast_window_start() -> datetime:
    # Back off a little so a departure up to an hour ago, just after midnight UTC, still fits.
    earliest = datetime.now(timezone.utc) - timedelta(hours=2)
    return earliest.replace(hour=0, minute=0, second=0, microsecond=0)


def _key(point: tuple[float, float], window_start: datetime) -> str:
    return f"wx:{point[0]}:{point[1]}:{window_start:%Y%m%d}"


# Requested from Open-Meteo, by the server or by the browser (see store_client_forecasts).
HOURLY_VARIABLES = ["wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall"]
FIXED_PARAMS = {"hourly": ",".join(HOURLY_VARIABLES), "wind_speed_unit": "mph", "timezone": "GMT"}


def parse_hourly(h: dict) -> Forecast:
    """Open-Meteo ``hourly`` block (mph, mm, cm) -> Forecast in mph and inches."""
    hours = len(h.get("wind_speed_10m") or [])
    rain = [r + s for r, s in zip(_num(h.get("rain"), hours), _num(h.get("showers"), hours))]
    return Forecast(
        wind_mph=_num(h.get("wind_speed_10m"), hours),
        gust_mph=_num(h.get("wind_gusts_10m"), hours),
        rain_in=[v / MM_PER_INCH for v in rain],
        snow_in=_num(h.get("snowfall"), hours, CM_PER_INCH),
    )


def _fetch_batch(points: list[tuple[float, float]], window_start: datetime) -> list[Forecast]:
    params = {
        **FIXED_PARAMS,
        "latitude": ",".join(str(lat) for lat, _ in points),
        "longitude": ",".join(str(lon) for _, lon in points),
        "start_date": window_start.strftime("%Y-%m-%d"),
        "end_date": (window_start + timedelta(days=WINDOW_DAYS - 1)).strftime("%Y-%m-%d"),
    }
    if settings.OPEN_METEO_API_KEY:
        params["apikey"] = settings.OPEN_METEO_API_KEY
    data = get_json(_session, settings.OPEN_METEO_URL, params, timeout=30, body_on_status=(400,))
    if isinstance(data, dict) and data.get("error"):
        raise UpstreamError(f"Weather forecast unavailable: {data.get('reason')}")
    items = data if isinstance(data, list) else [data]
    if len(items) != len(points):
        raise UpstreamError("Weather service returned an unexpected number of locations.")
    return [parse_hourly(item.get("hourly", {})) for item in items]


def store_client_forecasts(points: list[tuple[float, float]], hourly: list[dict]) -> int:
    """Cache forecasts the browser fetched from Open-Meteo itself.

    Free-tier quota is per IP, and cloud hosts share outbound IPs with many other
    apps, so the server's own requests can be rate-limited before it makes any.
    The browser has its own quota. Entries only fill gaps: a longer forecast
    already in the cache is never replaced by a shorter one.
    """
    start = forecast_window_start()
    fresh = {}
    existing = cache.get_many([_key(p, start) for p in points])
    for p, h in zip(points, hourly):
        f = parse_hourly(h)
        key = _key(p, start)
        old = existing.get(key)
        if old is None or len(old.wind_mph) < len(f.wind_mph):
            fresh[key] = f
    cache.set_many(fresh, settings.WEATHER_CACHE_SECONDS)
    return len(fresh)


def fetch_hourly(points: list[tuple[float, float]], start: datetime, hours: int) -> list[Forecast]:
    """Forecasts aligned with ``points``, for ``hours`` hours from ``start`` (a whole UTC hour)."""
    window_start = forecast_window_start()
    offset = int((start - window_start).total_seconds() // 3600)
    snapped = [snap(lat, lon) for lat, lon in points]
    unique = list(dict.fromkeys(snapped))

    keys = {p: _key(p, window_start) for p in unique}
    cached = cache.get_many(list(keys.values()))
    # A browser-supplied forecast may be too short for this request; refetch those.
    found = {p: cached[k] for p, k in keys.items() if k in cached and len(cached[k].wind_mph) >= offset + hours}
    missing = [p for p in unique if p not in found]

    batches = [missing[i : i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
    if batches:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            results = list(pool.map(lambda b: _fetch_batch(b, window_start), batches))
        fresh = {}
        for batch, forecasts in zip(batches, results):
            for p, f in zip(batch, forecasts):
                found[p] = f
                fresh[keys[p]] = f
        cache.set_many(fresh, settings.WEATHER_CACHE_SECONDS)

    return [found[p].window(offset, hours) for p in snapped]
