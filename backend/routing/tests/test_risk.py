from django.test import SimpleTestCase

from routing.risk import Risk, assess, load_adjusted_wind_risk, rain_risk, snow_risk, wind_risk


class WindBandTests(SimpleTestCase):
    def test_bands_and_boundaries(self):
        cases = [
            (0, Risk.LOW),
            (24.9, Risk.LOW),
            (25, Risk.MODERATE),
            (34.9, Risk.MODERATE),
            (35, Risk.HIGH),
            (44.9, Risk.HIGH),
            (45, Risk.SEVERE),
            (54.9, Risk.SEVERE),
            (55, Risk.NO_TRAVEL),
            (80, Risk.NO_TRAVEL),
        ]
        for mph, expected in cases:
            with self.subTest(mph=mph):
                self.assertEqual(wind_risk(mph), expected)


class RainBandTests(SimpleTestCase):
    def test_bands_and_boundaries(self):
        cases = [
            (0, Risk.LOW),
            (0.099, Risk.LOW),
            (0.10, Risk.MODERATE),
            (0.25, Risk.HIGH),
            (0.50, Risk.SEVERE),
            (1.00, Risk.SEVERE),  # brief: No Travel is strictly > 1.00
            (1.01, Risk.NO_TRAVEL),
        ]
        for rate, expected in cases:
            with self.subTest(rate=rate):
                self.assertEqual(rain_risk(rate), expected)


class SnowBandTests(SimpleTestCase):
    def test_bands_and_boundaries(self):
        cases = [
            (0.49, Risk.LOW),
            (0.5, Risk.MODERATE),
            (1.0, Risk.HIGH),
            (2.0, Risk.SEVERE),
            (3.0, Risk.SEVERE),  # brief: No Travel is strictly > 3.0
            (3.1, Risk.NO_TRAVEL),
        ]
        for rate, expected in cases:
            with self.subTest(rate=rate):
                self.assertEqual(snow_risk(rate), expected)


class LoadRuleTests(SimpleTestCase):
    def test_55_mph_is_no_travel_for_any_load(self):
        self.assertEqual(load_adjusted_wind_risk(55, 0), Risk.NO_TRAVEL)

    def test_45_to_54_mph_heavy_load_is_no_travel(self):
        self.assertEqual(load_adjusted_wind_risk(50, 30_001), Risk.NO_TRAVEL)
        self.assertEqual(load_adjusted_wind_risk(50, 30_000), Risk.SEVERE)  # rule is "> 30,000"

    def test_35_to_44_mph_heavy_load_is_severe(self):
        self.assertEqual(load_adjusted_wind_risk(40, 40_001), Risk.SEVERE)
        self.assertEqual(load_adjusted_wind_risk(40, 40_000), Risk.HIGH)  # rule is "> 40,000"

    def test_load_does_not_affect_lighter_winds(self):
        self.assertEqual(load_adjusted_wind_risk(30, 80_000), Risk.MODERATE)


class AssessTests(SimpleTestCase):
    def test_worst_factor_wins(self):
        a = assess(wind_mph=10, rain_in_hr=0.3, snow_in_hr=1.5, load_lb=20_000)
        self.assertEqual(a.level, Risk.HIGH)
        self.assertEqual(a.rain, Risk.HIGH)
        self.assertEqual(a.snow, Risk.HIGH)
        self.assertEqual(len(a.reasons), 2)

    def test_load_rule_is_reported(self):
        a = assess(wind_mph=38, rain_in_hr=0, snow_in_hr=0, load_lb=45_000)
        self.assertEqual(a.level, Risk.SEVERE)
        self.assertTrue(a.load_applied)
        self.assertIn("45,000 lb", a.reasons[0])

    def test_calm_weather_has_no_reasons(self):
        a = assess(5, 0, 0, 10_000)
        self.assertEqual(a.level, Risk.LOW)
        self.assertEqual(a.reasons, [])
