"""Serial transport for the fixed vision-to-motor packet."""

import threading
from typing import Optional

import serial

from project.Driver.vision_protocol import (
    VisionSerialFrame,
    VisionStatus,
    build_packet,
)


class MySerial:
    def __init__(
        self,
        port,
        baudrate=115200,
        timeout=0.0,
        write_timeout=0.05,
        serial_factory=serial.Serial,
    ):
        self.port = port
        self.baudrate = int(baudrate)
        self.timeout = timeout
        self.write_timeout = write_timeout
        self._serial_factory = serial_factory
        self.ser = None
        self.is_open = False
        self._sequence = 0
        self._write_lock = threading.Lock()

    def open(self):
        try:
            self.ser = self._serial_factory(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=self.write_timeout,
            )
            self.is_open = bool(getattr(self.ser, "is_open", True))
            if not self.is_open:
                raise OSError(f"serial port did not open: {self.port}")
            print(f"串口 {self.port} 打开成功")
            return True
        except (OSError, serial.SerialException, ValueError) as error:
            print(f"串口打开失败: {error}")
            self.ser = None
            self.is_open = False
            return False

    def send_data(self, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("serial data must be bytes-like or str")
        if not self.is_open or self.ser is None:
            return False
        raw = bytes(data)
        try:
            with self._write_lock:
                written = self.ser.write(raw)
            return written is None or written == len(raw)
        except (OSError, serial.SerialException):
            return False

    def send_vision_frame(self, frame: VisionSerialFrame) -> bool:
        return self.send_data(build_packet(frame))

    def read(self, size=1) -> bytes:
        if not self.is_open or self.ser is None:
            return b""
        try:
            return bytes(self.ser.read(size))
        except (OSError, serial.SerialException):
            return b""

    def receive_available(self, max_bytes=4096) -> bytes:
        """Read currently buffered bytes without waiting for a complete protocol frame."""
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if not self.is_open or self.ser is None:
            return b""
        try:
            available = int(getattr(self.ser, "in_waiting", 0))
            if available <= 0:
                return b""
            return bytes(self.ser.read(min(available, max_bytes)))
        except (OSError, serial.SerialException):
            return b""

    def send_vision_state(
        self,
        position_cm: Optional[float],
        target_position_cm: float = 0.0,
        velocity_cm_s: float = 0.0,
        valid: bool = True,
        predicted: bool = False,
        sequence: Optional[int] = None,
    ) -> bool:
        """Send one measurement; error_cm is target minus measured position."""
        if sequence is None:
            sequence = self._sequence
            self._sequence = (self._sequence + 1) & 0xFFFF
        else:
            sequence = int(sequence) & 0xFFFF

        if not valid or position_cm is None:
            frame = VisionSerialFrame(
                status=VisionStatus.LOST,
                error_cm=0.0,
                position_cm=0.0,
                velocity_cm_s=0.0,
                sequence=sequence,
            )
        else:
            position_cm = float(position_cm)
            frame = VisionSerialFrame(
                status=VisionStatus.PREDICTED if predicted else VisionStatus.DETECTED,
                error_cm=float(target_position_cm) - position_cm,
                position_cm=position_cm,
                velocity_cm_s=float(velocity_cm_s),
                sequence=sequence,
            )
        return self.send_vision_frame(frame)

    def send_deta(self, deta_x, deta_y=0.0):
        """Compatibility wrapper: send deta_x as error_cm in a detected frame."""
        frame = VisionSerialFrame(
            status=VisionStatus.DETECTED,
            error_cm=float(deta_x),
            position_cm=float(deta_y),
            velocity_cm_s=0.0,
            sequence=self._sequence,
        )
        self._sequence = (self._sequence + 1) & 0xFFFF
        return self.send_vision_frame(frame)

    def close(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except (OSError, serial.SerialException):
                pass
        self.ser = None
        self.is_open = False

    def __enter__(self):
        if not self.open():
            raise OSError(f"failed to open serial port: {self.port}")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def __del__(self):
        self.close()
