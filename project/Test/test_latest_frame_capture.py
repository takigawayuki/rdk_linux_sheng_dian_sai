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


class SlowPreprocessCamera:
    def __init__(self):
        self.sequence = 0

    def capture_raw_packet(self):
        time.sleep(0.001)
        packet = FramePacket(
            frame=np.zeros((2, 2, 3), dtype=np.uint8),
            captured_at=time.monotonic(),
            sequence=self.sequence,
        )
        self.sequence += 1
        return packet

    def preprocess_packet(self, packet):
        time.sleep(0.012)
        return packet


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
            with self.assertRaisesRegex(RuntimeError, "pipeline thread failed"):
                capture.wait_for_frame(timeout=0.2)
        finally:
            capture.stop()

    def test_raw_capture_continues_while_slow_preprocess_drops_old_frames(self):
        capture = LatestFrameCapture(SlowPreprocessCamera()).start()
        try:
            first = capture.wait_for_frame(timeout=0.2)
            time.sleep(0.05)
            latest = capture.wait_for_frame(first.sequence, timeout=0.2)
            self.assertGreater(latest.sequence, first.sequence)
            self.assertGreater(capture.captured_count, capture.preprocessed_count)
            self.assertGreater(capture.preprocess_skipped_count, 0)
        finally:
            capture.stop()


if __name__ == "__main__":
    unittest.main()
