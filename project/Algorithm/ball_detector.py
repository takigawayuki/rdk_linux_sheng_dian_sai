"""Initial ROI + Hough-circle steel-ball detector for the collected dataset."""

from dataclasses import dataclass
from math import exp
from typing import Optional

import cv2
import numpy as np

from project.Core.models import BallDetection


@dataclass(frozen=True)
class BallDetectorConfig:
    """Detector values are expressed for the 640x480 undistorted reference image."""

    reference_width: int = 640
    reference_height: int = 480
    roi_top: int = 215
    roi_bottom: int = 285
    min_radius: int = 6
    max_radius: int = 15
    expected_radius: float = 12.5
    rod_y_intercept: float = 238.5
    rod_y_slope: float = 0.032
    median_blur_size: int = 5
    hough_dp: float = 1.1
    hough_min_distance: float = 25.0
    hough_param1: float = 90.0
    hough_param2: float = 16.0
    max_path_error: float = 18.0
    prediction_weight: float = 0.08
    max_prediction_distance: float = 55.0

    def validate(self) -> None:
        if self.reference_width <= 0 or self.reference_height <= 0:
            raise ValueError("reference image dimensions must be positive")
        if not 0 <= self.roi_top < self.roi_bottom <= self.reference_height:
            raise ValueError("invalid detector ROI")
        if not 0 < self.min_radius <= self.max_radius:
            raise ValueError("invalid radius range")
        if self.median_blur_size < 3 or self.median_blur_size % 2 == 0:
            raise ValueError("median blur size must be an odd number >= 3")


class BallDetector:
    """Detect the most plausible circular ball candidate inside the groove ROI."""

    def __init__(self, config: Optional[BallDetectorConfig] = None):
        self.config = config or BallDetectorConfig()
        self.config.validate()

    def detect(
        self, frame: np.ndarray, predicted_x: Optional[float] = None
    ) -> BallDetection:
        if frame is None or frame.size == 0:
            raise ValueError("frame must be a non-empty image")
        if frame.ndim not in (2, 3):
            raise ValueError("frame must be a grayscale or BGR image")

        height, width = frame.shape[:2]
        scale_x = width / self.config.reference_width
        scale_y = height / self.config.reference_height
        radius_scale = (scale_x + scale_y) * 0.5
        top = max(0, int(round(self.config.roi_top * scale_y)))
        bottom = min(height, int(round(self.config.roi_bottom * scale_y)))
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        roi = gray[top:bottom]
        if roi.size == 0:
            return BallDetection(detected=False)

        blurred = cv2.medianBlur(roi, self.config.median_blur_size)
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=self.config.hough_dp,
            minDist=max(1.0, self.config.hough_min_distance * scale_x),
            param1=self.config.hough_param1,
            param2=self.config.hough_param2,
            minRadius=max(1, int(round(self.config.min_radius * radius_scale))),
            maxRadius=max(2, int(round(self.config.max_radius * radius_scale))),
        )
        if circles is None or len(circles[0]) == 0:
            return BallDetection(detected=False)

        candidates = []
        for x, local_y, radius in circles[0]:
            y = float(local_y + top)
            expected_y = (
                self.config.rod_y_intercept
                + self.config.rod_y_slope * (float(x) / scale_x)
            ) * scale_y
            path_error = abs(y - expected_y)
            if path_error > self.config.max_path_error * scale_y:
                continue
            radius_error = abs(float(radius) - self.config.expected_radius * radius_scale)
            prediction_error = (
                0.0 if predicted_x is None else abs(float(x) - predicted_x)
            )
            if (
                predicted_x is not None
                and prediction_error > self.config.max_prediction_distance * scale_x
            ):
                continue
            score = path_error + radius_error * 0.35 + prediction_error * self.config.prediction_weight
            candidates.append((score, float(x), y, float(radius), path_error, radius_error))

        if not candidates:
            return BallDetection(detected=False, candidate_count=len(circles[0]))

        candidates.sort(key=lambda item: item[0])
        _, x, y, radius, path_error, radius_error = candidates[0]
        path_confidence = exp(-0.5 * (path_error / max(1.0, 7.0 * scale_y)) ** 2)
        radius_confidence = exp(
            -0.5 * (radius_error / max(1.0, 4.0 * radius_scale)) ** 2
        )
        ambiguity = 1.0 / (1.0 + 0.15 * (len(candidates) - 1))
        confidence = float(np.clip(path_confidence * radius_confidence * ambiguity, 0.0, 1.0))
        return BallDetection(
            detected=True,
            pixel_x=x,
            pixel_y=y,
            radius_px=radius,
            confidence=confidence,
            candidate_count=len(candidates),
        )

    def roi_bounds(self, frame_shape) -> tuple:
        height, width = frame_shape[:2]
        scale_y = height / self.config.reference_height
        top = max(0, int(round(self.config.roi_top * scale_y)))
        bottom = min(height, int(round(self.config.roi_bottom * scale_y)))
        return 0, top, width, bottom
