from pathlib import Path

import cv2
import numpy as np


class Undistorter:
    """Apply cached lens-distortion correction from a calibration NPZ file."""

    def __init__(self, calibration_file: Path, alpha: float = 0.0):
        calibration_file = Path(calibration_file)
        if not calibration_file.is_file():
            raise FileNotFoundError(f"calibration file not found: {calibration_file}")
        if not 0.0 <= alpha <= 1.0:
            raise ValueError("undistort alpha must be between 0 and 1")

        with np.load(calibration_file, allow_pickle=False) as data:
            self.camera_matrix = data["camera_matrix"].astype(np.float64)
            self.dist_coeffs = data["dist_coeffs"].astype(np.float64)
            self.calibration_size = tuple(int(value) for value in data["image_size"])

        self.calibration_file = calibration_file
        self.alpha = alpha
        self._cached_size = None
        self._map_x = None
        self._map_y = None

    def apply(self, frame):
        height, width = frame.shape[:2]
        frame_size = (width, height)
        if self._cached_size != frame_size:
            self._build_maps(frame_size)
        return cv2.remap(
            frame,
            self._map_x,
            self._map_y,
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
        )

    def _build_maps(self, frame_size) -> None:
        calibration_width, calibration_height = self.calibration_size
        frame_width, frame_height = frame_size
        calibration_ratio = calibration_width / calibration_height
        frame_ratio = frame_width / frame_height
        if abs(calibration_ratio - frame_ratio) > 0.01:
            raise ValueError(
                "current frame aspect ratio differs from calibration: "
                f"{frame_width}x{frame_height} vs "
                f"{calibration_width}x{calibration_height}"
            )

        scaled_matrix = self.camera_matrix.copy()
        scaled_matrix[0, :] *= frame_width / calibration_width
        scaled_matrix[1, :] *= frame_height / calibration_height
        new_matrix, _ = cv2.getOptimalNewCameraMatrix(
            scaled_matrix,
            self.dist_coeffs,
            frame_size,
            self.alpha,
            frame_size,
        )
        self._map_x, self._map_y = cv2.initUndistortRectifyMap(
            scaled_matrix,
            self.dist_coeffs,
            None,
            new_matrix,
            frame_size,
            cv2.CV_16SC2,
        )
        self._cached_size = frame_size

    def describe(self) -> dict:
        return {
            "enabled": True,
            "calibration_file": str(self.calibration_file),
            "calibration_width": self.calibration_size[0],
            "calibration_height": self.calibration_size[1],
            "alpha": self.alpha,
        }
