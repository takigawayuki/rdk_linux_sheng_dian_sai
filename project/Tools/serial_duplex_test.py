#!/usr/bin/env python3
"""Bidirectional USB-TTL test for use with a PC serial assistant."""

import argparse
from pathlib import Path
import sys
import time

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from project.Driver.my_serial import MySerial
from project.Driver.vision_protocol import VisionSerialFrame, VisionStatus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test two-way serial traffic with a PC serial assistant."
    )
    parser.add_argument("--serial-port", required=True)
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--mode", choices=("echo", "packet"), default="echo")
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--duration", type=float, default=0.0, help="0 runs until Ctrl+C")
    return parser


def printable(data: bytes) -> str:
    return "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in data)


def main() -> int:
    args = build_parser().parse_args()
    if args.interval <= 0 or args.duration < 0:
        raise SystemExit("--interval must be positive and --duration cannot be negative")

    started = time.monotonic()
    next_packet_at = started
    sequence = 0
    try:
        with MySerial(args.serial_port, args.baudrate, timeout=0.0) as link:
            print(f"mode={args.mode} port={args.serial_port} baudrate={args.baudrate}")
            if args.mode == "echo":
                link.send_data(b"RDK_READY\r\n")
                print("TX ASCII: RDK_READY")
            while args.duration == 0 or time.monotonic() - started < args.duration:
                now = time.monotonic()
                if args.mode == "packet" and now >= next_packet_at:
                    frame = VisionSerialFrame(
                        status=VisionStatus.DETECTED,
                        error_cm=-2.0,
                        position_cm=3.0,
                        velocity_cm_s=-2.0,
                        sequence=sequence,
                    )
                    if not link.send_vision_frame(frame):
                        raise OSError("serial packet write failed")
                    sequence = (sequence + 1) & 0xFFFF
                    next_packet_at = now + args.interval

                received = link.receive_available()
                if received:
                    print(f"RX HEX: {received.hex(' ').upper()}")
                    print(f"RX TXT: {printable(received)}")
                    if args.mode == "echo":
                        if not link.send_data(received):
                            raise OSError("serial echo write failed")
                        print(f"TX ECHO: {received.hex(' ').upper()}")
                    elif b"PING" in received.upper():
                        if not link.send_data(b"PONG\r\n"):
                            raise OSError("serial PONG write failed")
                        print("TX ASCII: PONG")
                time.sleep(0.002)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
