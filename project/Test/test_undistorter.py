import unittest
from pathlib import Path

import numpy as np

from project.Driver.calibration.undistorter import Undistorter


CALIBRATION_FILE = (
    Path(__file__).resolve().parents[1]
    / "Driver"
    / "calibration"
    / "camera_calibration.npz"
)


class UndistorterTests(unittest.TestCase):
    def test_bundled_calibration_corrects_640_by_480_frame(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        undistorter = Undistorter(CALIBRATION_FILE)

        corrected = undistorter.apply(frame)

        self.assertEqual(corrected.shape, frame.shape)
        self.assertEqual(undistorter.calibration_size, (640, 480))

    def test_incompatible_aspect_ratio_is_rejected(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        undistorter = Undistorter(CALIBRATION_FILE)

        with self.assertRaises(ValueError):
            undistorter.apply(frame)


if __name__ == "__main__":
    unittest.main()
