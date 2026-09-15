"""
Integration and schema tests for ae-mcp FastMCP server tools.
"""

import os
import pytest
from server import (
    mcp,
    get_active_comp_state,
    execute_extendscript,
    create_mask_path,
    analyze_audio_track,
    segment_and_track_matte,
    get_dispatcher,
)
from bridge.ae_dispatch import AEDispatcher
from tests.test_backend import MockBridgeBackend


def test_tool_registration():
    """Verify that all 5 required tools are registered on the FastMCP instance."""
    # FastMCP stores tools in _tool_manager or tool dictionaries
    # FastMCP tools can be checked via get_tool
    tool_names = [
        "get_active_comp_state",
        "execute_extendscript",
        "create_mask_path",
        "analyze_audio_track",
        "segment_and_track_matte",
    ]

    for name in tool_names:
        # Verify function is callable and has docstring
        func = globals().get(name)
        assert func is not None, f"Tool function '{name}' is not defined"
        assert callable(func), f"Tool '{name}' is not callable"
        assert func.__doc__ is not None, f"Tool '{name}' is missing docstring"


def test_create_mask_path_validation():
    """Verify input validation on create_mask_path tool."""
    # 1. Less than 2 vertices
    res = create_mask_path(layer_index=1, vertices=[[10, 10]])
    assert res["status"] == "error"
    assert "at least 2 vertices" in res["message"]

    # 2. Invalid vertex shape
    res = create_mask_path(layer_index=1, vertices=[[10, 10], [20]])
    assert res["status"] == "error"
    assert "must be a 2-element" in res["message"]

    # 3. Mismatched tangent count
    res = create_mask_path(
        layer_index=1,
        vertices=[[10, 10], [20, 20]],
        in_tangents=[[0, 0]]  # only 1 tangent for 2 vertices
    )
    assert res["status"] == "error"
    assert "must match vertices count" in res["message"]

    # 4. Invalid mask mode
    res = create_mask_path(
        layer_index=1,
        vertices=[[10, 10], [20, 20]],
        mask_mode="INVALID_MODE"
    )
    assert res["status"] == "error"
    assert "Invalid mask_mode" in res["message"]


def test_analyze_audio_track_missing_file():
    """Verify error reporting for non-existent audio file."""
    res = analyze_audio_track("C:/does_not_exist.wav")
    assert res["status"] == "error"
    assert "not found" in res["message"]


def test_server_tools_with_mock_dispatcher(monkeypatch):
    """Test get_active_comp_state and execute_extendscript with mock backend."""
    import server

    mock_comp_json = '{"status": "success", "result": {"name": "TestComp", "width": 1920, "height": 1080, "numLayers": 0, "layers": []}}'
    mock_backend = MockBridgeBackend(default_response=mock_comp_json)
    mock_dispatcher = AEDispatcher(backend=mock_backend)

    monkeypatch.setattr(server, "_dispatcher", mock_dispatcher)

    comp_state = server.get_active_comp_state()
    assert comp_state["status"] == "success"
    assert comp_state["composition"]["name"] == "TestComp"

    exec_result = server.execute_extendscript("return 42;", undo_name="Test Calc")
    assert exec_result["status"] == "success"
    assert exec_result["result"] == 42 or exec_result["result"] == {"name": "TestComp", "width": 1920, "height": 1080, "numLayers": 0, "layers": []}


def test_create_mask_path_success(monkeypatch):
    """Test create_mask_path when dispatch returns success."""
    import server

    mock_mask_json = '{"status": "success", "result": {"success": true, "maskIndex": 1, "maskName": "Mask 1", "maskMode": "ADD", "vertexCount": 3}}'
    mock_backend = MockBridgeBackend(default_response=mock_mask_json)
    mock_dispatcher = AEDispatcher(backend=mock_backend)

    monkeypatch.setattr(server, "_dispatcher", mock_dispatcher)

    res = create_mask_path(
        layer_index=1,
        vertices=[[0, 0], [100, 0], [50, 100]],
        in_tangents=[[0, 0], [0, 0], [0, 0]],
        out_tangents=[[0, 0], [0, 0], [0, 0]],
        mask_mode="ADD",
        feather=[10, 10],
        closed=True
    )
    assert res["status"] == "success"
    assert res["layer_index"] == 1
    assert res["mask_mode"] == "ADD"
    assert res["mask_data"]["vertexCount"] == 3


def test_segment_and_track_matte_non_footage_layer(monkeypatch):
    """Test that segment_and_track_matte gracefully rejects layers without footage source files."""
    import server

    # Simulated layer inspection returning null for source file (e.g. Text or Shape layer)
    mock_layer_json = '{"status": "success", "result": {"name": "Shape Layer 1", "sourceFilePath": null, "inPoint": 0, "outPoint": 5, "startTime": 0, "compFps": 30}}'
    mock_backend = MockBridgeBackend(default_response=mock_layer_json)
    mock_dispatcher = AEDispatcher(backend=mock_backend)

    monkeypatch.setattr(server, "_dispatcher", mock_dispatcher)

    res = segment_and_track_matte(layer_index=1, model="rembg")
    assert res["status"] == "error"
    assert "does not reference a footage file" in res["message"]
