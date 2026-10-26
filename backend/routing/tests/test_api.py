"""End-to-end API tests with the third-party services stubbed out."""

from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from routing.services.osrm import RawRoute
from routing.services.weather import Forecast


def line(lon: float, n: int = 100, lat_span: float = 3.0) -> list[tuple[float, float]]:
    return [(35 + lat_span * i / n, lon) for i in range(n + 1)]


def raw(lon: float, hours: float) -> RawRoute:
    coords = line(lon)
    return RawRoute(coords, None, hours * 3600, 330_000, ["I 35"])


def calm(n_hours: int) -> Forecast:
    return Forecast([5.0] * n_hours, [8.0] * n_hours, [0.0] * n_hours, [0.0] * n_hours)


def windy(n_hours: int) -> Forecast:
    return Forecast([40.0] * n_hours, [50.0] * n_hours, [0.0] * n_hours, [0.0] * n_hours)


class PlanApiTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.body = {
            "origin": {"label": "A", "lat": 35.0, "lon": -97.0},
            "destination": {"label": "B", "lat": 38.0, "lon": -97.0},
            "departure": (timezone.now() + timedelta(hours=1)).isoformat(),
            "load_weight_lb": 45_000,
            "interval_miles": 25,
        }

    def _plan(self, routes, weather_for_lon):
        def fake_weather(points, start, hours):
            return [weather_for_lon(lon)(hours) for _, lon in points]

        with (
            mock.patch("routing.planner.osrm.fetch_routes", return_value=routes),
            mock.patch("routing.planner.weather.fetch_hourly", side_effect=fake_weather),
        ):
            return self.client.post("/api/plan", self.body, format="json")

    def test_recommends_calm_route_over_faster_windy_one(self):
        routes = [raw(-97.0, hours=5), raw(-98.0, hours=6), raw(-99.0, hours=7)]
        # Fastest route is windy; 40 mph with a 45,000 lb load is Severe.
        resp = self._plan(routes, lambda lon: windy if lon == -97.0 else calm)

        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(len(data["routes"]), 3)
        self.assertEqual(data["recommended_route_id"], 1)
        self.assertEqual(data["routes"][0]["max_risk"], "severe")
        self.assertTrue(all(c["load_applied"] for c in data["routes"][0]["checkpoints"]))
        self.assertIn("Severe", data["recommendation"])

    def test_checkpoint_spacing_and_etas(self):
        resp = self._plan([raw(-97.0, 5), raw(-98.0, 6), raw(-99.0, 7)], lambda lon: calm)
        cps = resp.json()["routes"][0]["checkpoints"]
        self.assertEqual([c["mile"] for c in cps[:4]], [0.0, 25.0, 50.0, 75.0])
        hours = [c["hours_from_departure"] for c in cps]
        self.assertEqual(hours, sorted(hours))

    def test_rejects_bad_interval(self):
        self.body["interval_miles"] = 15
        resp = self.client.post("/api/plan", self.body, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_rejects_past_departure(self):
        self.body["departure"] = (timezone.now() - timedelta(days=1)).isoformat()
        resp = self.client.post("/api/plan", self.body, format="json")
        self.assertEqual(resp.status_code, 400)


class HeatmapApiTests(SimpleTestCase):
    def test_frames_cover_48_hours(self):
        body = {
            "corridor": [[list(p) for p in line(-97.0, n=20)]],
            "departure": (timezone.now() + timedelta(hours=1)).isoformat(),
            "load_weight_lb": 20_000,
        }
        with mock.patch(
            "routing.heatmap.weather.fetch_hourly",
            side_effect=lambda pts, start, hours: [calm(hours) for _ in pts],
        ):
            resp = APIClient().post("/api/heatmap", body, format="json")

        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(len(data["hours"]), 49)
        self.assertEqual(len(data["frames"]["risk"]), 49)
        self.assertTrue(data["cells"])
        self.assertEqual(len(data["frames"]["risk"][0]), len(data["cells"]))
