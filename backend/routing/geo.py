"""Geometry helpers: distances along a route, checkpoint sampling and ETAs."""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass

EARTH_RADIUS_MI = 3958.7613
METERS_PER_MILE = 1609.344

# OSRM's public server only has a car profile. Trucks are governed slower,
# so segments faster than this are slowed down to it.
TRUCK_MAX_SPEED_MPH = 65.0


def haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(a))


@dataclass
class Track:
    """A route polyline with cumulative distance and truck travel time at every vertex."""

    coords: list[tuple[float, float]]  # (lat, lon)
    cum_miles: list[float]
    cum_seconds: list[float]

    @property
    def total_miles(self) -> float:
        return self.cum_miles[-1]

    @property
    def total_seconds(self) -> float:
        return self.cum_seconds[-1]

    def locate(self, mile: float) -> tuple[float, float, float]:
        """(lat, lon, seconds from departure) at a distance along the route."""
        mile = min(max(mile, 0.0), self.total_miles)
        i = bisect_left(self.cum_miles, mile)
        if i == 0:
            lat, lon = self.coords[0]
            return lat, lon, 0.0
        m0, m1 = self.cum_miles[i - 1], self.cum_miles[i]
        t = 0.0 if m1 == m0 else (mile - m0) / (m1 - m0)
        (la0, lo0), (la1, lo1) = self.coords[i - 1], self.coords[i]
        s0, s1 = self.cum_seconds[i - 1], self.cum_seconds[i]
        return la0 + (la1 - la0) * t, lo0 + (lo1 - lo0) * t, s0 + (s1 - s0) * t


def build_track(
    coords: list[tuple[float, float]],
    segment_seconds: list[float] | None,
    total_seconds: float,
    max_speed_mph: float = TRUCK_MAX_SPEED_MPH,
) -> Track:
    """Accumulate distance and truck time along a polyline.

    ``segment_seconds`` are OSRM's per-segment durations. If they don't line up
    with the geometry, the route's total duration is spread by distance instead.
    """
    seg_miles = [
        haversine_mi(a[0], a[1], b[0], b[1]) for a, b in zip(coords, coords[1:])
    ]
    if segment_seconds is None or len(segment_seconds) != len(seg_miles):
        dist = sum(seg_miles) or 1.0
        segment_seconds = [total_seconds * m / dist for m in seg_miles]

    cum_miles = [0.0]
    cum_seconds = [0.0]
    for miles, secs in zip(seg_miles, segment_seconds):
        truck_secs = max(secs, miles / max_speed_mph * 3600)
        cum_miles.append(cum_miles[-1] + miles)
        cum_seconds.append(cum_seconds[-1] + truck_secs)
    return Track(coords=coords, cum_miles=cum_miles, cum_seconds=cum_seconds)


@dataclass
class Sample:
    mile: float
    lat: float
    lon: float
    seconds: float
    covers_miles: float  # route miles this checkpoint represents


def sample_checkpoints(track: Track, interval_mi: float) -> list[Sample]:
    """Checkpoints at the origin, every ``interval_mi`` miles, and the destination.

    Each checkpoint represents the stretch of road closer to it than to its
    neighbours (half the gap on each side), so the miles add up to the route length.
    """
    total = track.total_miles
    miles = [0.0]
    m = interval_mi
    while m < total - 0.5:  # skip a sliver checkpoint right before the destination
        miles.append(m)
        m += interval_mi
    if total > 0:
        miles.append(total)

    samples = []
    for i, mile in enumerate(miles):
        left = (mile - miles[i - 1]) / 2 if i > 0 else 0.0
        right = (miles[i + 1] - mile) / 2 if i < len(miles) - 1 else 0.0
        lat, lon, secs = track.locate(mile)
        samples.append(Sample(mile=mile, lat=lat, lon=lon, seconds=secs, covers_miles=left + right))
    return samples


def simplify_indices(coords: list[tuple[float, float]], tolerance_deg: float) -> list[int]:
    """Douglas-Peucker: indices of the vertices needed to stay within ``tolerance_deg`` of the line."""
    n = len(coords)
    if n < 3:
        return list(range(n))
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    tol_sq = tolerance_deg**2
    while stack:
        a, b = stack.pop()
        (ay, ax), (by, bx) = coords[a], coords[b]
        dx, dy = bx - ax, by - ay
        seg_sq = dx * dx + dy * dy
        worst, worst_i = -1.0, -1
        for i in range(a + 1, b):
            py, px = coords[i]
            if seg_sq == 0:
                d = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_sq))
                d = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if d > worst:
                worst, worst_i = d, i
        if worst > tol_sq:
            keep[worst_i] = True
            stack.append((a, worst_i))
            stack.append((worst_i, b))
    return [i for i, k in enumerate(keep) if k]


def thin_track(track: Track, tolerance_deg: float = 0.0004) -> Track:
    """A lighter copy of the track for drawing (~40 m tolerance), keeping exact distances and times."""
    idx = simplify_indices(track.coords, tolerance_deg)
    return Track(
        coords=[track.coords[i] for i in idx],
        cum_miles=[track.cum_miles[i] for i in idx],
        cum_seconds=[track.cum_seconds[i] for i in idx],
    )


def simplify(coords: list[tuple[float, float]], max_points: int) -> list[tuple[float, float]]:
    """Evenly thin a polyline, always keeping both ends."""
    if len(coords) <= max_points:
        return list(coords)
    step = (len(coords) - 1) / (max_points - 1)
    return [coords[round(i * step)] for i in range(max_points)]


def offset_point(lat: float, lon: float, bearing_deg: float, dist_mi: float) -> tuple[float, float]:
    """Point ``dist_mi`` away from (lat, lon) along a compass bearing."""
    d = dist_mi / EARTH_RADIUS_MI
    b = math.radians(bearing_deg)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360
