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
from project.Services.vision_pipeline import VisionPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send one 18-byte ball-state packet after every processed camera frame."
    )
    parser.add_argument("--serial-port", required=True, help="for example /dev/ttyS1")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--device", default="/dev/video0")
    parser.add_argument("--target-cm", type=float, default=0.0)
    parser.add_argument("--headless", action="store_true")
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
    value = "--" if measurement.error_cm is None else f"{measurement.error_cm:+.2f} cm"
    cv2.putText(
        output,
        f"serial {status}  error={value}  seq={measurement.sequence & 0xFFFF}",
        (12, 30),
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
    pipeline = VisionPipeline(args.calibration)
    camera_config = CameraConfig(device=args.device, width=640, height=480, fps=120.0)
    processed = sent = 0
    started = time.monotonic()
    last_log_at = started
    last_valid = None
    try:
        with Camera(camera_config) as camera, MySerial(
            args.serial_port, args.baudrate
        ) as serial_link:
            while True:
                packet = camera.capture_packet()
                result = pipeline.process(packet, args.target_cm)
                measurement = result.measurement
                ok = serial_link.send_vision_state(
                    position_cm=measurement.position_cm,
                    target_position_cm=measurement.target_position_cm,
                    velocity_cm_s=measurement.velocity_cm_s,
                    valid=measurement.valid,
                    predicted=measurement.predicted,
                    sequence=measurement.sequence,
                )
                processed += 1
                sent += int(ok)
                if not ok:
                    raise OSError("serial write failed or wrote an incomplete packet")
                now = time.monotonic()
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
                    rate = processed / max(now - started, 1e-9)
                    print(
                        f"TX seq={measurement.sequence & 0xFFFF:05d} "
                        f"status={status:<9} position={position:>8} "
                        f"error={error:>8} velocity={measurement.velocity_cm_s:+7.2f}cm/s "
                        f"confidence={measurement.confidence:.2f} "
                        f"sent={sent} rate={rate:.1f}Hz",
                        flush=True,
                    )
                    last_log_at = now
                last_valid = measurement.valid
                if not args.headless:
                    cv2.imshow("H Ball Vision Serial", annotate(packet.frame, result))
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                if args.max_frames and processed >= args.max_frames:
                    break
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
    elapsed = time.monotonic() - started
    print(
        f"processed={processed} sent={sent} elapsed={elapsed:.2f}s "
        f"rate={processed / max(elapsed, 1e-9):.1f}fps"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
