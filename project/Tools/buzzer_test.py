#!/usr/bin/env python3
"""Command-line test for the active-low GPIO16 buzzer."""

import argparse
from pathlib import Path
import sys
import time


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from project.Driver.buzzer import Buzzer, BuzzerConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Beep an active-low GPIO buzzer.")
    parser.add_argument("--pin", type=int, default=16, help="GPIO number, default BCM 16")
    parser.add_argument("--numbering", choices=("BCM", "BOARD"), default="BCM")
    parser.add_argument("--duration", type=float, default=0.2, help="seconds per beep")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--gap", type=float, default=0.15, help="seconds between beeps")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.duration <= 0:
        raise SystemExit("--duration must be positive")
    if args.count <= 0:
        raise SystemExit("--count must be positive")
    if args.gap < 0:
        raise SystemExit("--gap cannot be negative")

    config = BuzzerConfig(pin=args.pin, numbering=args.numbering, active_low=True)
    print(
        f"buzzer pin={args.numbering}{args.pin} active=LOW inactive=HIGH "
        f"duration={args.duration:g}s count={args.count}",
        flush=True,
    )
    try:
        with Buzzer(config) as buzzer:
            for index in range(args.count):
                buzzer.beep(args.duration)
                if index + 1 < args.count:
                    time.sleep(args.gap)
    except RuntimeError as error:
        raise SystemExit(f"buzzer error: {error}") from error
    print("buzzer test complete; GPIO restored HIGH", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
