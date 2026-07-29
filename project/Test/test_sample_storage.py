import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from project.Core.models import CameraConfig, FramePacket
from project.Services.sample_storage import SampleSession


class SampleSessionTests(unittest.TestCase):
    def test_snapshot_and_metadata_are_written_together(self):
        with tempfile.TemporaryDirectory() as directory:
            session = SampleSession(Path(directory), "static ball", -5.0)
            session_path = session.start(
                CameraConfig(),
                {
                    "width": 640,
                    "height": 480,
                    "fps": 120.0,
                    "undistortion": {"enabled": True},
                },
                [],
            )
            image_path = session.save_snapshot(
                FramePacket(
                    frame=np.zeros((8, 12, 3), dtype=np.uint8),
                    captured_at=12.5,
                    sequence=7,
                )
            )
            session.close()

            metadata = json.loads(
                (session_path / "samples.jsonl").read_text(encoding="utf-8")
            )
            self.assertTrue(image_path.exists())
            self.assertEqual(metadata["position_cm"], -5.0)
            self.assertEqual(metadata["frame_sequence"], 7)
            self.assertEqual(metadata["width"], 12)
            session_metadata = json.loads(
                (session_path / "session.json").read_text(encoding="utf-8")
            )
            self.assertTrue(session_metadata["images_are_undistorted"])


if __name__ == "__main__":
    unittest.main()
