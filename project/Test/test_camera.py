import unittest
from unittest.mock import patch

import cv2
import numpy as np

from project.Core.models import CameraConfig
from project.Driver.camera import Camera


class FakeCapture:
    def __init__(self):
        self.opened = True
        self.released = False
        self.properties = {
            cv2.CAP_PROP_FRAME_WIDTH: 640.0,
            cv2.CAP_PROP_FRAME_HEIGHT: 480.0,
            cv2.CAP_PROP_FPS: 120.0,
            cv2.CAP_PROP_FOURCC: float(cv2.VideoWriter_fourcc(*"MJPG")),
            cv2.CAP_PROP_BUFFERSIZE: 1.0,
        }

    def isOpened(self):
        return self.opened

    def set(self, property_id, value):
        self.properties[property_id] = float(value)
        return True

    def get(self, property_id):
        return self.properties.get(property_id, 0.0)

    def read(self):
        return True, np.zeros((2, 3, 3), dtype=np.uint8)

    def release(self):
        self.released = True
        self.opened = False


class CameraTests(unittest.TestCase):
    def test_packet_adds_sequence_and_rotates_frame(self):
        fake = FakeCapture()
        config = CameraConfig(
            width=640, height=480, fps=120, rotation=90, undistort=False
        )

        with patch("project.Driver.camera.cv2.VideoCapture", return_value=fake):
            with Camera(config) as camera:
                first = camera.capture_packet()
                second = camera.capture_packet()

        self.assertEqual(first.sequence, 0)
        self.assertEqual(second.sequence, 1)
        self.assertEqual(first.frame.shape, (3, 2, 3))
        self.assertLessEqual(first.captured_at, second.captured_at)
        self.assertTrue(fake.released)

    def test_actual_mode_has_no_warnings_when_driver_accepts_it(self):
        fake = FakeCapture()
        config = CameraConfig(
            width=640, height=480, fps=120, fourcc="MJPG", undistort=False
        )

        with patch("project.Driver.camera.cv2.VideoCapture", return_value=fake):
            with Camera(config) as camera:
                actual = camera.actual_settings()
                warnings = camera.mode_warnings()

        self.assertEqual(actual["width"], 640)
        self.assertEqual(actual["height"], 480)
        self.assertEqual(actual["fourcc"], "MJPG")
        self.assertEqual(warnings, [])

    def test_legacy_open_and_capture_api_still_works(self):
        fake = FakeCapture()
        with patch("project.Driver.camera.cv2.VideoCapture", return_value=fake):
            camera = Camera(CameraConfig(undistort=False))
            self.assertTrue(camera.open(main_size=(640, 480), fps=120))
            self.assertIsNotNone(camera.capture())
            camera.close()

    def test_undistortion_is_applied_by_default(self):
        fake = FakeCapture()
        corrected = np.ones((2, 3, 3), dtype=np.uint8)

        with patch("project.Driver.camera.cv2.VideoCapture", return_value=fake), patch(
            "project.Driver.camera.Undistorter"
        ) as undistorter_class:
            undistorter = undistorter_class.return_value
            undistorter.apply.return_value = corrected
            undistorter.describe.return_value = {
                "enabled": True,
                "calibration_width": 640,
                "calibration_height": 480,
            }
            with Camera(CameraConfig()) as camera:
                packet = camera.capture_packet()
                actual = camera.actual_settings()

        undistorter.apply.assert_called_once()
        self.assertIs(packet.frame, corrected)
        self.assertTrue(actual["undistortion"]["enabled"])

    def test_default_target_is_120_fps(self):
        self.assertEqual(CameraConfig().fps, 120.0)

    def test_config_rejects_invalid_rotation(self):
        with self.assertRaises(ValueError):
            CameraConfig(rotation=45).validate()


if __name__ == "__main__":
    unittest.main()
