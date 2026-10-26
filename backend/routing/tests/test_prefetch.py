"""Browser-side weather prefetch: needs -> upload -> plan without server weather calls."""

from datetime import date, timedelta
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from routing.services import UpstreamError
from routing.tests.test_api import raw


def calm_block(hours: int) -> dict:
    return {
        "wind_speed_10m": [5.0] * hours,
        "wind_gusts_10m": [9.0] * hours,
        "rain": [0.0] * hours,
        "showers": [None] * hours,  # Open-Meteo sends null for missing values
        "snowfall": [0.0] * hours,
    }


class PrefetchTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.trip = {
            "origin": {"label": "A", "lat": 35.0, "lon": -97.0},
            "destination": {"label": "B", "lat": 38.0, "lon": -97.0},
            "departure": (timezone.now() + timedelta(hours=1)).isoformat(),
        }
        routes = [raw(-97.0, hours=5), raw(-98.0, hours=6), raw(-99.0, hours=7)]
        patcher = mock.patch("routing.planner.osrm.fetch_routes", return_value=routes)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _upload_needs(self) -> dict:
        needs = self.client.post("/api/weather/needs", self.trip, format="json").json()
        days = (date.fromisoformat(needs["end_date"]) - date.fromisoformat(needs["start_date"])).days + 1
        points = needs["points"]
        for i in range(0, len(points), 100):
            batch = points[i : i + 100]
            resp = self.client.post(
                "/api/weather",
                {"points": batch, "hourly": [calm_block(days * 24) for _ in batch]},
                format="json",
            )
            self.assertEqual(resp.status_code, 200, resp.content)
        return needs

    def test_needs_cover_all_spacings_and_heatmap(self):
        needs = self._upload_needs()
        self.assertTrue(needs["points"])
        self.assertLessEqual(needs["start_date"], needs["end_date"])

        # With the browser's forecasts cached, the server never calls Open-Meteo.
        boom = mock.patch(
            "routing.services.weather._fetch_batch", side_effect=UpstreamError("rate limited")
        )
        with boom:
            for interval in (10, 25, 50):
                with self.subTest(interval=interval):
                    body = {**self.trip, "load_weight_lb": 20_000, "interval_miles": interval}
                    resp = self.client.post("/api/plan", body, format="json")
                    self.assertEqual(resp.status_code, 200, resp.content)
            plan = resp.json()
            heat = self.client.post(
                "/api/heatmap",
                {"corridor": plan["corridor"], "departure": plan["departure"], "load_weight_lb": 20_000},
                format="json",
            )
            self.assertEqual(heat.status_code, 200, heat.content)

    def test_upload_rejects_points_off_the_lattice(self):
        resp = self.client.post(
            "/api/weather", {"points": [[35.1234, -97.0]], "hourly": [calm_block(24)]}, format="json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_upload_rejects_non_numeric_values(self):
        block = calm_block(24)
        block["rain"][3] = "lots"
        resp = self.client.post("/api/weather", {"points": [[35.0, -97.0]], "hourly": [block]}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_short_upload_does_not_replace_longer_forecast(self):
        self.client.post("/api/weather", {"points": [[35.0, -97.0]], "hourly": [calm_block(96)]}, format="json")
        resp = self.client.post("/api/weather", {"points": [[35.0, -97.0]], "hourly": [calm_block(24)]}, format="json")
        self.assertEqual(resp.json()["stored"], 0)
