"""
Unit tests for audio analysis and keyframe generation DSP.
"""

import os
import tempfile
import pytest
import numpy as np
import scipy.io.wavfile

from bridge.audio import (
    load_audio_signal,
    compute_rms_envelope,
    detect_tempo_and_onsets,
    resample_envelope_for_comp,
    analyze_audio,
    AudioAnalysisError,
)


@pytest.fixture
def synthetic_wav_file():
    """Generate a temporary 2-second WAV file with 120 BPM pulses."""
    sr = 22050
    duration = 2.0  # seconds
    total_samples = int(sr * duration)
    t = np.linspace(0, duration, total_samples, endpoint=False)

    # 440 Hz carrier tone
    carrier = 0.3 * np.sin(2 * np.pi * 440 * t)

    # Create pulses every 0.5 seconds (120 BPM = 2 beats per second)
    pulse_envelope = np.zeros(total_samples, dtype=np.float32)
    for beat_time in [0.0, 0.5, 1.0, 1.5]:
        beat_idx = int(beat_time * sr)
        pulse_len = int(0.08 * sr)
        if beat_idx + pulse_len < total_samples:
            pulse_envelope[beat_idx:beat_idx + pulse_len] = 1.0

    signal = (carrier * pulse_envelope).astype(np.float32)
    int_signal = (signal * 32767).astype(np.int16)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    scipy.io.wavfile.write(wav_path, sr, int_signal)

    yield wav_path

    if os.path.exists(wav_path):
        os.remove(wav_path)


def test_load_audio_signal(synthetic_wav_file):
    """Verify audio signal loading and float32 normalization."""
    signal, sr = load_audio_signal(synthetic_wav_file)
    assert isinstance(signal, np.ndarray)
    assert signal.dtype == np.float32
    assert sr > 0
    assert len(signal) > 0
    # Values should be within [-1.0, 1.0]
    assert np.max(signal) <= 1.0
    assert np.min(signal) >= -1.0


def test_load_nonexistent_audio():
    """Verify FileNotFoundError on invalid audio paths."""
    with pytest.raises(FileNotFoundError):
        load_audio_signal("C:/nonexistent_audio_file.wav")


def test_compute_rms_envelope(synthetic_wav_file):
    """Verify RMS energy envelope computation and normalization."""
    signal, sr = load_audio_signal(synthetic_wav_file)
    times, rms = compute_rms_envelope(signal, sr, hop_length=512)

    assert len(times) == len(rms)
    assert len(rms) > 0
    # Values should be normalized between 0.0 and 1.0
    assert np.min(rms) >= 0.0
    assert np.max(rms) <= 1.0001


def test_resample_envelope_for_comp():
    """Verify downsampling to comp frame rate."""
    times = np.linspace(0.0, 2.0, 100)
    values = np.sin(times * np.pi)
    values = np.clip(values, 0.0, 1.0)

    target_fps = 30.0
    comp_times, comp_values = resample_envelope_for_comp(times, values, target_fps=target_fps, duration=2.0)

    # 2 seconds at 30 fps should be ~61 frames (0 to 60)
    assert len(comp_times) == 61
    assert len(comp_values) == 61
    assert comp_times[0] == 0.0
    assert comp_times[-1] == 2.0
    for v in comp_values:
        assert 0.0 <= v <= 1.0


def test_analyze_audio_integration(synthetic_wav_file):
    """Verify full audio analysis pipeline output structure."""
    result = analyze_audio(synthetic_wav_file, hop_length=512, target_fps=30.0)

    assert "file_path" in result
    assert result["duration_seconds"] > 1.8
    assert result["bpm"] > 0
    assert "onset_timestamps" in result
    assert isinstance(result["onset_timestamps"], list)
    assert "keyframe_data" in result
    assert "fps" in result["keyframe_data"]
    assert len(result["keyframe_data"]["times"]) > 0
    assert len(result["keyframe_data"]["values"]) == len(result["keyframe_data"]["times"])
