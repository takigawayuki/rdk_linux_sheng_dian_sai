#!/usr/bin/env python3
"""Run detector, short-occlusion tracker, and rod mapping on a recorded video."""

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from project.Algorithm.ball_detector import BallDetector
from project.Algorithm.ball_tracker import BallTracker
from project.Algorithm.rod_mapper import RodMapper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate the initial steel-ball vision pipeline on a video."
    )
    parser.add_argument("video", type=Path)
    parser.add_argument(
        "--calibration",
        type=Path,
        default=PROJECT_ROOT / "Driver" / "configs" / "rod_calibration.json",
    )
    parser.add_argument("--output-video", type=Path)
    parser.add_argument("--max-frames", type=int, default=0)
    return parser


def annotate(frame, detector, detection, track, position_cm, frame_index, fps):
    output = frame.copy()
    x1, y1, x2, y2 = detector.roi_bounds(frame.shape)
    cv2.rectangle(output, (x1, y1), (x2 - 1, y2 - 1), (40, 180, 240), 1)
    if track.valid and track.pixel_x is not None and track.pixel_y is not None:
        center = (int(round(track.pixel_x)), int(round(track.pixel_y)))
        radius = 13 if detection.radius_px is None else int(round(detection.radius_px))
        color = (40, 210, 80) if track.detected else (0, 180, 255)
        cv2.circle(output, center, radius, color, 2)
        cv2.drawMarker(output, center, color, cv2.MARKER_CROSS, 16, 2)
    status = "DETECTED" if track.detected else "PREDICTED" if track.predicted else "LOST"
    position_text = "--" if position_cm is None else f"{position_cm:+.2f} cm"
    lines = (
        f"frame {frame_index}  t={frame_index / fps:.3f}s",
        f"status {status}  confidence={track.confidence:.2f}",
        f"position {position_text}  vx={track.velocity_x_px_s:.1f}px/s",
    )
    for index, text in enumerate(lines):
        y = 28 + index * 24
        cv2.putText(output, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
        cv2.putText(output, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (80, 240, 120), 1)
    return output


def main() -> int:
    args = build_parser().parse_args()
    if args.max_frames < 0:
        raise SystemExit("--max-frames cannot be negative")
    if not args.video.is_file():
        raise SystemExit(f"video does not exist: {args.video}")

    mapper = RodMapper.load(args.calibration)
    detector = BallDetector()
    tracker = BallTracker()
    capture = cv2.VideoCapture(str(args.video))
    if not capture.isOpened():
        raise SystemExit(f"failed to open video: {args.video}")
    fps = capture.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 120.0

    writer = None
    raw_detected = predicted = lost = total = 0
    predicted_run = lost_run = max_predicted_run = max_lost_run = 0
    lost_run_start = None
    lost_runs = []
    positions = []
    confidences = []
    started = time.perf_counter()
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if args.max_frames and total >= args.max_frames:
                break
            timestamp = total / fps
            detection = detector.detect(frame, tracker.predicted_x(timestamp))
            track = tracker.update(detection, timestamp)
            if detection.detected:
                raw_detected += 1
            if track.predicted:
                predicted += 1
                predicted_run += 1
                max_predicted_run = max(max_predicted_run, predicted_run)
            else:
                predicted_run = 0
            if not track.valid:
                lost += 1
                if lost_run == 0:
                    lost_run_start = total
                lost_run += 1
                max_lost_run = max(max_lost_run, lost_run)
            else:
                if lost_run and lost_run_start is not None:
                    lost_runs.append((lost_run_start, total - 1))
                lost_run = 0
                lost_run_start = None

            position_cm = None
            if track.valid and track.pixel_x is not None:
                position_cm = mapper.map_pixel(track.pixel_x, clamp=True)
                positions.append(position_cm)
                confidences.append(track.confidence)

            if args.output_video is not None:
                annotated = annotate(
                    frame, detector, detection, track, position_cm, total, fps
                )
                if writer is None:
                    args.output_video.parent.mkdir(parents=True, exist_ok=True)
                    height, width = annotated.shape[:2]
                    suffix = args.output_video.suffix.lower()
                    codec = "MJPG" if suffix == ".avi" else "mp4v"
                    writer = cv2.VideoWriter(
                        str(args.output_video),
                        cv2.VideoWriter_fourcc(*codec),
                        fps,
                        (width, height),
                    )
                    if not writer.isOpened():
                        raise OSError(f"failed to create output video: {args.output_video}")
                writer.write(annotated)
            total += 1
    finally:
        capture.release()
        if writer is not None:
            writer.release()

    elapsed = time.perf_counter() - started
    if lost_run and lost_run_start is not None:
        lost_runs.append((lost_run_start, total - 1))
    valid = total - lost
    print(f"video: {args.video}")
    print(f"frames: {total}  source_fps: {fps:.3f}  duration: {total / fps:.3f}s")
    print(
        f"raw_detected: {raw_detected} ({raw_detected / max(1, total):.1%})  "
        f"predicted: {predicted} ({predicted / max(1, total):.1%})  "
        f"valid: {valid} ({valid / max(1, total):.1%})  lost: {lost}"
    )
    print(
        f"longest_prediction: {max_predicted_run} frames "
        f"({max_predicted_run / fps * 1000:.1f}ms)  "
        f"longest_lost: {max_lost_run} frames ({max_lost_run / fps * 1000:.1f}ms)"
    )
    notable_lost_runs = [run for run in lost_runs if run[1] - run[0] + 1 >= 3]
    if notable_lost_runs:
        formatted = ", ".join(
            f"{start}-{end} ({(end - start + 1) / fps * 1000:.1f}ms)"
            for start, end in notable_lost_runs
        )
        print(f"lost_runs_ge_3_frames: {formatted}")
    if positions:
        print(
            f"position_range: {min(positions):+.2f} .. {max(positions):+.2f} cm  "
            f"mean_confidence: {float(np.mean(confidences)):.3f}"
        )
    print(f"processing: {total / max(elapsed, 1e-9):.1f} fps ({elapsed:.2f}s)")
    if args.output_video is not None:
        print(f"annotated_video: {args.output_video}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
