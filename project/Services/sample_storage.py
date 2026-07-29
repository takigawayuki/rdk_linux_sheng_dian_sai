import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2

from project.Core.models import CameraConfig, FramePacket


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("._") or "sample"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


class SampleSession:
    """Own one labelled sample directory, its metadata and optional video."""

    def __init__(
        self,
        output_root: Path,
        label: str,
        position_cm: Optional[float],
        jpeg_quality: int = 95,
    ):
        if not 1 <= jpeg_quality <= 100:
            raise ValueError("JPEG quality must be between 1 and 100")
        self.output_root = Path(output_root)
        self.label = label
        self.position_cm = position_cm
        self.jpeg_quality = jpeg_quality
        self.path: Optional[Path] = None
        self.saved_images = 0
        self._video_writer = None

    def start(
        self,
        requested_camera: CameraConfig,
        actual_camera: dict,
        mode_warnings: list,
    ) -> Path:
        if self.path is not None:
            raise RuntimeError("sample session has already started")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate = self.output_root / f"{timestamp}_{_safe_name(self.label)}"
        suffix = 1
        while candidate.exists():
            candidate = self.output_root / (
                f"{timestamp}_{_safe_name(self.label)}_{suffix:02d}"
            )
            suffix += 1
        candidate.mkdir(parents=True)
        self.path = candidate

        self._write_json(
            self.path / "session.json",
            {
                "created_at": _now_iso(),
                "label": self.label,
                "position_cm": self.position_cm,
                "requested_camera": requested_camera.to_dict(),
                "actual_camera": actual_camera,
                "mode_warnings": mode_warnings,
                "images_have_preview_overlay": False,
                "images_are_undistorted": bool(
                    actual_camera.get("undistortion", {}).get("enabled", False)
                ),
            },
        )
        return self.path

    def save_snapshot(self, packet: FramePacket) -> Path:
        session_path = self._require_started()
        filename = (
            f"frame_{self.saved_images:04d}_seq_{packet.sequence:08d}.jpg"
        )
        image_path = session_path / filename
        success = cv2.imwrite(
            str(image_path),
            packet.frame,
            [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality],
        )
        if not success:
            raise OSError(f"failed to write image: {image_path}")

        self._append_json_line(
            session_path / "samples.jsonl",
            {
                "file": filename,
                "label": self.label,
                "position_cm": self.position_cm,
                "frame_sequence": packet.sequence,
                "captured_at_monotonic_s": packet.captured_at,
                "saved_at": _now_iso(),
                "width": int(packet.frame.shape[1]),
                "height": int(packet.frame.shape[0]),
            },
        )
        self.saved_images += 1
        return image_path

    def write_video_frame(self, frame, fps: float) -> None:
        session_path = self._require_started()
        if self._video_writer is None:
            height, width = frame.shape[:2]
            self._video_writer = cv2.VideoWriter(
                str(session_path / "video.avi"),
                cv2.VideoWriter_fourcc(*"MJPG"),
                fps,
                (width, height),
            )
            if not self._video_writer.isOpened():
                self._video_writer.release()
                self._video_writer = None
                raise OSError(f"failed to create video: {session_path / 'video.avi'}")
        self._video_writer.write(frame)

    def close(self) -> None:
        if self._video_writer is not None:
            self._video_writer.release()
            self._video_writer = None

    def _require_started(self) -> Path:
        if self.path is None:
            raise RuntimeError("sample session has not started")
        return self.path

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _append_json_line(path: Path, data: dict) -> None:
        with path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(data, ensure_ascii=False) + "\n")

    def __enter__(self) -> "SampleSession":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
