from django.test import SimpleTestCase

from routing import geo


def straight_track(miles: float, mph: float = 50.0) -> geo.Track:
    """A due-north line of roughly ``miles`` length driven at ``mph``."""
    n = 200
    lat_span = miles / 69.09
    coords = [(30 + lat_span * i / n, -95.0) for i in range(n + 1)]
    seg = geo.haversine_mi(*coords[0], *coords[1])
    return geo.build_track(coords, [seg / mph * 3600] * n, total_seconds=0)


class TrackTests(SimpleTestCase):
    def test_haversine_one_degree_latitude(self):
        self.assertAlmostEqual(geo.haversine_mi(0, 0, 1, 0), 69.09, places=1)

    def test_truck_speed_cap_slows_fast_segments(self):
        fast = straight_track(100, mph=80)
        self.assertAlmostEqual(fast.total_seconds / 3600, fast.total_miles / geo.TRUCK_MAX_SPEED_MPH, places=3)

    def test_slow_segments_are_kept(self):
        slow = straight_track(100, mph=40)
        self.assertAlmostEqual(slow.total_seconds / 3600, slow.total_miles / 40, places=3)

    def test_mismatched_annotations_fall_back_to_distance(self):
        coords = [(30, -95), (30.5, -95), (31, -95)]
        track = geo.build_track(coords, [1.0], total_seconds=7200)  # wrong length on purpose
        self.assertAlmostEqual(track.total_seconds, 7200, delta=1)

    def test_locate_interpolates_time(self):
        track = straight_track(100, mph=50)
        _, _, secs = track.locate(track.total_miles / 2)
        self.assertAlmostEqual(secs, track.total_seconds / 2, delta=1)


class CheckpointTests(SimpleTestCase):
    def test_spacing_includes_origin_and_destination(self):
        track = straight_track(103)
        samples = geo.sample_checkpoints(track, 25)
        self.assertEqual([round(s.mile) for s in samples], [0, 25, 50, 75, 100, round(track.total_miles)])

    def test_covered_miles_sum_to_route_length(self):
        track = straight_track(237)
        for interval in (10, 25, 50):
            with self.subTest(interval=interval):
                samples = geo.sample_checkpoints(track, interval)
                self.assertAlmostEqual(sum(s.covers_miles for s in samples), track.total_miles, places=6)

    def test_eta_increases_along_route(self):
        samples = geo.sample_checkpoints(straight_track(120), 10)
        times = [s.seconds for s in samples]
        self.assertEqual(times, sorted(times))
        self.assertEqual(times[0], 0)

    def test_no_sliver_checkpoint_before_destination(self):
        track = straight_track(50.2)
        miles = [s.mile for s in geo.sample_checkpoints(track, 25)]
        self.assertEqual(len(miles), 3)  # 0, 25, end - not 0, 25, 50, end


class SimplifyTests(SimpleTestCase):
    def test_keeps_ends(self):
        line = [(i, i) for i in range(1000)]
        out = geo.simplify(line, 50)
        self.assertEqual(len(out), 50)
        self.assertEqual(out[0], line[0])
        self.assertEqual(out[-1], line[-1])
