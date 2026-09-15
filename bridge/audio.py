"""
Audio Analysis & Keyframe DSP Engine for Adobe After Effects.
Extracts BPM, onset timestamps, normalized RMS energy envelopes,
and converts audio features into keyframe sequences ready for ExtendScript.
"""

import os
import math
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

try:
    import librosa
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False

try:
    import soundfile as sf
    HAS_SOUNDFILE = True
except ImportError:
    HAS_SOUNDFILE = False

import scipy.signal
import scipy.io.wavfile

logger = logging.getLogger("ae_mcp.bridge.audio")


class AudioAnalysisError(Exception):
    """Raised when audio loading or DSP processing fails."""
    pass


def load_audio_signal(file_path: str, target_sr: Optional[int] = None) -> Tuple[np.ndarray, int]:
    """
    Load an audio file into a mono float32 numpy array [-1.0, 1.0] and sample rate.
    Uses librosa or soundfile with fallback to scipy for uncompressed WAV.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    # Strategy 1: librosa (handles mp3, aac, wav, ogg, flac, etc.)
    if HAS_LIBROSA:
        try:
            y, sr = librosa.load(file_path, sr=target_sr, mono=True)
            return y.astype(np.float32), int(sr)
        except Exception as e:
            logger.warning("librosa.load failed on %s: %s. Trying soundfile...", file_path, e)

    # Strategy 2: soundfile
    if HAS_SOUNDFILE:
        try:
            data, sr = sf.read(file_path, dtype="float32", always_2d=False)
            if data.ndim > 1:
                data = np.mean(data, axis=1)
            return data.astype(np.float32), int(sr)
        except Exception as e:
            logger.warning("soundfile.read failed on %s: %s. Trying scipy...", file_path, e)

    # Strategy 3: scipy.io.wavfile
    try:
        sr, data = scipy.io.wavfile.read(file_path)
        if data.dtype == np.int16:
            data = data.astype(np.float32) / 32768.0
        elif data.dtype == np.int32:
            data = data.astype(np.float32) / 2147483648.0
        elif data.dtype == np.uint8:
            data = (data.astype(np.float32) - 128.0) / 128.0
        else:
            data = data.astype(np.float32)

        if data.ndim > 1:
            data = np.mean(data, axis=1)

        return data, int(sr)
    except Exception as e:
        raise AudioAnalysisError(
            f"Could not decode audio file '{file_path}'. Ensure file is valid audio: {e}"
        ) from e


def compute_rms_envelope(
    y: np.ndarray,
    sr: int,
    hop_length: int = 512,
    frame_length: int = 2048
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute normalized Root Mean Square (RMS) energy envelope over time.

    Returns:
        (timestamps, normalized_rms)
    """
    if len(y) == 0:
        return np.array([], dtype=np.float32), np.array([], dtype=np.float32)

    if HAS_LIBROSA:
        try:
            rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
            times = librosa.times_like(rms, sr=sr, hop_length=hop_length)
        except Exception:
            rms, times = _compute_rms_manual(y, sr, hop_length, frame_length)
    else:
        rms, times = _compute_rms_manual(y, sr, hop_length, frame_length)

    # Normalize to [0.0, 1.0]
    max_val = float(np.max(rms)) if len(rms) > 0 else 0.0
    min_val = float(np.min(rms)) if len(rms) > 0 else 0.0

    if max_val - min_val > 1e-6:
        normalized = (rms - min_val) / (max_val - min_val)
    else:
        normalized = np.zeros_like(rms)

    return times, normalized.astype(np.float32)


def _compute_rms_manual(
    y: np.ndarray,
    sr: int,
    hop_length: int,
    frame_length: int
) -> Tuple[np.ndarray, np.ndarray]:
    """Fallback manual sliding window RMS calculation."""
    num_frames = max(1, 1 + (len(y) - frame_length) // hop_length)
    rms_vals = np.zeros(num_frames, dtype=np.float32)
    times = np.zeros(num_frames, dtype=np.float32)

    for i in range(num_frames):
        start = i * hop_length
        end = start + frame_length
        window = y[start:end]
        if len(window) > 0:
            rms_vals[i] = np.sqrt(np.mean(window ** 2))
        times[i] = (start + frame_length / 2.0) / float(sr)

    return rms_vals, times


def detect_tempo_and_onsets(
    y: np.ndarray,
    sr: int,
    hop_length: int = 512
) -> Tuple[float, List[float]]:
    """
    Estimate BPM tempo and detect musical onset timestamps in seconds.
    """
    if len(y) == 0:
        return 0.0, []

    bpm = 120.0
    onsets: List[float] = []

    if HAS_LIBROSA:
        try:
            # Beat tempo
            tempo_result, _ = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)
            if isinstance(tempo_result, np.ndarray):
                bpm = float(tempo_result.item(0)) if tempo_result.size > 0 else 120.0
            else:
                bpm = float(tempo_result)

            # Musical onsets
            onset_frames = librosa.onset.onset_detect(y=y, sr=sr, hop_length=hop_length, units="frames")
            onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=hop_length)
            onsets = [round(float(t), 4) for t in onset_times]
            return round(bpm, 2), onsets
        except Exception as e:
            logger.warning("librosa beat detection failed: %s. Using fallback.", e)

    # Fallback: Autocorrelation-based BPM & peak-detection on energy
    times, rms = compute_rms_envelope(y, sr, hop_length=hop_length)
    if len(rms) > 10:
        # Detect peaks in RMS envelope
        peaks, _ = scipy.signal.find_peaks(
            rms,
            prominence=0.15,
            distance=int((sr / hop_length) * 0.2)  # Min 200ms between beats
        )
        onsets = [round(float(times[p]), 4) for p in peaks]

        # Estimate tempo from inter-peak intervals
        if len(onsets) > 2:
            diffs = np.diff(onsets)
            median_diff = float(np.median(diffs))
            if median_diff > 0:
                bpm = 60.0 / median_diff
                # Normalize into reasonable musical range (60-180 BPM)
                while bpm < 70.0:
                    bpm *= 2.0
                while bpm > 180.0:
                    bpm /= 2.0

    return round(float(bpm), 2), onsets


def resample_envelope_for_comp(
    times: np.ndarray,
    values: np.ndarray,
    target_fps: float = 30.0,
    duration: Optional[float] = None
) -> Tuple[List[float], List[float]]:
    """
    Downsample / interpolate an audio envelope to match comp frame rate,
    preventing UI slowdowns in AE from millions of redundant keyframes.
    """
    if len(times) == 0:
        return [], []

    total_duration = duration if duration is not None else float(times[-1])
    num_frames = int(math.ceil(total_duration * target_fps)) + 1
    target_times = np.linspace(0.0, total_duration, num_frames)

    # Linear interpolation
    interpolated = np.interp(target_times, times, values)
    interpolated = np.clip(interpolated, 0.0, 1.0)

    return (
        [round(float(t), 4) for t in target_times],
        [round(float(v), 4) for v in interpolated],
    )


def analyze_audio(
    file_path: str,
    hop_length: int = 512,
    target_fps: float = 30.0
) -> Dict[str, Any]:
    """
    Main audio analysis routine.
    Loads audio, extracts BPM, onsets, full RMS envelope, downsampled comp keyframes,
    and returns a clean dictionary.
    """
    abs_path = os.path.abspath(file_path)
    y, sr = load_audio_signal(abs_path)
    duration = float(len(y)) / float(sr)

    # 1. RMS Envelope
    times, rms = compute_rms_envelope(y, sr, hop_length=hop_length)

    # 2. BPM and Onsets
    bpm, onsets = detect_tempo_and_onsets(y, sr, hop_length=hop_length)

    # 3. Peak Detection (top prominent energy spikes)
    peaks_indices, _ = scipy.signal.find_peaks(
        rms,
        height=0.6,
        distance=int((sr / hop_length) * 0.15)
    )
    peak_times = [round(float(times[i]), 4) for i in peaks_indices]

    # 4. Comp-ready downsampled keyframe data
    comp_times, comp_values = resample_envelope_for_comp(times, rms, target_fps=target_fps, duration=duration)

    return {
        "file_path": abs_path,
        "duration_seconds": round(duration, 3),
        "sample_rate": sr,
        "bpm": bpm,
        "total_onsets": len(onsets),
        "onset_timestamps": onsets,
        "peak_timestamps": peak_times,
        "keyframe_data": {
            "fps": target_fps,
            "times": comp_times,
            "values": comp_values,
        },
        "stats": {
            "min_rms": round(float(np.min(rms)), 4) if len(rms) > 0 else 0.0,
            "max_rms": round(float(np.max(rms)), 4) if len(rms) > 0 else 0.0,
            "mean_rms": round(float(np.mean(rms)), 4) if len(rms) > 0 else 0.0,
        }
    }
