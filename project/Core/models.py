from dataclasses import asdict, dataclass
from typing import Optional, Union

import numpy as np


CameraDevice = Union[int, str]


@dataclass(frozen=True)
class CameraConfig:
    """Requested camera mode and optional UVC controls."""

    device: CameraDevice = 0
    width: int = 640
    height: int = 480
    fps: float = 120.0
    fourcc: str = "MJPG"
    buffer_size: int = 1
    rotation: int = 0
    undistort: bool = True
    calibration_file: Optional[str] = None
    undistort_alpha: float = 0.0
    auto_exposure: Optional[float] = None
    exposure: Optional[float] = None
    gain: Optional[float] = None
    auto_white_balance: Optional[bool] = None
    white_balance_temperature: Optional[float] = None
    autofocus: Optional[bool] = None
    focus: Optional[float] = None

    def validate(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("camera width and height must be positive")
        if self.fps <= 0:
            raise ValueError("camera FPS must be positive")
        if len(self.fourcc) != 4:
            raise ValueError("camera FOURCC must contain exactly four characters")
        if self.buffer_size <= 0:
            raise ValueError("camera buffer size must be positive")
        if self.rotation not in (0, 90, 180, 270):
            raise ValueError("camera rotation must be one of 0, 90, 180, 270")
        if not 0.0 <= self.undistort_alpha <= 1.0:
            raise ValueError("undistort alpha must be between 0 and 1")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FramePacket:
    """A captured frame with timing data used by all downstream stages."""

    frame: np.ndarray
    captured_at: float
    sequence: int
    read_seconds: float = 0.0
    preprocess_seconds: float = 0.0


@dataclass(frozen=True)
class BallDetection:
    """One frame's steel-ball detection in undistorted image coordinates."""

    detected: bool
    pixel_x: Optional[float] = None
    pixel_y: Optional[float] = None
    radius_px: Optional[float] = None
    confidence: float = 0.0
    candidate_count: int = 0
   

@dataclass(frozen=True)
class BallMeasurement:
    """Mapped ball position passed from vision toward tracking/control."""

    captured_at: float
    sequence: int
    position_cm: Optional[float]
    confidence: float
    detected: bool
    velocity_cm_s: float = 0.0
    valid: bool = False
    predicted: bool = False
    target_position_cm: float = 0.0
    error_cm: Optional[float] = None
    control_position_cm: Optional[float] = None
    lookahead_seconds: float = 0.0


@dataclass(frozen=True)
class BallTrack:
    """Temporally filtered pixel state with explicit short-occlusion status."""

    valid: bool
    pixel_x: Optional[float] = None
    pixel_y: Optional[float] = None
    velocity_x_px_s: float = 0.0
    confidence: float = 0.0
    detected: bool = False
    predicted: bool = False
    missed_seconds: float = 0.0
