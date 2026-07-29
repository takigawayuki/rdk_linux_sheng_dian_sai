#!/usr/bin/env python3
"""Fit the initial linear rod mapping from labelled static-ball sessions."""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from project.Algorithm.ball_detector import BallDetector
from project.Algorithm.rod_mapper import RodMapper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect labelled static balls and fit pixel_x to position_cm."
    )
    parser.add_argument(
        "--samples-root",
        type=Path,
        default=PROJECT_ROOT / "Data" / "samples",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "Driver" / "configs" / "rod_calibration.json",
    )
    parser.add_argument("--minimum-images", type=int, default=10)
    return parser


def load_sessions(samples_root: Path, detector: BallDetector, minimum_images: int):
    sessions = []
    calibration_files = set()
    dimensions = set()
    for metadata_path in sorted(samples_root.glob("*/session.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("label") != "static_ball" or metadata.get("position_cm") is None:
            continue
        if not metadata.get("images_are_undistorted", False):
            raise ValueError(f"static samples are not undistorted: {metadata_path.parent}")
        image_paths = sorted(metadata_path.parent.glob("frame_*.jpg"))
        if len(image_paths) < minimum_images:
            raise ValueError(
                f"{metadata_path.parent} has {len(image_paths)} images; "
                f"need at least {minimum_images}"
            )

        detections = []
        for image_path in image_paths:
            frame = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if frame is None:
                raise OSError(f"failed to read image: {image_path}")
            detection = detector.detect(frame)
            if detection.detected:
                detections.append(detection)
        if len(detections) < minimum_images:
            raise RuntimeError(
                f"only detected {len(detections)}/{len(image_paths)} images in "
                f"{metadata_path.parent}"
            )

        pixel_values = np.asarray([item.pixel_x for item in detections], dtype=np.float64)
        confidences = np.asarray([item.confidence for item in detections], dtype=np.float64)
        actual = metadata.get("actual_camera", {})
        dimensions.add((actual.get("width"), actual.get("height")))
        calibration_files.add(
            actual.get("undistortion", {}).get("calibration_file")
        )
        sessions.append(
            {
                "session": metadata_path.parent.name,
                "position_cm": float(metadata["position_cm"]),
                "pixel_x": float(np.median(pixel_values)),
                "pixel_x_std": float(np.std(pixel_values)),
                "mean_confidence": float(np.mean(confidences)),
                "detected_images": len(detections),
                "total_images": len(image_paths),
            }
        )

    if len(sessions) < 3:
        raise ValueError("at least three labelled static-ball sessions are required")
    if len(dimensions) != 1:
        raise ValueError(f"sample image dimensions are inconsistent: {dimensions}")
    if len(calibration_files) != 1:
        raise ValueError("samples use different camera calibration files")
    sessions.sort(key=lambda item: item["position_cm"])
    return sessions, dimensions.pop(), calibration_files.pop()


def main() -> int:
    args = build_parser().parse_args()
    if args.minimum_images <= 0:
        raise SystemExit("--minimum-images must be positive")

    detector = BallDetector()
    sessions, dimensions, camera_calibration = load_sessions(
        args.samples_root, detector, args.minimum_images
    )
    fit_samples = [(item["pixel_x"], item["position_cm"]) for item in sessions]
    mapper = RodMapper.fit(fit_samples)
    stats = mapper.evaluate(fit_samples)

    for item, error in zip(sessions, stats.errors_cm):
        item["fit_error_cm"] = error
        print(
            f"{item['position_cm']:+6.1f} cm  "
            f"u={item['pixel_x']:7.2f} px  "
            f"jitter={item['pixel_x_std']:.2f} px  "
            f"det={item['detected_images']:2d}/{item['total_images']:2d}  "
            f"error={error:+.3f} cm"
        )

    mapper.save(
        args.output,
        sessions,
        metadata={
            "image_width": dimensions[0],
            "image_height": dimensions[1],
            "images_are_undistorted": True,
            "camera_calibration_file": camera_calibration,
            "rmse_cm": stats.rmse_cm,
            "max_error_cm": stats.max_error_cm,
            "calibrated_range_cm": [
                sessions[0]["position_cm"],
                sessions[-1]["position_cm"],
            ],
        },
    )
    print(f"model: x_cm = {mapper.slope_cm_per_px:.9f} * u + {mapper.intercept_cm:.6f}")
    print(f"RMSE: {stats.rmse_cm:.4f} cm  max: {stats.max_error_cm:.4f} cm")
    print(f"saved: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
