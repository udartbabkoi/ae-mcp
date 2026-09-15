"""
Computer Vision AI Rotoscoping & Matte Generation Pipeline.
Extracts video frames via OpenCV, computes foreground alpha mattes
locally using rembg / computer vision pipelines, and exports formatted
image sequences ready for Adobe After Effects Track Matte linking.
"""

import os
import sys
import time
import shutil
import tempfile
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import numpy as np
from PIL import Image

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import rembg
    HAS_REMBG = True
except ImportError:
    HAS_REMBG = False

logger = logging.getLogger("ae_mcp.bridge.vision")


class VisionProcessingError(Exception):
    """Raised when frame extraction, segmentation, or sequence generation fails."""
    pass


def extract_and_segment_frames(
    video_path: str,
    output_dir: Optional[str] = None,
    model: str = "rembg",
    time_range: Optional[Tuple[float, float]] = None,
    target_fps: Optional[float] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, Any]:
    """
    Extract frames from a video file across time_range, generate alpha mattes,
    and save them as a sequential PNG image sequence (frame_00000.png, ...).

    Args:
        video_path: Path to the input video or image footage file.
        output_dir: Destination directory. If None, a dedicated directory in temp is created.
        model: Segmentation model ('rembg', 'grabcut', or 'saliency').
        time_range: Optional (start_seconds, end_seconds). If None, full duration is used.
        target_fps: Optional frame rate to resample. If None, original video FPS is used.
        progress_callback: Optional callback(current_frame, total_frames).

    Returns:
        Dictionary with sequence directory, first frame path, frame count, fps, and metadata.
    """
    if not HAS_CV2:
        raise VisionProcessingError("OpenCV (cv2) is required for video frame extraction.")

    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Source video footage not found: {video_path}")

    # Set up destination directory
    if output_dir is None:
        timestamp = int(time.time())
        output_dir = os.path.join(tempfile.gettempdir(), f"ae_mcp_matte_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise VisionProcessingError(f"OpenCV could not open video file: {video_path}")

    try:
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        if video_fps <= 0 or np.isnan(video_fps):
            video_fps = 30.0  # Safe fallback for variable frame rate or stills

        total_source_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = float(total_source_frames) / float(video_fps) if total_source_frames > 0 else 0.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Calculate time boundaries
        start_sec = 0.0
        end_sec = duration
        if time_range:
            start_sec = max(0.0, float(time_range[0]))
            if time_range[1] is not None and time_range[1] > start_sec:
                end_sec = min(duration, float(time_range[1]))

        effective_fps = target_fps if (target_fps and target_fps > 0) else video_fps
        frame_interval_sec = 1.0 / effective_fps

        # Generate sampling timestamps
        sample_times: List[float] = []
        curr = start_sec
        while curr <= end_sec + 1e-4:
            sample_times.append(curr)
            curr += frame_interval_sec

        if not sample_times:
            sample_times = [start_sec]

        logger.info(
            "Extracting and segmenting %d frames from %s (time: %.2f - %.2f s at %.2f FPS)",
            len(sample_times), video_path, start_sec, end_sec, effective_fps
        )

        # Pre-initialize rembg session if requested
        rembg_session = None
        if model.lower() == "rembg" and HAS_REMBG:
            try:
                rembg_session = rembg.new_session("u2net")
            except Exception as e:
                logger.warning("Could not initialize u2net session for rembg: %s. Using default session.", e)

        saved_files: List[str] = []

        for seq_idx, t in enumerate(sample_times):
            # Seek video to target timestamp in milliseconds
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ret, frame_bgr = cap.read()
            if not ret or frame_bgr is None:
                # If seek failed near end, try reading next frame or stop
                break

            # Segment frame to alpha mask
            matte_mask = _segment_frame(frame_bgr, model=model, rembg_session=rembg_session)

            # Build 32-bit RGBA matte: White RGB with alpha channel = mask
            # This ensures optimal compatibility with both Alpha and Luma track matte modes in AE
            h, w = matte_mask.shape
            rgba_matte = np.zeros((h, w, 4), dtype=np.uint8)
            rgba_matte[:, :, 0] = 255  # Red
            rgba_matte[:, :, 1] = 255  # Green
            rgba_matte[:, :, 2] = 255  # Blue
            rgba_matte[:, :, 3] = matte_mask  # Alpha channel

            out_filename = f"matte_{seq_idx:05d}.png"
            out_path = os.path.join(output_dir, out_filename)

            # Save PNG using PIL to preserve alpha channel cleanly
            pil_matte = Image.fromarray(rgba_matte, mode="RGBA")
            pil_matte.save(out_path, format="PNG", compress_level=3)
            saved_files.append(out_path)

            if progress_callback:
                progress_callback(seq_idx + 1, len(sample_times))

        if not saved_files:
            raise VisionProcessingError(f"No frames could be extracted from footage: {video_path}")

        first_frame_path = os.path.abspath(saved_files[0])

        return {
            "sequence_directory": os.path.abspath(output_dir),
            "first_frame_path": first_frame_path,
            "frame_count": len(saved_files),
            "fps": round(float(effective_fps), 3),
            "start_time_seconds": round(float(start_sec), 3),
            "duration_seconds": round(float(len(saved_files) * frame_interval_sec), 3),
            "dimensions": {"width": width, "height": height},
            "model_used": model,
        }

    finally:
        cap.release()


def _segment_frame(
    frame_bgr: np.ndarray,
    model: str = "rembg",
    rembg_session: Any = None
) -> np.ndarray:
    """
    Generate an 8-bit single-channel alpha mask (0=background, 255=foreground).
    """
    model_lower = model.lower()

    # Model 1: rembg (AI background removal)
    if model_lower == "rembg" and HAS_REMBG:
        try:
            # Convert BGR to RGB PIL
            rgb_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb_frame)

            # Run rembg
            if rembg_session:
                result_rgba = rembg.remove(pil_img, session=rembg_session, only_mask=True)
            else:
                result_rgba = rembg.remove(pil_img, only_mask=True)

            mask = np.array(result_rgba)
            if mask.ndim == 3:
                mask = mask[:, :, 0]
            return mask.astype(np.uint8)
        except Exception as e:
            logger.warning("rembg segmentation failed on frame: %s. Using CV fallback.", e)

    # Fallback Model: GrabCut / Edge Saliency
    return _segment_cv_fallback(frame_bgr)


def _segment_cv_fallback(frame_bgr: np.ndarray) -> np.ndarray:
    """
    Lightweight computer vision segmentation fallback using color saliency
    and Otsu thresholding when neural models are unavailable.
    """
    h, w = frame_bgr.shape[:2]
    # Convert to LAB for luminance/color saliency
    lab = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    # Compute color distance from border pixels (assuming borders are background)
    border_pixels = np.concatenate([
        lab[0, :, :], lab[-1, :, :], lab[:, 0, :], lab[:, -1, :]
    ], axis=0)
    bg_mean = np.mean(border_pixels, axis=0)

    diff = np.linalg.norm(lab.astype(np.float32) - bg_mean, axis=2)
    diff_norm = cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    # Threshold with Otsu
    _, thresh = cv2.threshold(diff_norm, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Morphological clean up
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    cleaned = cv2.GaussianBlur(cleaned, (5, 5), 0)

    return cleaned


def build_track_matte_extendscript(
    layer_index: int,
    first_frame_path: str,
    fps: float,
    start_time: float = 0.0
) -> str:
    """
    Generate the ES3 ExtendScript snippet to import the matte image sequence,
    conform its frame rate, place it directly above the target layer,
    and link it as an Alpha Track Matte.
    """
    # Sanitize Windows backslashes for ExtendScript string literals
    clean_path = first_frame_path.replace("\\", "/")

    return f"""
(function() {{
    if (!app.project || !app.project.activeItem || !(app.project.activeItem instanceof CompItem)) {{
        throw new Error("No active composition open in After Effects.");
    }}

    var comp = app.project.activeItem;
    var targetIndex = {layer_index};

    if (targetIndex < 1 || targetIndex > comp.numLayers) {{
        throw new Error("Target layer index " + targetIndex + " is out of bounds (1 to " + comp.numLayers + ").");
    }}

    var targetLayer = comp.layer(targetIndex);

    // 1. Setup sequence import
    var seqFile = new File("{clean_path}");
    if (!seqFile.exists) {{
        throw new Error("Matte sequence file not found at: {clean_path}");
    }}

    var importOptions = new ImportOptions(seqFile);
    importOptions.sequence = true;
    importOptions.forceAlphabetical = true;

    var matteFootage = app.project.importFile(importOptions);
    matteFootage.name = "AI_Matte_" + targetLayer.name;

    // Conform frame rate to match comp / video
    if (matteFootage.mainSource && matteFootage.mainSource.conformFrameRate !== undefined) {{
        matteFootage.mainSource.conformFrameRate = {fps};
    }}

    // 2. Add matte layer directly above the target layer
    var matteLayer = comp.layers.add(matteFootage);
    matteLayer.startTime = {start_time};
    matteLayer.inPoint = targetLayer.inPoint;
    matteLayer.outPoint = targetLayer.outPoint;
    matteLayer.moveBefore(targetLayer);

    // 3. Apply Alpha Track Matte (AE 2023+ modern API vs legacy fallback)
    var matteApplied = false;
    var apiType = "legacy";

    if (typeof targetLayer.setTrackMatte === "function") {{
        // Modern AE 2023+ (v23.0+) API
        targetLayer.setTrackMatte(matteLayer, TrackMatteType.ALPHA);
        matteApplied = true;
        apiType = "modern_setTrackMatte";
    }} else if (targetLayer.trackMatteType !== undefined) {{
        // Legacy AE API (matte layer must be immediately above targetLayer)
        targetLayer.trackMatteType = TrackMatteType.ALPHA;
        matteApplied = true;
        apiType = "legacy_trackMatteType";
    }}

    return {{
        status: "success",
        matteLayerIndex: matteLayer.index,
        matteLayerName: matteLayer.name,
        targetLayerIndex: targetLayer.index,
        apiType: apiType,
        trackMatteApplied: matteApplied
    }};
}})();
"""
