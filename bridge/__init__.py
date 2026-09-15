"""
AE-MCP Bridge Package.
Provides IPC transport, audio analysis DSP, and vision segmentation pipelines.
"""

from .backend import (
    BridgeBackend,
    AEBridgeError,
    AENotRunningError,
    AETimeoutError,
    AEScriptExecutionError,
    AECOMError,
)
from .ae_dispatch import COMBridgeBackend, AEDispatcher
from .audio import analyze_audio, compute_rms_envelope, detect_tempo_and_onsets
from .vision import extract_and_segment_frames, build_track_matte_extendscript

__all__ = [
    "BridgeBackend",
    "AEBridgeError",
    "AENotRunningError",
    "AETimeoutError",
    "AEScriptExecutionError",
    "AECOMError",
    "COMBridgeBackend",
    "AEDispatcher",
    "analyze_audio",
    "compute_rms_envelope",
    "detect_tempo_and_onsets",
    "extract_and_segment_frames",
    "build_track_matte_extendscript",
]
