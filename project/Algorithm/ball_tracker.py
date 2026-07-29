"""Alpha-beta pixel tracker that bridges only brief steel-ball occlusions."""

from dataclasses import dataclass
from math import exp
from typing import Optional

from project.Core.models import BallDetection, BallTrack


@dataclass(frozen=True)
class BallTrackerConfig:
    alpha: float = 0.72
    beta: float = 0.18
    max_prediction_seconds: float = 0.12
    max_dt_seconds: float = 0.05
    confidence_decay_seconds: float = 0.07
    max_innovation_px: float = 55.0
    min_pixel_x: float = 0.0
    max_pixel_x: float = 639.0
    max_speed_px_s: float = 1800.0
    acquisition_confirmations: int = 2
    acquisition_max_distance_px: float = 25.0

    def validate(self) -> None:
        if not 0.0 < self.alpha <= 1.0:
            raise ValueError("tracker alpha must be in (0, 1]")
        if not 0.0 <= self.beta <= 1.0:
            raise ValueError("tracker beta must be in [0, 1]")
        if self.max_prediction_seconds <= 0 or self.max_dt_seconds <= 0:
            raise ValueError("tracker time limits must be positive")
        if self.confidence_decay_seconds <= 0 or self.max_innovation_px <= 0:
            raise ValueError("tracker decay and innovation limits must be positive")
        if self.min_pixel_x >= self.max_pixel_x or self.max_speed_px_s <= 0:
            raise ValueError("tracker pixel range and speed limit are invalid")
        if self.acquisition_confirmations <= 0 or self.acquisition_max_distance_px <= 0:
            raise ValueError("tracker acquisition settings must be positive")


class BallTracker:
    """Track x velocity and reject implausible candidates near hands/structure."""

    def __init__(self, config: Optional[BallTrackerConfig] = None):
        self.config = config or BallTrackerConfig()
        self.config.validate()
        self.reset()

    def reset(self) -> None:
        self._x: Optional[float] = None
        self._y: Optional[float] = None
        self._velocity = 0.0
        self._last_timestamp: Optional[float] = None
        self._last_detected_timestamp: Optional[float] = None
        self._confidence = 0.0
        self._pending_detection: Optional[BallDetection] = None
        self._pending_count = 0

    def predicted_x(self, timestamp: float) -> Optional[float]:
        if self._x is None or self._last_timestamp is None:
            return None
        dt = max(0.0, min(self.config.max_dt_seconds, timestamp - self._last_timestamp))
        return self._clamp_x(self._x + self._velocity * dt)

    def update(self, detection: BallDetection, timestamp: float) -> BallTrack:
        timestamp = float(timestamp)
        if self._last_timestamp is None:
            dt = 0.0
        else:
            dt = max(1e-4, min(self.config.max_dt_seconds, timestamp - self._last_timestamp))

        if self._x is not None:
            self._x = self._clamp_x(self._x + self._velocity * dt)

        accepted = False
        if detection.detected and detection.pixel_x is not None and detection.pixel_y is not None:
            measurement_x = float(detection.pixel_x)
            if self._x is None and not self._confirm_acquisition(detection):
                self._last_timestamp = timestamp
                return BallTrack(valid=False)
            innovation = 0.0 if self._x is None else measurement_x - self._x
            if self._x is None or abs(innovation) <= self.config.max_innovation_px:
                if self._x is None:
                    self._x = measurement_x
                    self._y = float(detection.pixel_y)
                    self._velocity = 0.0
                else:
                    self._x += self.config.alpha * innovation
                    if dt > 1e-4:
                        self._velocity += self.config.beta * innovation / dt
                        self._velocity = max(
                            -self.config.max_speed_px_s,
                            min(self.config.max_speed_px_s, self._velocity),
                        )
                    self._x = self._clamp_x(self._x)
                    self._y = (
                        float(detection.pixel_y)
                        if self._y is None
                        else self._y + self.config.alpha * (float(detection.pixel_y) - self._y)
                    )
                self._last_detected_timestamp = timestamp
                self._confidence = detection.confidence
                self._pending_detection = None
                self._pending_count = 0
                accepted = True
        elif self._x is None:
            self._pending_detection = None
            self._pending_count = 0

        self._last_timestamp = timestamp
        if accepted:
            return BallTrack(
                valid=True,
                pixel_x=self._x,
                pixel_y=self._y,
                velocity_x_px_s=self._velocity,
                confidence=self._confidence,
                detected=True,
                predicted=False,
                missed_seconds=0.0,
            )

        if self._x is None or self._last_detected_timestamp is None:
            return BallTrack(valid=False)

        missed_seconds = max(0.0, timestamp - self._last_detected_timestamp)
        if missed_seconds > self.config.max_prediction_seconds:
            self.reset()
            return BallTrack(valid=False, missed_seconds=missed_seconds)

        confidence = self._confidence * exp(
            -missed_seconds / self.config.confidence_decay_seconds
        )
        return BallTrack(
            valid=True,
            pixel_x=self._x,
            pixel_y=self._y,
            velocity_x_px_s=self._velocity,
            confidence=confidence,
            detected=False,
            predicted=True,
            missed_seconds=missed_seconds,
        )

    def _clamp_x(self, value: float) -> float:
        return max(self.config.min_pixel_x, min(self.config.max_pixel_x, value))

    def _confirm_acquisition(self, detection: BallDetection) -> bool:
        """Require a stable candidate before initial/re-acquisition after a long cover."""
        if self.config.acquisition_confirmations == 1:
            return True
        if self._pending_detection is None:
            self._pending_detection = detection
            self._pending_count = 1
            return False
        distance = abs(float(detection.pixel_x) - float(self._pending_detection.pixel_x))
        if distance > self.config.acquisition_max_distance_px:
            self._pending_detection = detection
            self._pending_count = 1
            return False
        self._pending_detection = detection
        self._pending_count += 1
        return self._pending_count >= self.config.acquisition_confirmations
