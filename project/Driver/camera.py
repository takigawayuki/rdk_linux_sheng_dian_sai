import time
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional

import cv2

from project.Core.models import CameraConfig, FramePacket
from project.Driver.calibration.undistorter import Undistorter


DEFAULT_CALIBRATION_FILE = (
    Path(__file__).resolve().parent / "calibration" / "camera_calibration.npz"
)


class CameraError(RuntimeError):
    pass


def _decode_fourcc(value: float) -> str:
    number = int(value)
    return "".join(chr((number >> (8 * index)) & 0xFF) for index in range(4))


class Camera:
    """The single reusable V4L2 camera wrapper used by this project.

    `open()` and `capture()` retain the old project's non-throwing API.
    New code should use the context manager and `capture_packet()` so failures,
    frame timestamps and sequence numbers cannot be silently lost.
    """

    def __init__(self, config: Optional[CameraConfig] = None):
        self.config = config or CameraConfig()
        self.config.validate()
        self.cvcap: Optional[cv2.VideoCapture] = None
        self.is_opened = False
        self.last_error: Optional[str] = None
        self._sequence = 0
        self._control_results: Dict[str, bool] = {}
        self._undistorter: Optional[Undistorter] = None

    def open(self, main_size=None, fps=None) -> bool:
        """Open without raising, preserving compatibility with older callers."""
        if main_size is not None or fps is not None:
            width, height = (
                main_size if main_size is not None else (self.config.width, self.config.height)
            )
            self.config = replace(
                self.config,
                width=width,
                height=height,
                fps=self.config.fps if fps is None else fps,
            )
            self.config.validate()
        try:
            self.open_or_raise()
        except CameraError as error:
            self.last_error = str(error)
            print(f"Camera Open Failed: {error}")
            return False
        return True

    def open_or_raise(self) -> "Camera":
        if self.is_opened and self.cvcap is not None:
            return self

        capture = cv2.VideoCapture(self.config.device, cv2.CAP_V4L2)
        if not capture.isOpened():
            capture.release()
            raise CameraError(
                f"cannot open camera {self.config.device!r}; check the V4L2 device "
                "path and permissions"
            )

        self.cvcap = capture
        self.is_opened = True
        try:
            self._set("fourcc", cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.config.fourcc))
            self._set("width", cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
            self._set("height", cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
            self._set("fps", cv2.CAP_PROP_FPS, self.config.fps)
            self._set("buffer_size", cv2.CAP_PROP_BUFFERSIZE, self.config.buffer_size)
            self._set_optional(
                "auto_exposure", cv2.CAP_PROP_AUTO_EXPOSURE, self.config.auto_exposure
            )
            self._set_optional("exposure", cv2.CAP_PROP_EXPOSURE, self.config.exposure)
            self._set_optional("gain", cv2.CAP_PROP_GAIN, self.config.gain)
            self._set_optional(
                "auto_white_balance",
                cv2.CAP_PROP_AUTO_WB,
                None
                if self.config.auto_white_balance is None
                else float(self.config.auto_white_balance),
            )
            self._set_optional(
                "white_balance_temperature",
                cv2.CAP_PROP_WB_TEMPERATURE,
                self.config.white_balance_temperature,
            )
            self._set_optional(
                "autofocus",
                cv2.CAP_PROP_AUTOFOCUS,
                None if self.config.autofocus is None else float(self.config.autofocus),
            )
            self._set_optional("focus", cv2.CAP_PROP_FOCUS, self.config.focus)
            if self.config.undistort:
                calibration_file = (
                    Path(self.config.calibration_file)
                    if self.config.calibration_file is not None
                    else DEFAULT_CALIBRATION_FILE
                )
                try:
                    self._undistorter = Undistorter(
                        calibration_file,
                        alpha=self.config.undistort_alpha,
                    )
                except (FileNotFoundError, KeyError, OSError, ValueError) as error:
                    raise CameraError(f"cannot load camera calibration: {error}") from error
            else:
                self._undistorter = None
        except Exception:
            self.close()
            raise

        self._sequence = 0
        self.last_error = None
        return self

    def _set(self, name: str, property_id: int, value: float) -> None:
        if self.cvcap is None:
            raise CameraError("camera is not open")
        self._control_results[name] = bool(self.cvcap.set(property_id, value))

    def _set_optional(self, name: str, property_id: int, value: Optional[float]) -> None:
        if value is not None:
            self._set(name, property_id, value)

    def capture_packet(self) -> FramePacket:
        """Read and preprocess one frame synchronously for compatibility callers."""
        return self.preprocess_packet(self.capture_raw_packet())

    def capture_raw_packet(self) -> FramePacket:
        """Read one raw BGR frame without undistortion or rotation."""
        if not self.is_opened or self.cvcap is None:
            raise CameraError("camera is not open")

        read_started = time.monotonic()
        success, frame = self.cvcap.read()
        captured_at = time.monotonic()
        if not success or frame is None:
            raise CameraError("camera opened but failed to read a frame")

        packet = FramePacket(
            frame=frame,
            captured_at=captured_at,
            sequence=self._sequence,
            read_seconds=captured_at - read_started,
        )
        self._sequence += 1
        return packet

    def preprocess_packet(self, packet: FramePacket) -> FramePacket:
        """Apply calibration and rotation without blocking the next camera read."""
        frame = packet.frame
        preprocess_started = time.monotonic()
        if self._undistorter is not None:
            try:
                frame = self._undistorter.apply(frame)
            except (cv2.error, ValueError) as error:
                raise CameraError(f"failed to undistort camera frame: {error}") from error
        frame = self._rotate(frame)
        preprocess_finished = time.monotonic()
        return replace(
            packet,
            frame=frame,
            preprocess_seconds=preprocess_finished - preprocess_started,
        )

    def capture(self, resize=None):
        """Return a bare frame or None, preserving the previous wrapper API."""
        try:
            frame = self.capture_packet().frame
            if resize and isinstance(resize, tuple) and len(resize) == 2:
                frame = cv2.resize(frame, resize)
            return frame
        except CameraError as error:
            self.last_error = str(error)
            print(f"Image Capture Failed: {error}")
            return None

    def _rotate(self, frame):
        rotations = {
            90: cv2.ROTATE_90_CLOCKWISE,
            180: cv2.ROTATE_180,
            270: cv2.ROTATE_90_COUNTERCLOCKWISE,
        }
        rotation_code = rotations.get(self.config.rotation)
        return cv2.rotate(frame, rotation_code) if rotation_code is not None else frame

    def actual_settings(self) -> dict:
        if not self.is_opened or self.cvcap is None:
            raise CameraError("camera is not open")
        undistortion = (
            self._undistorter.describe()
            if self._undistorter is not None
            else {"enabled": False}
        )
        return {
            "device": self.config.device,
            "width": int(round(self.cvcap.get(cv2.CAP_PROP_FRAME_WIDTH))),
            "height": int(round(self.cvcap.get(cv2.CAP_PROP_FRAME_HEIGHT))),
            "fps": float(self.cvcap.get(cv2.CAP_PROP_FPS)),
            "fourcc": _decode_fourcc(self.cvcap.get(cv2.CAP_PROP_FOURCC)),
            "buffer_size": int(round(self.cvcap.get(cv2.CAP_PROP_BUFFERSIZE))),
            "rotation": self.config.rotation,
            "output_fps_target": self.config.fps,
            "undistortion": undistortion,
            "control_set_results": dict(self._control_results),
        }

    def mode_warnings(self) -> List[str]:
        actual = self.actual_settings()
        warnings = []
        expected_size = (self.config.width, self.config.height)
        actual_size = (actual["width"], actual["height"])
        if actual_size != expected_size:
            warnings.append(
                f"camera negotiated {actual_size[0]}x{actual_size[1]}, "
                f"requested {expected_size[0]}x{expected_size[1]}"
            )
        if actual["fourcc"] != self.config.fourcc:
            warnings.append(
                f"camera negotiated FOURCC {actual['fourcc']!r}, "
                f"requested {self.config.fourcc!r}"
            )
        if actual["fps"] > 0 and abs(actual["fps"] - self.config.fps) > 1.0:
            warnings.append(
                f"camera reports {actual['fps']:.2f} FPS, requested {self.config.fps:.2f}"
            )
        failed_controls = [
            name for name, accepted in self._control_results.items() if not accepted
        ]
        if failed_controls:
            warnings.append("driver rejected controls: " + ", ".join(failed_controls))
        return warnings

    def close(self) -> None:
        if self.cvcap is not None:
            self.cvcap.release()
            self.cvcap = None
        self._undistorter = None
        self.is_opened = False

    def __enter__(self) -> "Camera":
        return self.open_or_raise()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def __del__(self):
        self.close()
