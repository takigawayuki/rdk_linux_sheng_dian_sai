import unittest

import cv2
import numpy as np

from project.Algorithm.ball_detector import BallDetector


class BallDetectorTests(unittest.TestCase):
    def test_detects_circle_inside_rod_roi(self):
        frame = np.full((480, 640, 3), 225, dtype=np.uint8)
        cv2.rectangle(frame, (0, 215), (639, 285), (245, 245, 245), -1)
        cv2.circle(frame, (310, 248), 12, (70, 70, 70), -1)
        cv2.circle(frame, (306, 244), 4, (245, 245, 245), -1)

        detection = BallDetector().detect(frame)

        self.assertTrue(detection.detected)
        self.assertAlmostEqual(detection.pixel_x, 310, delta=3)
        self.assertAlmostEqual(detection.pixel_y, 248, delta=3)
        self.assertGreater(detection.confidence, 0.4)

    def test_rejects_empty_roi(self):
        frame = np.full((480, 640, 3), 225, dtype=np.uint8)
        detection = BallDetector().detect(frame)
        self.assertFalse(detection.detected)

    def test_rejects_candidate_far_from_prediction(self):
        frame = np.full((480, 640, 3), 225, dtype=np.uint8)
        cv2.circle(frame, (310, 248), 12, (40, 40, 40), -1)
        detection = BallDetector().detect(frame, predicted_x=100)
        self.assertFalse(detection.detected)


if __name__ == "__main__":
    unittest.main()
