"""
Unit tests for computer vision frame extraction and matte segmentation.
"""

import os
import shutil
import tempfile
import pytest
import numpy as np
from PIL import Image

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from bridge.vision import (
    extract_and_segment_frames,
    build_track_matte_extendscript,
    VisionProcessingError,
)


@pytest.fixture
def synthetic_video_file():
    """Create a 5-frame synthetic MP4/AVI video with a white box moving on black background."""
    if not HAS_CV2:
        pytest.skip("OpenCV not installed")

    width, height = 320, 240
    fps = 10.0
    num_frames = 5

    temp_dir = tempfile.mkdtemp()
    video_path = os.path.join(temp_dir, "synth_footage.mp4")

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(video_path, fourcc, fps, (width, height))

    try:
        for i in range(num_frames):
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            # Draw moving white rectangle
            x_start = 50 + i * 20
            cv2.rectangle(frame, (x_start, 50), (x_start + 80, 150), (255, 255, 255), -1)
            out.write(frame)
    finally:
        out.release()

    yield video_path

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_extract_and_segment_frames(synthetic_video_file):
    """Verify video frame extraction, matte generation, and sequence saving."""
    temp_out = tempfile.mkdtemp()
    try:
        result = extract_and_segment_frames(
            video_path=synthetic_video_file,
            output_dir=temp_out,
            model="saliency",  # Fast local fallback model
            target_fps=10.0
        )

        assert "sequence_directory" in result
        assert "first_frame_path" in result
        assert result["frame_count"] > 0
        assert os.path.isfile(result["first_frame_path"])

        # Verify generated frame format (RGBA PNG)
        first_frame = Image.open(result["first_frame_path"])
        assert first_frame.format == "PNG"
        assert first_frame.mode == "RGBA"
        assert first_frame.size == (320, 240)

        # Alpha channel should have non-zero mask pixels
        alpha = np.array(first_frame)[:, :, 3]
        assert np.max(alpha) > 0

    finally:
        shutil.rmtree(temp_out, ignore_errors=True)


def test_extract_nonexistent_video():
    """Verify FileNotFoundError for missing video files."""
    with pytest.raises(FileNotFoundError):
        extract_and_segment_frames("C:/nonexistent_video_path.mp4")


def test_build_track_matte_extendscript():
    """Verify generated ExtendScript for track matte sequence import."""
    script = build_track_matte_extendscript(
        layer_index=2,
        first_frame_path="C:\\temp\\matte_00000.png",
        fps=29.97,
        start_time=1.5
    )

    # Must contain sanitized forward slashes
    assert "C:/temp/matte_00000.png" in script
    # Target layer index
    assert "var targetIndex = 2;" in script
    # Modern setTrackMatte check
    assert "targetLayer.setTrackMatte(matteLayer, TrackMatteType.ALPHA)" in script
    # Legacy fallback
    assert "targetLayer.trackMatteType = TrackMatteType.ALPHA" in script
    # Conform frame rate
    assert "matteFootage.mainSource.conformFrameRate = 29.97;" in script
