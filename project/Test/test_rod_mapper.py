import tempfile
import unittest
from pathlib import Path

from project.Algorithm.rod_mapper import RodMapper


class RodMapperTests(unittest.TestCase):
    def test_fits_and_evaluates_linear_mapping(self):
        mapper = RodMapper.fit([(50, -10), (310, 0), (570, 10)])
        stats = mapper.evaluate([(50, -10), (310, 0), (570, 10)])

        self.assertAlmostEqual(mapper.map_pixel(310), 0, places=6)
        self.assertLess(stats.rmse_cm, 1e-6)

    def test_round_trips_json_configuration(self):
        mapper = RodMapper(0.04, -12.4)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mapping.json"
            mapper.save(path, [{"pixel_x": 310, "position_cm": 0}])
            loaded = RodMapper.load(path)
        self.assertAlmostEqual(loaded.map_pixel(310), 0.0)

    def test_optional_clamp_prevents_impossible_positions(self):
        mapper = RodMapper(0.04, -12.4)
        self.assertEqual(mapper.map_pixel(-1000, clamp=True), -12.5)
        self.assertEqual(mapper.map_pixel(1000, clamp=True), 12.5)


if __name__ == "__main__":
    unittest.main()
