#!/usr/bin/env python3
"""Run the live camera-to-vision-to-serial path."""

import argparse
from pathlib import Path
import sys
import time

import cv2

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from project.Core.models import CameraConfig
from project.Driver.camera import Camera
from project.Driver.my_serial import MySerial
from project.Services.latest_frame_capture import LatestFrameCapture
from project.Services.vision_pipeline import BALL_VISION_DIRECTION, VisionPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send one 18-byte ball-state packet after every processed camera frame."
    )
    parser.add_argument("--serial-port", required=True, help="for example /dev/ttyS1")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--device", default="/dev/video0")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=float, default=120.0)
    parser.add_argument("--fourcc", default="MJPG")
    parser.add_argument("--buffer-size", type=int, default=3)
    parser.add_argument("--no-undistort", action="store_true")
    parser.add_argument("--auto-exposure", type=float)
    parser.add_argument("--exposure", type=float)
    parser.add_argument("--gain", type=float)
    parser.add_argument("--target-cm", type=float, default=0.0)
    parser.add_argument(
        "--position-direction",
        type=float,
        choices=(-1.0, 1.0),
        default=BALL_VISION_DIRECTION,
        help="control-coordinate direction applied to mapped position and velocity",
    )
    parser.add_argument(
        "--position-scale",
        type=float,
        default=1.0,
        help="positive scale applied after pixel-to-centimetre calibration",
    )
    parser.add_argument(
        "--lookahead-ms",
        type=float,
        default=0.0,
        help="constant-velocity control lookahead in milliseconds (0 to 200)",
    )
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--preview-fps",
        type=float,
        default=30.0,
        help="preview refresh rate; vision and serial continue at their maximum rate",
    )
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument(
        "--log-interval",
        type=float,
        default=0.5,
        help="seconds between TX summaries; 0 disables periodic logs",
    )
    parser.add_argument(
        "--calibration",
        type=Path,
        default=PROJECT_ROOT / "Driver" / "configs" / "rod_calibration.json",
    )
    return parser


def annotate(frame, result):
    output = frame.copy()
    measurement = result.measurement
    if result.track.valid and result.track.pixel_x is not None:
        center = (
            int(round(result.track.pixel_x)),
            int(round(result.track.pixel_y)),
        )
        color = (40, 210, 80) if result.track.detected else (0, 180, 255)
        cv2.circle(output, center, 13, color, 2)
    status = "DETECTED" if measurement.detected else "PREDICTED" if measurement.predicted else "LOST"
    position = "--" if measurement.position_cm is None else f"{measurement.position_cm:+.2f}"
    control = (
        "--"
        if measurement.control_position_cm is None
        else f"{measurement.control_position_cm:+.2f}"
    )
    error = "--" if measurement.error_cm is None else f"{measurement.error_cm:+.2f}"
    cv2.putText(
        output,
        f"serial {status}  seq={measurement.sequence & 0xFFFF}",
        (12, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (40, 220, 80),
        2,
    )
    cv2.putText(
        output,
        f"x={position}  control={control}  error={error} cm",
        (12, 55),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (40, 220, 80),
        2,
    )
    return output


def main() -> int:
    args = build_parser().parse_args()
    if args.max_frames < 0:
        raise SystemExit("--max-frames cannot be negative")
    if args.log_interval < 0:
        raise SystemExit("--log-interval cannot be negative")
    if args.preview_fps <= 0:
        raise SystemExit("--preview-fps must be positive; use --headless to disable it")
    if args.position_scale <= 0:
        raise SystemExit("--position-scale must be positive")
    if not 0.0 <= args.lookahead_ms <= 200.0:
        raise SystemExit("--lookahead-ms must be between 0 and 200")
    if args.width <= 0 or args.height <= 0 or args.fps <= 0:
        raise SystemExit("camera width, height and FPS must be positive")
    if len(args.fourcc) != 4:
        raise SystemExit("--fourcc must contain exactly four characters")
    if args.buffer_size <= 0:
        raise SystemExit("--buffer-size must be positive")
    pipeline = VisionPipeline(
        args.calibration,
        position_direction=args.position_direction,
        position_scale=args.position_scale,
        control_lookahead_seconds=args.lookahead_ms / 1000.0,
    )
    camera_config = CameraConfig(
        device=args.device,
        width=args.width,
        height=args.height,
        fps=args.fps,
        fourcc=args.fourcc,
        buffer_size=args.buffer_size,
        undistort=not args.no_undistort,
        auto_exposure=args.auto_exposure,
        exposure=args.exposure,
        gain=args.gain,
    )
    processed = sent = 0
    started = time.monotonic()
    last_log_at = started
    last_log_processed = 0
    last_log_captured = 0
    last_preview_at = 0.0
    last_valid = None
    timing_samples = 0
    wait_seconds = read_seconds = preprocess_seconds = 0.0
    vision_seconds = serial_seconds = ui_seconds = 0.0
    skipped_frames = 0
    last_sequence = -1
    try:
        with Camera(camera_config) as camera, MySerial(
            args.serial_port, args.baudrate
        ) as serial_link:
            actual = camera.actual_settings()
            print(
                f"camera device={actual['device']} "
                f"mode={actual['width']}x{actual['height']} "
                f"fourcc={actual['fourcc']} fps={actual['fps']:.2f} "
                f"undistorted={actual['undistortion'].get('enabled', False)}",
                flush=True,
            )
            if args.no_undistort:
                print(
                    "camera warning: undistortion disabled for timing diagnostics; "
                    "mapped centimetre positions are not valid for control",
                    flush=True,
                )
            print(
                f"coordinates calibration-label direction={args.position_direction:+.0f} "
                f"scale={args.position_scale:g} lookahead={args.lookahead_ms:g}ms "
                f"error=target-control_position",
                flush=True,
            )
            for warning in camera.mode_warnings():
                print(f"camera warning: {warning}", flush=True)
            capture = LatestFrameCapture(camera).start()
            try:
                while True:
                    loop_started = time.monotonic()
                    packet = capture.wait_for_frame(last_sequence, timeout=1.0)
                    capture_finished = time.monotonic()
                    if last_sequence >= 0:
                        skipped_frames += max(0, packet.sequence - last_sequence - 1)
                    last_sequence = packet.sequence
                    result = pipeline.process(packet, args.target_cm)
                    vision_finished = time.monotonic()
                    measurement = result.measurement
                    ok = serial_link.send_vision_state(
                        position_cm=measurement.control_position_cm,
                        target_position_cm=measurement.target_position_cm,
                        velocity_cm_s=measurement.velocity_cm_s,
                        valid=measurement.valid,
                        predicted=measurement.predicted,
                        sequence=measurement.sequence,
                    )
                    serial_finished = time.monotonic()
                    processed += 1
                    sent += int(ok)
                    if not ok:
                        raise OSError("serial write failed or wrote an incomplete packet")
                    quit_requested = False
                    if not args.headless:
                        preview_now = time.monotonic()
                        if preview_now - last_preview_at >= 1.0 / args.preview_fps:
                            cv2.imshow("H Ball Vision Serial", annotate(packet.frame, result))
                            last_preview_at = preview_now
                        quit_requested = cv2.waitKey(1) & 0xFF == ord("q")
                    now = time.monotonic()
                    timing_samples += 1
                    wait_seconds += capture_finished - loop_started
                    read_seconds += packet.read_seconds
                    preprocess_seconds += packet.preprocess_seconds
                    vision_seconds += vision_finished - capture_finished
                    serial_seconds += serial_finished - vision_finished
                    ui_seconds += now - serial_finished
                    validity_changed = last_valid is not None and measurement.valid != last_valid
                    periodic_log = (
                        args.log_interval > 0 and now - last_log_at >= args.log_interval
                    )
                    if last_valid is None or validity_changed or periodic_log:
                        status = (
                            "DETECTED"
                            if measurement.detected
                            else "PREDICTED"
                            if measurement.predicted
                            else "LOST"
                        )
                        position = (
                            "--" if measurement.position_cm is None else f"{measurement.position_cm:+.2f}cm"
                        )
                        error = (
                            "--" if measurement.error_cm is None else f"{measurement.error_cm:+.2f}cm"
                        )
                        control_position = (
                            "--"
                            if measurement.control_position_cm is None
                            else f"{measurement.control_position_cm:+.2f}cm"
                        )
                        window_seconds = max(now - last_log_at, 1e-9)
                        capture_count = capture.captured_count
                        tx_fps = (processed - last_log_processed) / window_seconds
                        camera_fps = (capture_count - last_log_captured) / window_seconds
                        average_fps = processed / max(now - started, 1e-9)
                        timing_divisor = max(1, timing_samples)
                        print(
                            f"TX seq={measurement.sequence & 0xFFFF:05d} "
                            f"status={status:<9} position={position:>8} "
                            f"control={control_position:>8} "
                            f"error={error:>8} velocity={measurement.velocity_cm_s:+7.2f}cm/s "
                            f"confidence={measurement.confidence:.2f} "
                            f"sent={sent} tx_fps={tx_fps:.1f} camera_fps={camera_fps:.1f} "
                            f"avg={average_fps:.1f} skipped={skipped_frames} "
                            f"preprocess_dropped={capture.preprocess_skipped_count} "
                            f"ms[wait={wait_seconds / timing_divisor * 1000:.1f} "
                            f"read={read_seconds / timing_divisor * 1000:.1f} "
                            f"undistort={preprocess_seconds / timing_divisor * 1000:.1f} "
                            f"vision={vision_seconds / timing_divisor * 1000:.1f} "
                            f"serial={serial_seconds / timing_divisor * 1000:.1f} "
                            f"ui={ui_seconds / timing_divisor * 1000:.1f}]",
                            flush=True,
                        )
                        last_log_processed = processed
                        last_log_captured = capture_count
                        last_log_at = now
                        timing_samples = 0
                        wait_seconds = read_seconds = preprocess_seconds = 0.0
                        vision_seconds = serial_seconds = ui_seconds = 0.0
                    last_valid = measurement.valid
                    if quit_requested:
                        break
                    if args.max_frames and processed >= args.max_frames:
                        break
            finally:
                capture.stop()
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
    elapsed = time.monotonic() - started
    print(
        f"processed={processed} sent={sent} elapsed={elapsed:.2f}s "
        f"average_tx_fps={processed / max(elapsed, 1e-9):.1f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
