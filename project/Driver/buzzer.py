"""Active-low GPIO buzzer driver for D-Robotics RDK boards."""

from dataclasses import dataclass
import threading
import time
from typing import Any, Optional


@dataclass(frozen=True)
class BuzzerConfig:
    """GPIO16 uses BCM 16, which is physical header pin 36 on this board."""

    pin: int = 16
    numbering: str = "BCM"
    active_low: bool = True

    def validate(self) -> None:
        if self.pin < 0:
            raise ValueError("buzzer pin must be non-negative")
        if self.numbering not in ("BCM", "BOARD"):
            raise ValueError("buzzer numbering must be BCM or BOARD")


class Buzzer:
    """Control a digital buzzer and always restore its inactive level on exit."""

    def __init__(
        self,
        config: Optional[BuzzerConfig] = None,
        gpio_module: Optional[Any] = None,
    ):
        self.config = config or BuzzerConfig()
        self.config.validate()
        self._gpio = gpio_module
        self._opened = False
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        return self._opened

    @property
    def active_level(self) -> int:
        return self._gpio.LOW if self.config.active_low else self._gpio.HIGH

    @property
    def inactive_level(self) -> int:
        return self._gpio.HIGH if self.config.active_low else self._gpio.LOW

    def open(self) -> "Buzzer":
        if self._opened:
            return self
        if self._gpio is None:
            try:
                import Hobot.GPIO as gpio
            except (ImportError, RuntimeError) as error:
                raise RuntimeError(
                    "cannot initialize Hobot.GPIO; run as root and check GPIO permissions"
                ) from error
            self._gpio = gpio

        mode = getattr(self._gpio, self.config.numbering, None)
        if mode is None:
            raise RuntimeError(
                f"Hobot.GPIO does not support {self.config.numbering} numbering"
            )
        self._gpio.setwarnings(False)
        self._gpio.setmode(mode)
        self._gpio.setup(
            self.config.pin,
            self._gpio.OUT,
            initial=self.inactive_level,
        )
        self._opened = True
        self.off()
        return self

    def on(self) -> None:
        self._write(self.active_level)

    def off(self) -> None:
        self._write(self.inactive_level)

    def beep(self, duration_seconds: float = 0.2) -> None:
        if duration_seconds <= 0:
            raise ValueError("beep duration must be positive")
        self.on()
        try:
            time.sleep(duration_seconds)
        finally:
            self.off()

    def close(self) -> None:
        if not self._opened or self._gpio is None:
            return
        with self._lock:
            try:
                self._gpio.output(self.config.pin, self.inactive_level)
            finally:
                try:
                    self._gpio.cleanup(self.config.pin)
                finally:
                    self._opened = False

    def _write(self, level: int) -> None:
        if not self._opened or self._gpio is None:
            raise RuntimeError("buzzer is not open")
        with self._lock:
            self._gpio.output(self.config.pin, level)

    def __enter__(self) -> "Buzzer":
        return self.open()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
