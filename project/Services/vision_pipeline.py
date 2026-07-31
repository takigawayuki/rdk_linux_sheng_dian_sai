"""Reusable single-frame steel-ball vision pipeline."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from project.Algorithm.ball_detector import BallDetector
from project.Algorithm.ball_tracker import BallTracker
from project.Algorithm.rod_mapper import RodMapper
from project.Core.models import BallDetection, BallMeasurement, BallTrack, FramePacket


BALL_VISION_DIRECTION = 1.0
BALL_VISION_SCALE_CM_PER_CM = 1.0


@dataclass(frozen=True)
class VisionPipelineResult:
    measurement: BallMeasurement
    detection: BallDetection
    track: BallTrack


class VisionPipeline:
    def __init__(
        self,
        calibration_file: Path,
        detector: Optional[BallDetector] = None,
        tracker: Optional[BallTracker] = None,
        position_direction: float = BALL_VISION_DIRECTION,
        position_scale: float = BALL_VISION_SCALE_CM_PER_CM,
        control_lookahead_seconds: float = 0.0,
    ):
        if position_direction not in (-1.0, 1.0):
            raise ValueError("position_direction must be -1 or +1")
        if position_scale <= 0.0:
            raise ValueError("position_scale must be positive")
        if not 0.0 <= control_lookahead_seconds <= 0.2:
            raise ValueError("control_lookahead_seconds must be between 0 and 0.2")
        self.mapper = RodMapper.load(calibration_file)
        self.detector = detector or BallDetector()
        self.tracker = tracker or BallTracker()
        self.position_direction = float(position_direction)
        self.position_scale = float(position_scale)
        self.control_lookahead_seconds = float(control_lookahead_seconds)

    def process(
        self, packet: FramePacket, target_position_cm: float = 0.0
    ) -> VisionPipelineResult:
        detection = self.detector.detect(
            packet.frame, self.tracker.predicted_x(packet.captured_at)
        )
        track = self.tracker.update(detection, packet.captured_at)
        position_cm = None
        control_position_cm = None
        velocity_cm_s = 0.0
        error_cm = None
        if track.valid and track.pixel_x is not None:
            coordinate_scale = self.position_scale * self.position_direction
            position_cm = (
                self.mapper.map_pixel(track.pixel_x, clamp=True) * coordinate_scale
            )
            velocity_cm_s = (
                track.velocity_x_px_s
                * self.mapper.slope_cm_per_px
                * coordinate_scale
            )
            raw_prediction = (
                position_cm + velocity_cm_s * self.control_lookahead_seconds
            )
            coordinate_bounds = sorted(
                (
                    self.mapper.min_cm * coordinate_scale,
                    self.mapper.max_cm * coordinate_scale,
                )
            )
            control_position_cm = min(
                coordinate_bounds[1], max(coordinate_bounds[0], raw_prediction)
            )
            error_cm = float(target_position_cm) - control_position_cm
        measurement = BallMeasurement(
            captured_at=packet.captured_at,
            sequence=packet.sequence,
            position_cm=position_cm,
            confidence=track.confidence,
            detected=track.detected,
            velocity_cm_s=velocity_cm_s,
            valid=track.valid,
            predicted=track.predicted,
            target_position_cm=float(target_position_cm),
            error_cm=error_cm,
            control_position_cm=control_position_cm,
            lookahead_seconds=self.control_lookahead_seconds,
        )
        return VisionPipelineResult(measurement, detection, track)
