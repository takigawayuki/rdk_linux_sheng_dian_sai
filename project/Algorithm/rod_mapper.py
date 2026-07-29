"""Map undistorted ball pixel positions to centimeters along the rod."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence, Tuple

import numpy as np


@dataclass(frozen=True)
class MappingStats:
    rmse_cm: float
    max_error_cm: float
    errors_cm: Tuple[float, ...]


class RodMapper:
    """Initial one-dimensional linear pixel-to-centimeter mapping."""

    VERSION = 1

    def __init__(
        self,
        slope_cm_per_px: float,
        intercept_cm: float,
        min_cm: float = -12.5,
        max_cm: float = 12.5,
    ):
        if not np.isfinite(slope_cm_per_px) or abs(slope_cm_per_px) < 1e-12:
            raise ValueError("mapping slope must be finite and non-zero")
        if not np.isfinite(intercept_cm):
            raise ValueError("mapping intercept must be finite")
        if min_cm >= max_cm:
            raise ValueError("mapping range must be increasing")
        self.slope_cm_per_px = float(slope_cm_per_px)
        self.intercept_cm = float(intercept_cm)
        self.min_cm = float(min_cm)
        self.max_cm = float(max_cm)

    def map_pixel(self, pixel_x: float, clamp: bool = False) -> float:
        position = self.slope_cm_per_px * float(pixel_x) + self.intercept_cm
        if clamp:
            return min(self.max_cm, max(self.min_cm, position))
        return position

    @classmethod
    def fit(cls, samples: Iterable[Tuple[float, float]]) -> "RodMapper":
        points = [(float(pixel_x), float(position_cm)) for pixel_x, position_cm in samples]
        if len(points) < 2:
            raise ValueError("at least two mapping samples are required")
        pixels = np.asarray([point[0] for point in points], dtype=np.float64)
        positions = np.asarray([point[1] for point in points], dtype=np.float64)
        if np.unique(pixels).size < 2:
            raise ValueError("mapping samples need at least two distinct pixel positions")
        design = np.column_stack((pixels, np.ones_like(pixels)))
        slope, intercept = np.linalg.lstsq(design, positions, rcond=None)[0]
        return cls(float(slope), float(intercept))

    def evaluate(self, samples: Iterable[Tuple[float, float]]) -> MappingStats:
        points = list(samples)
        if not points:
            raise ValueError("cannot evaluate an empty sample set")
        errors = tuple(self.map_pixel(pixel_x) - position_cm for pixel_x, position_cm in points)
        error_array = np.asarray(errors, dtype=np.float64)
        return MappingStats(
            rmse_cm=float(np.sqrt(np.mean(error_array**2))),
            max_error_cm=float(np.max(np.abs(error_array))),
            errors_cm=errors,
        )

    def to_dict(self, calibration_points: Sequence[dict] = ()) -> dict:
        return {
            "version": self.VERSION,
            "model": "linear_1d",
            "input_coordinate": "undistorted_pixel_x",
            "output_coordinate": "position_cm_relative_to_O",
            "slope_cm_per_px": self.slope_cm_per_px,
            "intercept_cm": self.intercept_cm,
            "valid_range_cm": [self.min_cm, self.max_cm],
            "calibration_points": list(calibration_points),
        }

    def save(
        self,
        path: Path,
        calibration_points: Sequence[dict] = (),
        metadata: dict = None,
    ) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict(calibration_points)
        if metadata:
            data["metadata"] = metadata
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "RodMapper":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("model") != "linear_1d":
            raise ValueError(f"unsupported rod mapping model: {data.get('model')}")
        valid_range = data.get("valid_range_cm", [-12.5, 12.5])
        return cls(
            data["slope_cm_per_px"],
            data["intercept_cm"],
            valid_range[0],
            valid_range[1],
        )
