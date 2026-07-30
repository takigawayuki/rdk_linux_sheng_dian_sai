import tempfile
import unittest
from pathlib import Path

import numpy as np

from project.Algorithm.rod_mapper import RodMapper
from project.Core.models import BallDetection, BallTrack, FramePacket
from project.Services.vision_pipeline import VisionPipeline


class FakeDetector:
    def __init__(self, detection):
        self.detection = detection

    def detect(self, frame, predicted_x=None):
        return self.detection


class FakeTracker:
    def __init__(self, track):
        self.track = track

    def predicted_x(self, timestamp):
        return None

    def update(self, detection, timestamp):
        return self.track


class VisionPipelineTests(unittest.TestCase):
    def make_pipeline(self, directory, track):
        calibration = Path(directory) / "rod.json"
        RodMapper(0.04, -12.4).save(calibration)
        detection = BallDetection(True, 310.0, 248.0, 12.0, 0.9, 1)
        return VisionPipeline(
            calibration,
            detector=FakeDetector(detection),
            tracker=FakeTracker(track),
        )

    def test_maps_position_velocity_and_target_error(self):
        track = BallTrack(
            valid=True,
            pixel_x=335.0,
            pixel_y=248.0,
            velocity_x_px_s=50.0,
            confidence=0.8,
            detected=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            pipeline = self.make_pipeline(directory, track)
            result = pipeline.process(
                FramePacket(np.zeros((10, 10, 3), dtype=np.uint8), 1.5, 12),
                target_position_cm=2.0,
            )
        measurement = result.measurement
        self.assertAlmostEqual(measurement.position_cm, 1.0)
        self.assertAlmostEqual(measurement.velocity_cm_s, 2.0)
        self.assertAlmostEqual(measurement.error_cm, 1.0)
        self.assertTrue(measurement.valid)
        self.assertEqual(measurement.sequence, 12)

    def test_lost_track_has_no_position_or_error(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline = self.make_pipeline(directory, BallTrack(valid=False))
            result = pipeline.process(
                FramePacket(np.zeros((10, 10, 3), dtype=np.uint8), 1.5, 13)
            )
        self.assertFalse(result.measurement.valid)
        self.assertIsNone(result.measurement.position_cm)
        self.assertIsNone(result.measurement.error_cm)


if __name__ == "__main__":
    unittest.main()
