import unittest

from project.Algorithm.ball_tracker import BallTracker
from project.Core.models import BallDetection


def detection(x, y=248, confidence=0.9):
    return BallDetection(
        detected=True,
        pixel_x=x,
        pixel_y=y,
        radius_px=12,
        confidence=confidence,
        candidate_count=1,
    )


class BallTrackerTests(unittest.TestCase):
    def acquire(self, tracker, x=100, timestamp=0.0):
        pending = tracker.update(detection(x), timestamp)
        self.assertFalse(pending.valid)
        return tracker.update(detection(x + 1), timestamp + 1.0 / 120.0)

    def test_bridges_short_occlusion_then_becomes_invalid(self):
        tracker = BallTracker()
        first = self.acquire(tracker)
        predicted = tracker.update(BallDetection(detected=False), 0.02)
        lost = tracker.update(BallDetection(detected=False), 0.20)

        self.assertTrue(first.detected)
        self.assertTrue(predicted.valid)
        self.assertTrue(predicted.predicted)
        self.assertLess(predicted.confidence, 0.9)
        self.assertFalse(lost.valid)

    def test_rejects_large_innovation_during_tracking(self):
        tracker = BallTracker()
        self.acquire(tracker)
        result = tracker.update(detection(300), 0.01)
        self.assertTrue(result.predicted)
        self.assertLess(result.pixel_x, 120)

    def test_prediction_stays_inside_image(self):
        tracker = BallTracker()
        self.acquire(tracker, x=630)
        tracker.update(detection(638), 0.01)
        result = tracker.update(BallDetection(detected=False), 0.02)
        self.assertLessEqual(result.pixel_x, 639)

    def test_reacquisition_requires_consistent_detections(self):
        tracker = BallTracker()
        self.assertFalse(tracker.update(detection(100), 0.0).valid)
        self.assertFalse(tracker.update(detection(180), 0.01).valid)
        acquired = tracker.update(detection(181), 0.02)
        self.assertTrue(acquired.valid)


if __name__ == "__main__":
    unittest.main()
