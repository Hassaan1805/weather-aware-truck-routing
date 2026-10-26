from django.test import SimpleTestCase

from routing.recommend import RouteScore, explain, rank, score
from routing.risk import Risk

L, M, H, S, N = Risk.LOW, Risk.MODERATE, Risk.HIGH, Risk.SEVERE, Risk.NO_TRAVEL


def rs(no_travel=0.0, severe=0.0, high=0.0, avg=0.0, hours=10.0) -> RouteScore:
    return RouteScore(no_travel, severe, high, avg, hours * 3600)


class ScoreTests(SimpleTestCase):
    def test_miles_and_average(self):
        s = score([(L, 50), (H, 25), (S, 20), (N, 5)], duration_s=3600)
        self.assertEqual(s.no_travel_miles, 5)
        self.assertEqual(s.severe_miles, 25)  # Severe or worse
        self.assertEqual(s.high_miles, 25)
        self.assertAlmostEqual(s.avg_risk, (0 * 50 + 2 * 25 + 3 * 20 + 4 * 5) / 100)


class RankTests(SimpleTestCase):
    def test_severe_miles_beat_travel_time(self):
        fast_stormy = rs(severe=10, hours=8)
        slow_clear = rs(severe=0, hours=12)
        self.assertEqual(rank([fast_stormy, slow_clear]), [1, 0])

    def test_high_miles_break_severe_tie(self):
        self.assertEqual(rank([rs(severe=5, high=30), rs(severe=5, high=10)]), [1, 0])

    def test_average_risk_breaks_high_tie(self):
        self.assertEqual(rank([rs(high=10, avg=0.9), rs(high=10, avg=0.4)]), [1, 0])

    def test_time_breaks_full_risk_tie(self):
        self.assertEqual(rank([rs(hours=11), rs(hours=9), rs(hours=10)]), [1, 2, 0])

    def test_no_travel_ranks_below_severe(self):
        # Fewer severe-or-worse miles, but some of them are No Travel.
        self.assertEqual(rank([rs(no_travel=5, severe=5), rs(severe=40)]), [1, 0])


class ExplainTests(SimpleTestCase):
    def test_names_deciding_criterion(self):
        text = explain(rs(severe=0), rs(severe=34), "Route B", "Route A")
        self.assertIn("Severe", text)
        self.assertIn("34 mi", text)

    def test_falls_back_to_time(self):
        text = explain(rs(hours=9), rs(hours=10), "Route A", "Route B")
        self.assertIn("faster", text)
