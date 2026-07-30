#!/usr/bin/env python3
"""Print or send fixed vision packets for lower-controller integration tests."""

import argparse
from pathlib import Path
import sys
import time

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from project.Driver.my_serial import MySerial
from project.Driver.vision_protocol import VisionSerialFrame, VisionStatus, build_packet


STATUS_BY_NAME = {
    "lost": VisionStatus.LOST,
    "detected": VisionStatus.DETECTED,
    "predicted": VisionStatus.PREDICTED,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send a fixed 18-byte vision packet.")
    parser.add_argument("--serial-port", help="for example /dev/ttyS1")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--status", choices=STATUS_BY_NAME, default="lost")
    parser.add_argument("--error-cm", type=float, default=0.0)
    parser.add_argument("--position-cm", type=float, default=0.0)
    parser.add_argument("--velocity-cm-s", type=float, default=0.0)
    parser.add_argument("--sequence", type=int, default=0)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--rate", type=float, default=10.0, help="packets per second")
    parser.add_argument("--print-only", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.count <= 0 or args.rate <= 0:
        raise SystemExit("--count and --rate must be positive")
    if not args.print_only and not args.serial_port:
        raise SystemExit("--serial-port is required unless --print-only is used")
    frame = VisionSerialFrame(
        status=STATUS_BY_NAME[args.status],
        error_cm=args.error_cm,
        position_cm=args.position_cm,
        velocity_cm_s=args.velocity_cm_s,
        sequence=args.sequence & 0xFFFF,
    )
    packet = build_packet(frame)
    print(packet.hex(" ").upper())
    if args.print_only:
        return 0

    with MySerial(args.serial_port, args.baudrate) as serial_link:
        for index in range(args.count):
            current_frame = VisionSerialFrame(
                status=frame.status,
                error_cm=frame.error_cm,
                position_cm=frame.position_cm,
                velocity_cm_s=frame.velocity_cm_s,
                sequence=(frame.sequence + index) & 0xFFFF,
            )
            if not serial_link.send_vision_frame(current_frame):
                raise OSError("serial write failed or wrote an incomplete packet")
            if index + 1 < args.count:
                time.sleep(1.0 / args.rate)
    print(f"sent={args.count} port={args.serial_port} baudrate={args.baudrate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
