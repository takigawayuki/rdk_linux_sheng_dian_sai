"""Background camera reader that keeps only the newest undistorted frame."""

import threading
import time
from typing import Optional

from project.Core.models import FramePacket


class LatestFrameCapture:
    """Overlap camera capture/undistortion with vision without queuing stale frames."""

    def __init__(self, camera):
        self.camera = camera
        self._condition = threading.Condition()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._latest: Optional[FramePacket] = None
        self._error: Optional[BaseException] = None
        self._captured_count = 0
        self._first_captured_at: Optional[float] = None
        self._last_captured_at: Optional[float] = None

    def start(self) -> "LatestFrameCapture":
        with self._condition:
            if self._running:
                return self
            self._running = True
            self._error = None
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="latest-camera-frame",
            daemon=True,
        )
        self._thread.start()
        return self

    def wait_for_frame(
        self, after_sequence: int = -1, timeout: float = 1.0
    ) -> FramePacket:
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                if self._error is not None:
                    raise RuntimeError("camera capture thread failed") from self._error
                if self._latest is not None and self._latest.sequence > after_sequence:
                    return self._latest
                if not self._running:
                    raise RuntimeError("camera capture thread stopped")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("timed out waiting for a new camera frame")
                self._condition.wait(remaining)

    @property
    def captured_count(self) -> int:
        with self._condition:
            return self._captured_count

    @property
    def measured_fps(self) -> float:
        with self._condition:
            if (
                self._captured_count < 2
                or self._first_captured_at is None
                or self._last_captured_at is None
                or self._last_captured_at <= self._first_captured_at
            ):
                return 0.0
            return (self._captured_count - 1) / (
                self._last_captured_at - self._first_captured_at
            )

    def stop(self) -> None:
        with self._condition:
            self._running = False
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _capture_loop(self) -> None:
        try:
            while True:
                with self._condition:
                    if not self._running:
                        return
                packet = self.camera.capture_packet()
                with self._condition:
                    self._latest = packet
                    self._captured_count += 1
                    if self._first_captured_at is None:
                        self._first_captured_at = packet.captured_at
                    self._last_captured_at = packet.captured_at
                    self._condition.notify_all()
        except BaseException as error:
            with self._condition:
                self._error = error
                self._running = False
                self._condition.notify_all()
