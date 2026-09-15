# ae-mcp: Adobe After Effects Model Context Protocol Server

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%20x64-lightgrey.svg)](https://microsoft.com/windows)
[![Adobe After Effects](https://img.shields.io/badge/Adobe%20After%20Effects-2023%20|%202024%20|%202025+-9999FF.svg)](https://www.adobe.com/products/aftereffects.html)
[![MCP](https://img.shields.io/badge/MCP-1.2+-purple.svg)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A production-grade, end-to-end [Model Context Protocol (MCP)](https://modelcontextprotocol.io) integration connecting local Large Language Models (LLMs) and agentic assistants directly to an active **Adobe After Effects** session on Windows.

`ae-mcp` allows AI assistants like Claude Desktop, Antigravity, Cursor, and custom agents to introspect compositions, construct parametric motion graphics, inject keyframes, create complex vector masks, analyze audio tracks for beat syncing, and perform automated rotoscoping without restarting After Effects or relying on closed internal APIs.

---

## Architecture Overview

```
+-----------------------------------------------------------------------------+
|                           Client Assistant / LLM                            |
|             (Claude Desktop / Antigravity / Cursor / Custom Agent)          |
+--------------------------------------+--------------------------------------+
                                       | stdio (JSON-RPC 2.0)
                                       v
+-----------------------------------------------------------------------------+
|                                ae-mcp Server                                |
|                                 (server.py)                                 |
+--------------------------------------+--------------------------------------+
                                       |
       +-------------------------------+-------------------------------+
       |                               |                               |
       v                               v                               v
+---------------+             +-----------------+             +-----------------+
| bridge/       |             | bridge/         |             | bridge/         |
| ae_dispatch.py|             | audio.py        |             | vision.py       |
| STA Thread    |             | Librosa/Soundfil|             | OpenCV + rembg  |
| Timeout Mgmt  |             | Beat & RMS DSP  |             | Alpha Mattes    |
+-------+-------+             +-----------------+             +--------+--------+
        |                                                              |
        | DoScript()                                                   | Image Sequence
        v                                                              v
+-----------------------------------------------------------------------------+
|                          Adobe After Effects (Win32)                         |
|  - Comp Introspection (extendscript/dom_helpers.jsx)                         |
|  - Shape / Vector Mask Injection (ADBE Mask Parade)                          |
|  - Dual-Engine Track Matte Linking (Modern setTrackMatte + Legacy)           |
|  - Production Templates (Lower Thirds, Audio Reactive, Mask Morphs)         |
+-----------------------------------------------------------------------------+
```

### Key Architectural Pillars

1. **Dual-Backend Windows IPC (`bridge/ae_dispatch.py`)**:
   - **`CLIBridgeBackend` (Default)**: Leverages After Effects' native `AfterFX.exe -r <script.jsx>` execution flag with an atomic temporary file channel for bidirectional JSON data exchange. Because standard After Effects does not register an `AfterEffects.Application` COM ProgID, this provides reliable zero-config IPC without app restarts.
   - **`COMBridgeBackend`**: Available when a COM bridge proxy is registered, running all COM calls inside a dedicated Single-Threaded Apartment (STA) worker thread with `pythoncom.CoInitialize()`.
   - Both backends enforce strict timeout handling (default 15s) to detect and gracefully bubble modal dialogs or UI hangs rather than freezing the MCP server.

2. **Abstract Bridge Backend (`bridge/backend.py`)**:
   Abstracts script execution behind `BridgeBackend`, allowing alternative execution mechanisms (e.g. WebSocket or CEP panel relays) without altering server logic.

3. **Audio DSP Keyframe Engine (`bridge/audio.py`)**:
   Extracts BPM tempo, musical onsets, prominent energy peaks, and normalized RMS envelopes via `librosa`, `soundfile`, and `scipy`, downsampling keyframe sequences to match composition frame rates.

4. **Automated AI Rotoscoping Pipeline (`bridge/vision.py`)**:
   Bypasses the closed, non-scriptable Roto Brush API by extracting frames using OpenCV, generating foreground alpha mattes locally via `rembg` (U-2-Net), exporting numbered image sequences, importing them into AE, and linking them as Alpha Track Mattes via modern `setTrackMatte()`.

5. **Strict ES3 ExtendScript Library (`extendscript/`)**:
   Enforces ECMAScript 3 compliance (no `let`, `const`, arrow functions, or template strings) and uses language-invariant match names (`ADBE Transform Group`, `ADBE Mask Parade`, etc.) to guarantee zero failures on localized non-English AE installs. Bundles an ES3 `json2.jsx` serializer.

---

## Requirements

- **Operating System**: Windows 10 / 11 (64-bit).
- **Adobe After Effects**: After Effects 2022, 2023, 2024, or 2025+.
- **Python**: Python 3.10 or higher.

---

## ⚠️ Mandatory After Effects Setup

Before running `ae-mcp`, you **must** allow After Effects scripts to perform file and network operations:

1. Launch **Adobe After Effects**.
2. Navigate to **Edit** > **Preferences** > **Scripting & Expressions...**
3. Check the box: **"Allow Scripts to Write Files and Access Network"**.
4. Click **OK**.

*(This is required for importing generated matte sequences and writing temporary files).*

---

## Installation

### 1. Clone or Open the Repository
```bash
cd c:\a1randomshit\ae-mcp
```

### 2. Create Virtual Environment & Install Dependencies
Using `uv` (recommended for speed):
```powershell
uv pip install -r requirements.txt
```

Or using standard `pip`:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Client Configuration

### 1. Claude Desktop Setup

Add `ae-mcp` to your Claude Desktop configuration file:
`%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ae-mcp": {
      "command": "python",
      "args": [
        "c:\\a1randomshit\\ae-mcp\\server.py"
      ],
      "env": {
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

### 2. Antigravity MCP Setup

Add `ae-mcp` to your Antigravity configuration (`%USERPROFILE%\.gemini\antigravity\mcp.json` or workspace configuration):

```json
{
  "mcpServers": {
    "ae-mcp": {
      "command": "python",
      "args": ["c:/a1randomshit/ae-mcp/server.py"],
      "enabled": true
    }
  }
}
```

---

## Available MCP Tools

### 1. `get_active_comp_state()`
Inspects the currently open composition in After Effects.
* **Returns**: JSON object containing:
  - Composition metadata: `name`, `width`, `height`, `frameRate`, `duration`, `workAreaStart`, `workAreaDuration`, `currentTime`, `numLayers`.
  - Layer properties: `index`, `name`, `type` (Footage, Shape, Text, Solid, Camera, Light, Null, Adjustment, Guide), `inPoint`, `outPoint`, `startTime`, `enabled`, `locked`, `shy`, `solo`, `parentIndex`, `sourceFilePath`.
  - `trackMatte`: Status, matte type (`ALPHA`, `LUMA`, etc.), and linked matte layer index.
  - `masks`: List of masks with names, modes (`ADD`, `SUBTRACT`, etc.), vertex counts, feather, and opacity.

### 2. `execute_extendscript(code: str, undo_name: str = "AI Action")`
Executes arbitrary ExtendScript (ES3) in the active session.
* Automatically wraps code in `app.beginUndoGroup(undo_name)` and `app.endUndoGroup()`.
* Automatically bundles ES3 `json2` polyfill and `AEDomHelpers`.
* Bubbles exact line numbers and stack traces on syntax or runtime errors.

### 3. `create_mask_path(layer_index: int, vertices: list[list[float]], ...)`
Injects vector path geometry into `ADBE Mask Parade` on the specified layer using AE's `Shape()` object.
* **Parameters**:
  - `layer_index`: 1-based index of the layer in the active composition.
  - `vertices`: List of `[x, y]` coordinates in Layer Space (e.g. `[[0, 0], [100, 0], [100, 100], [0, 100]]`).
  - `in_tangents`: Optional incoming bezier tangents `[[dx, dy], ...]`.
  - `out_tangents`: Optional outgoing bezier tangents `[[dx, dy], ...]`.
  - `mask_mode`: `"ADD"`, `"SUBTRACT"`, `"INTERSECT"`, `"LIGHTEN"`, `"DARKEN"`, `"DIFFERENCE"`, or `"NONE"`.
  - `feather`: Mask feather `[x, y]` in pixels (default `[0, 0]`).
  - `closed`: Boolean (default `true`).

### 4. `analyze_audio_track(file_path: str, hop_length: int = 512)`
Extracts musical and temporal features from audio for keyframe generation.
* **Parameters**:
  - `file_path`: Path to an audio file (`.wav`, `.mp3`, `.flac`, `.aif`).
  - `hop_length`: FFT hop size (default `512`).
* **Returns**:
  - `bpm`: Estimated musical tempo.
  - `onset_timestamps`: Exact seconds where musical beats or percussive hits occur.
  - `peak_timestamps`: Major energy spike timestamps.
  - `keyframe_data`: Quantized, comp-framerate-aligned keyframes (`times` and `values` normalized to `[0.0, 1.0]`).

### 5. `segment_and_track_matte(layer_index: int, model: str = "rembg", time_range: list[float] = None)`
Automated AI rotoscoping pipeline:
1. Queries After Effects for the source footage path and in/out points of `layer_index`.
2. Extracts video frames using OpenCV across `time_range`.
3. Segments foreground from background using local AI (`rembg` / `u2net`).
4. Exports a high-fidelity alpha PNG sequence.
5. Imports the sequence into After Effects, conforms frame rate, positions it above the source layer, and links it via `setTrackMatte(TrackMatteType.ALPHA)`.

---

## Production Templates (`templates/`)

`ae-mcp` ships with battle-tested ExtendScript templates designed for real-world motion graphics:

1. **`dynamic_lower_third.jsx`**:
   Constructs a dynamic lower-third title graphic. Background shape dimensions automatically adapt to title and subtitle lengths in real-time using `sourceRectAtTime()` expressions with padding, accompanied by smooth cubic-eased intro/outro keyframe animations.

2. **`audio_reactive_scale.jsx`**:
   Creates an `Audio_Amplitude_Controller` guide null with customizable amplitude sliders, threshold gating, and dynamic expressions linked to the target layer's `ADBE Scale`.

3. **`vector_mask_morph.jsx`**:
   Demonstrates non-destructive keyframing of `ADBE Mask Shape` vertices across time, morphing smoothly between distinct geometric polygons (rounded octagon, 4-point star, and diamond shield).

---

## Example Prompts for LLMs

```markdown
"Check the active After Effects comp state and list all text and shape layers."

"Create a dynamic lower third title for 'DR. ELENA ROSTOVA' with subtitle 'DIRECTOR OF PROPULSION' in the open comp."

"Analyze the audio track at C:/Music/beat.wav, extract the BPM and onsets, and animate the Scale property of Layer 2 to pulse on every beat."

"Rotoscope layer 1 from 0 to 4 seconds using rembg and set it as an alpha track matte for the background layer."

"Add a diamond-shaped vector mask to layer 3 with a 15-pixel feather."
```

---

## ExtendScript Rules & Best Practices

All LLMs interacting with this MCP server should follow the guidelines in [`.antigravity/rules.md`](file:///.antigravity/rules.md):
- **ES3 ONLY**: Never emit `let`, `const`, `() => {}`, or template literals.
- **Match Names**: Always use language-invariant match names like `ADBE Transform Group`, `ADBE Position`, `ADBE Root Vectors Group`.
- **Undo Groups**: Always wrap modifications in `app.beginUndoGroup("...")` and `app.endUndoGroup()`.

---

## Running the Test Suite

Run the full automated test suite using `pytest`:

```powershell
pytest -v tests/
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
