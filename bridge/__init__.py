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
from .ae_dispatch import (
    COMBridgeBackend,
    CLIBridgeBackend,
    AEDispatcher,
    create_default_backend,
    find_afterfx_executable,
    is_ae_running,
)
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
    "CLIBridgeBackend",
    "AEDispatcher",
    "create_default_backend",
    "find_afterfx_executable",
    "is_ae_running",
    "analyze_audio",
    "compute_rms_envelope",
    "detect_tempo_and_onsets",
    "extract_and_segment_frames",
    "build_track_matte_extendscript",
]
