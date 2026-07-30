"""Reusable single-frame steel-ball vision pipeline."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from project.Algorithm.ball_detector import BallDetector
from project.Algorithm.ball_tracker import BallTracker
from project.Algorithm.rod_mapper import RodMapper
from project.Core.models import BallDetection, BallMeasurement, BallTrack, FramePacket


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
    ):
        self.mapper = RodMapper.load(calibration_file)
        self.detector = detector or BallDetector()
        self.tracker = tracker or BallTracker()

    def process(
        self, packet: FramePacket, target_position_cm: float = 0.0
    ) -> VisionPipelineResult:
        detection = self.detector.detect(
            packet.frame, self.tracker.predicted_x(packet.captured_at)
        )
        track = self.tracker.update(detection, packet.captured_at)
        position_cm = None
        velocity_cm_s = 0.0
        error_cm = None
        if track.valid and track.pixel_x is not None:
            position_cm = self.mapper.map_pixel(track.pixel_x, clamp=True)
            velocity_cm_s = track.velocity_x_px_s * self.mapper.slope_cm_per_px
            error_cm = float(target_position_cm) - position_cm
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
        )
        return VisionPipelineResult(measurement, detection, track)
