import time
import unittest

import numpy as np

from project.Core.models import FramePacket
from project.Services.latest_frame_capture import LatestFrameCapture


class FakeCamera:
    def __init__(self):
        self.sequence = 0

    def capture_packet(self):
        time.sleep(0.002)
        packet = FramePacket(
            frame=np.zeros((2, 2, 3), dtype=np.uint8),
            captured_at=time.monotonic(),
            sequence=self.sequence,
        )
        self.sequence += 1
        return packet


class FailingCamera:
    def capture_packet(self):
        raise OSError("camera disconnected")


class LatestFrameCaptureTests(unittest.TestCase):
    def test_returns_newest_frame_without_queueing_old_frames(self):
        capture = LatestFrameCapture(FakeCamera()).start()
        try:
            first = capture.wait_for_frame(timeout=0.2)
            second = capture.wait_for_frame(first.sequence, timeout=0.2)
            self.assertGreater(second.sequence, first.sequence)
            self.assertGreaterEqual(capture.captured_count, 2)
            self.assertGreater(capture.measured_fps, 0.0)
        finally:
            capture.stop()

    def test_propagates_capture_thread_failure(self):
        capture = LatestFrameCapture(FailingCamera()).start()
        try:
            with self.assertRaisesRegex(RuntimeError, "capture thread failed"):
                capture.wait_for_frame(timeout=0.2)
        finally:
            capture.stop()


if __name__ == "__main__":
    unittest.main()
