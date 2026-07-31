#!/usr/bin/env python3
"""Collect position-labelled rod and ball images, undistorted by default."""

import argparse
import json
import sys
import time
from pathlib import Path

import cv2

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from project.Core.models import CameraConfig, FramePacket
from project.Driver.camera import Camera, CameraError
from project.Services.sample_storage import SampleSession


WINDOW_NAME = "H problem sample collector"


def parse_device(value: str):
    return int(value) if value.isdecimal() else value


def optional_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False
    raise argparse.ArgumentTypeError("expected true/false")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect undistorted images with a known ball position. In interactive mode, "
            "press s to save and q to quit."
        )
    )
    parser.add_argument("--device", default="0", help="camera index or /dev/videoX")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=float, default=120.0)
    parser.add_argument("--fourcc", default="MJPG")
    parser.add_argument("--buffer-size", type=int, default=3)
    parser.add_argument("--rotation", type=int, choices=(0, 90, 180, 270), default=0)
    parser.add_argument(
        "--no-undistort",
        action="store_true",
        help="disable the default calibration correction (use for new checkerboard data)",
    )
    parser.add_argument(
        "--calibration-file",
        type=Path,
        help="calibration NPZ; defaults to Driver/calibration/camera_calibration.npz",
    )
    parser.add_argument("--undistort-alpha", type=float, default=0.0)
    parser.add_argument("--auto-exposure", type=float)
    parser.add_argument("--exposure", type=float)
    parser.add_argument("--gain", type=float)
    parser.add_argument("--auto-white-balance", type=optional_bool)
    parser.add_argument("--white-balance-temperature", type=float)
    parser.add_argument("--autofocus", type=optional_bool)
    parser.add_argument("--focus", type=float)
    parser.add_argument(
        "--label",
        required=True,
        help="sample label, for example empty, center, static_ball or rolling_ball",
    )
    parser.add_argument(
        "--position-cm",
        type=float,
        help="known ball position relative to O; omit for empty/rolling samples",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "Data" / "samples",
    )
    parser.add_argument("--jpeg-quality", type=int, default=95)
    parser.add_argument("--warmup-seconds", type=float, default=1.0)
    parser.add_argument(
        "--headless",
        action="store_true",
        help="save automatically without opening an OpenCV window",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="number of snapshots; 0 means unlimited in interactive mode",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="automatic snapshot interval in headless mode",
    )
    parser.add_argument(
        "--record-video",
        action="store_true",
        help="also record every output frame to video.avi",
    )
    return parser


def validate_args(parser: argparse.ArgumentParser, args) -> None:
    if args.headless and args.count <= 0:
        parser.error("--headless requires --count greater than zero")
    if args.count < 0:
        parser.error("--count cannot be negative")
    if args.interval <= 0:
        parser.error("--interval must be positive")
    if not 1 <= args.jpeg_quality <= 100:
        parser.error("--jpeg-quality must be between 1 and 100")
    if args.warmup_seconds < 0:
        parser.error("--warmup-seconds cannot be negative")


def build_camera_config(args) -> CameraConfig:
    return CameraConfig(
        device=parse_device(args.device),
        width=args.width,
        height=args.height,
        fps=args.fps,
        fourcc=args.fourcc,
        buffer_size=args.buffer_size,
        rotation=args.rotation,
        undistort=not args.no_undistort,
        calibration_file=(
            None if args.calibration_file is None else str(args.calibration_file)
        ),
        undistort_alpha=args.undistort_alpha,
        auto_exposure=args.auto_exposure,
        exposure=args.exposure,
        gain=args.gain,
        auto_white_balance=args.auto_white_balance,
        white_balance_temperature=args.white_balance_temperature,
        autofocus=args.autofocus,
        focus=args.focus,
    )


def make_preview(
    packet: FramePacket,
    label: str,
    position_cm,
    saved: int,
    fps: float,
    undistorted: bool,
):
    preview = packet.frame.copy()
    position_text = "unknown" if position_cm is None else f"{position_cm:+.2f} cm"
    lines = (
        f"label: {label}",
        f"position: {position_text}",
        f"saved: {saved}  seq: {packet.sequence}  fps: {fps:.1f}",
        f"undistorted: {'YES' if undistorted else 'NO'}",
        "s: save    q: quit",
    )
    for index, line in enumerate(lines):
        y = 28 + index * 27
        cv2.putText(
            preview, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 3
        )
        cv2.putText(
            preview,
            line,
            (12, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 255),
            1,
        )
    return preview


def collect(args) -> Path:
    config = build_camera_config(args)
    session = SampleSession(
        output_root=args.output_root,
        label=args.label,
        position_cm=args.position_cm,
        jpeg_quality=args.jpeg_quality,
    )

    with Camera(config) as camera, session:
        actual = camera.actual_settings()
        warnings = camera.mode_warnings()
        session_path = session.start(config, actual, warnings)

        print("Session:", session_path)
        print("Camera:", json.dumps(actual, ensure_ascii=False))
        for warning in warnings:
            print("WARNING:", warning)

        warmup_deadline = time.monotonic() + args.warmup_seconds
        while time.monotonic() < warmup_deadline:
            camera.capture_packet()

        last_auto_save = float("-inf")
        fps = 0.0
        fps_count = 0
        fps_started = time.monotonic()

        try:
            while True:
                packet = camera.capture_packet()
                fps_count += 1
                now = time.monotonic()
                elapsed = now - fps_started
                if elapsed >= 1.0:
                    fps = fps_count / elapsed
                    fps_count = 0
                    fps_started = now

                if args.record_video:
                    writer_fps = actual["fps"] if actual["fps"] > 0 else args.fps
                    session.write_video_frame(packet.frame, writer_fps)

                should_save = args.headless and now - last_auto_save >= args.interval
                key = -1
                if not args.headless:
                    cv2.imshow(
                        WINDOW_NAME,
                        make_preview(
                            packet,
                            args.label,
                            args.position_cm,
                            session.saved_images,
                            fps,
                            bool(actual["undistortion"]["enabled"]),
                        ),
                    )
                    key = cv2.waitKey(1) & 0xFF
                    should_save = key == ord("s")

                if should_save:
                    image_path = session.save_snapshot(packet)
                    last_auto_save = now
                    print(f"Saved {image_path.name} ({session.saved_images})")

                if key == ord("q"):
                    break
                if args.count > 0 and session.saved_images >= args.count:
                    break
        finally:
            if not args.headless:
                cv2.destroyAllWindows()

    print(
        f"Finished: {session.saved_images} labelled image(s) in {session_path}"
    )
    return session_path


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(parser, args)
    try:
        collect(args)
    except (CameraError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
