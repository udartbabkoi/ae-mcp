"""
Adobe After Effects MCP (Model Context Protocol) Server.
Connects local LLMs and agentic assistants directly to an active Adobe After Effects
session on Windows using thread-safe COM dispatch, audio DSP, and computer vision rotoscoping.
"""

import os
import sys
import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from mcp.server.fastmcp import FastMCP

# Ensure current repository root is on sys.path
_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from bridge.backend import (
    AEBridgeError,
    AENotRunningError,
    AETimeoutError,
    AEScriptExecutionError,
    AECOMError,
)
from bridge.ae_dispatch import COMBridgeBackend, CLIBridgeBackend, AEDispatcher, create_default_backend
from bridge.audio import analyze_audio
from bridge.vision import extract_and_segment_frames, build_track_matte_extendscript
from extendscript import get_json2_source, get_dom_helpers_source, build_bundled_script

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger("ae_mcp.server")

# Initialize FastMCP Server
mcp = FastMCP("ae-mcp")

# Shared Dispatcher Instance
_dispatcher: Optional[AEDispatcher] = None


def get_dispatcher() -> AEDispatcher:
    """Retrieve or initialize the active AE dispatcher."""
    global _dispatcher
    if _dispatcher is None:
        backend = create_default_backend()
        _dispatcher = AEDispatcher(backend=backend)
    return _dispatcher


@mcp.tool()
def get_active_comp_state() -> Dict[str, Any]:
    """
    Introspect the currently open composition in Adobe After Effects.

    Returns complete metadata including composition name, dimensions (width/height),
    frame rate, duration, work area, and all layers (index, name, type, in/out points,
    enabled status, track matte settings, parenting, and masks).
    """
    dispatcher = get_dispatcher()

    script = build_bundled_script("""
    return AEDomHelpers.getActiveCompState();
    """, include_dom_helpers=True)

    try:
        result = dispatcher.execute_with_undo(script, undo_name="Inspect Comp State")
        return {
            "status": "success",
            "composition": result
        }
    except AENotRunningError as e:
        return {
            "status": "error",
            "error_type": "AENotRunningError",
            "message": str(e),
            "hint": "Please open Adobe After Effects and create or open a project with a composition."
        }
    except AETimeoutError as e:
        return {
            "status": "error",
            "error_type": "AETimeoutError",
            "message": str(e),
            "hint": "Check if After Effects has a modal dialog or alert open and dismiss it."
        }
    except AEScriptExecutionError as e:
        return {
            "status": "error",
            "error_type": "AEScriptExecutionError",
            "message": e.message,
            "line": e.line,
            "stack": e.stack
        }
    except Exception as e:
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "message": str(e)
        }


@mcp.tool()
def execute_extendscript(code: str, undo_name: str = "AI Action") -> Dict[str, Any]:
    """
    Execute arbitrary ExtendScript (ES3) in the active After Effects session.
    Automatically wraps execution in app.beginUndoGroup(undo_name) and app.endUndoGroup().
    Bundles json2 polyfill and captures line-numbered errors and stack traces.

    Args:
        code: ExtendScript ES3 source code to execute.
        undo_name: Display label for After Effects Edit > Undo menu.
    """
    dispatcher = get_dispatcher()

    # Prepend dom helpers so AEDomHelpers and MATCH constants are available
    bundled_code = build_bundled_script(code, include_dom_helpers=True)

    try:
        result = dispatcher.execute_with_undo(bundled_code, undo_name=undo_name)
        return {
            "status": "success",
            "undo_name": undo_name,
            "result": result
        }
    except AEScriptExecutionError as e:
        return {
            "status": "error",
            "error_type": "AEScriptExecutionError",
            "message": e.message,
            "line": e.line,
            "stack": e.stack
        }
    except (AENotRunningError, AETimeoutError, AECOMError) as e:
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "message": str(e)
        }
    except Exception as e:
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "message": str(e)
        }


@mcp.tool()
def create_mask_path(
    layer_index: int,
    vertices: List[List[float]],
    in_tangents: Optional[List[List[float]]] = None,
    out_tangents: Optional[List[List[float]]] = None,
    mask_mode: str = "ADD",
    feather: Optional[List[float]] = None,
    closed: bool = True
) -> Dict[str, Any]:
    """
    Inject vector path geometry into ADBE Mask Parade on a target layer using After Effects' Shape() object.

    Args:
        layer_index: 1-based index of the target layer in the active comp.
        vertices: List of [x, y] coordinates in Layer Space (e.g. [[100, 100], [200, 100], ...]).
        in_tangents: Optional list of incoming bezier tangent offsets [dx, dy] matching vertex count.
        out_tangents: Optional list of outgoing bezier tangent offsets [dx, dy] matching vertex count.
        mask_mode: One of 'NONE', 'ADD', 'SUBTRACT', 'INTERSECT', 'LIGHTEN', 'DARKEN', 'DIFFERENCE'.
        feather: Optional [x, y] mask feather values in pixels (e.g. [5, 5]). Defaults to [0, 0].
        closed: Whether the mask vector path is closed (default True).
    """
    # Validation
    if not vertices or len(vertices) < 2:
        return {
            "status": "error",
            "message": "Mask path requires at least 2 vertices."
        }

    for idx, v in enumerate(vertices):
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            return {
                "status": "error",
                "message": f"Vertex at index {idx} must be a 2-element [x, y] coordinate list, got {v}."
            }

    if in_tangents and len(in_tangents) != len(vertices):
        return {
            "status": "error",
            "message": f"in_tangents count ({len(in_tangents)}) must match vertices count ({len(vertices)})."
        }

    if out_tangents and len(out_tangents) != len(vertices):
        return {
            "status": "error",
            "message": f"out_tangents count ({len(out_tangents)}) must match vertices count ({len(vertices)})."
        }

    valid_modes = ["NONE", "ADD", "SUBTRACT", "INTERSECT", "LIGHTEN", "DARKEN", "DIFFERENCE"]
    clean_mode = mask_mode.upper()
    if clean_mode not in valid_modes:
        return {
            "status": "error",
            "message": f"Invalid mask_mode '{mask_mode}'. Must be one of {valid_modes}."
        }

    effective_feather = feather if (feather and len(feather) == 2) else [0.0, 0.0]

    dispatcher = get_dispatcher()

    # Serialize JSON arguments to pass safely into ExtendScript call
    verts_json = json.dumps(vertices)
    in_tan_json = json.dumps(in_tangents) if in_tangents else "null"
    out_tan_json = json.dumps(out_tangents) if out_tangents else "null"
    feather_json = json.dumps(effective_feather)
    closed_js = "true" if closed else "false"

    script = build_bundled_script(f"""
    return AEDomHelpers.createMaskPath(
        {layer_index},
        {verts_json},
        {in_tan_json},
        {out_tan_json},
        "{clean_mode}",
        {feather_json},
        {closed_js}
    );
    """, include_dom_helpers=True)

    try:
        result = dispatcher.execute_with_undo(script, undo_name=f"Create Mask on Layer {layer_index}")
        return {
            "status": "success",
            "layer_index": layer_index,
            "mask_mode": clean_mode,
            "mask_data": result
        }
    except Exception as e:
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "message": str(e)
        }


@mcp.tool()
def analyze_audio_track(file_path: str, hop_length: int = 512) -> Dict[str, Any]:
    """
    Analyze an audio track using librosa/scipy DSP to extract BPM, onset timestamps,
    prominent energy peaks, and normalized RMS energy envelopes formatted for AE keyframes.

    Args:
        file_path: Absolute or relative path to the audio file (.wav, .mp3, .aif, .flac, etc.).
        hop_length: Number of samples between successive STFT/RMS frames (default 512).
    """
    if not os.path.isfile(file_path):
        return {
            "status": "error",
            "message": f"Audio file not found at path: {file_path}"
        }

    try:
        analysis = analyze_audio(file_path=file_path, hop_length=hop_length)
        return {
            "status": "success",
            "analysis": analysis
        }
    except Exception as e:
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "message": str(e)
        }


@mcp.tool()
def segment_and_track_matte(
    layer_index: int,
    model: str = "rembg",
    time_range: Optional[List[float]] = None
) -> Dict[str, Any]:
    """
    Bypasses After Effects' closed Roto Brush API by extracting footage frames via OpenCV,
    generating an alpha matte image sequence locally via AI (rembg/u2net), importing the matte
    sequence into After Effects, positioning it above the source layer, and applying setTrackMatte(ALPHA).

    Args:
        layer_index: 1-based index of the footage layer in the active composition.
        model: Segmentation model to use ('rembg', 'grabcut', or 'saliency').
        time_range: Optional [start_seconds, end_seconds] to rotoscope. If omitted, uses full layer duration.
    """
    dispatcher = get_dispatcher()

    # 1. Query target layer footage path and temporal boundaries from After Effects
    query_script = f"""
    (function() {{
        if (!app.project || !app.project.activeItem || !(app.project.activeItem instanceof CompItem)) {{
            throw new Error("No active composition open in After Effects.");
        }}
        var comp = app.project.activeItem;
        if ({layer_index} < 1 || {layer_index} > comp.numLayers) {{
            throw new Error("Layer index {layer_index} is out of bounds (1 to " + comp.numLayers + ").");
        }}
        var l = comp.layer({layer_index});
        var srcPath = null;
        if (l.source && l.source.file) {{
            srcPath = l.source.file.fsName;
        }}
        return {{
            name: l.name,
            sourceFilePath: srcPath,
            inPoint: l.inPoint,
            outPoint: l.outPoint,
            startTime: l.startTime,
            compFps: comp.frameRate
        }};
    }})();
    """

    try:
        layer_info = dispatcher.execute_with_undo(query_script, undo_name="Query Layer For Roto")
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to inspect layer {layer_index} in After Effects: {e}"
        }

    footage_path = layer_info.get("sourceFilePath")
    if not footage_path or not os.path.isfile(footage_path):
        return {
            "status": "error",
            "message": (
                f"Layer {layer_index} ('{layer_info.get('name')}') does not reference a footage file on disk. "
                "segment_and_track_matte requires an AVLayer linked to a video or image file."
            )
        }

    # 2. Determine time range
    effective_range: Optional[Tuple[float, float]] = None
    if time_range and len(time_range) == 2:
        effective_range = (float(time_range[0]), float(time_range[1]))
    else:
        effective_range = (float(layer_info.get("inPoint", 0.0)), float(layer_info.get("outPoint", 5.0)))

    comp_fps = float(layer_info.get("compFps", 30.0))

    # 3. Extract and segment frames via OpenCV + AI
    try:
        seq_info = extract_and_segment_frames(
            video_path=footage_path,
            model=model,
            time_range=effective_range,
            target_fps=comp_fps
        )
    except Exception as e:
        return {
            "status": "error",
            "message": f"Frame extraction and segmentation failed: {e}"
        }

    # 4. Generate ExtendScript to import matte sequence and link Track Matte
    first_frame = seq_info["first_frame_path"]
    start_time = float(layer_info.get("startTime", 0.0))

    link_script = build_track_matte_extendscript(
        layer_index=layer_index,
        first_frame_path=first_frame,
        fps=seq_info["fps"],
        start_time=start_time
    )

    # 5. Execute sequence import and track matte setup in AE
    try:
        link_result = dispatcher.execute_with_undo(
            link_script,
            undo_name=f"AI Track Matte for {layer_info.get('name')}"
        )
        return {
            "status": "success",
            "source_layer_index": layer_index,
            "source_layer_name": layer_info.get("name"),
            "model_used": model,
            "segmentation": seq_info,
            "track_matte_result": link_result
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to import and link track matte in After Effects: {e}",
            "segmentation": seq_info
        }


def main():
    """Main CLI entrypoint for running the FastMCP server."""
    logger.info("Starting Adobe After Effects ae-mcp server over stdio...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
