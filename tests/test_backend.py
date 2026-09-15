"""
Unit tests for BridgeBackend, AEDispatcher, and exception hierarchy.
"""

import pytest
from typing import Optional
from bridge.backend import (
    BridgeBackend,
    AEBridgeError,
    AENotRunningError,
    AETimeoutError,
    AEScriptExecutionError,
    AECOMError,
)
from bridge.ae_dispatch import AEDispatcher


class MockBridgeBackend(BridgeBackend):
    """Mock backend that simulates ExtendScript execution responses."""

    def __init__(self, response_map=None, default_response=""):
        self.response_map = response_map or {}
        self.default_response = default_response
        self.connected = True
        self.execution_log = []

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def is_alive(self) -> bool:
        return self.connected

    def get_version(self) -> str:
        return "25.0"

    def execute(self, script: str, timeout: Optional[float] = None) -> str:
        self.execution_log.append((script, timeout))
        if not self.connected:
            raise AENotRunningError("Mock AE is not connected.")
        
        # Check simulated errors
        if "SIMULATE_TIMEOUT" in script:
            raise AETimeoutError("Mock timeout exceeded.")
        if "SIMULATE_COM_ERROR" in script:
            raise AECOMError("Mock COM failure.", hresult=-2147418111)

        # Return predefined response or a simulated successful JSON envelope
        for trigger, resp in self.response_map.items():
            if trigger in script:
                return resp

        # Return default response if provided, otherwise generic success envelope
        if self.default_response:
            return self.default_response
        return '{"status": "success", "result": "mock_ok"}'


def test_exception_hierarchy():
    """Verify custom exception inheritance and string formatting."""
    assert issubclass(AENotRunningError, AEBridgeError)
    assert issubclass(AETimeoutError, AEBridgeError)
    assert issubclass(AEScriptExecutionError, AEBridgeError)
    assert issubclass(AECOMError, AEBridgeError)

    err = AEScriptExecutionError("Syntax error", line=42, stack="Error at line 42")
    assert "line 42" in str(err)
    assert "Stack trace" in str(err)

    com_err = AECOMError("Call rejected", hresult=-2147418111)
    assert "0x80010001" in str(com_err)


def test_dispatcher_success():
    """Verify AEDispatcher correctly parses success envelope."""
    backend = MockBridgeBackend({
        "my_test_func": '{"status": "success", "result": {"comp_id": 1, "name": "MainComp"}}'
    })
    dispatcher = AEDispatcher(backend=backend)

    result = dispatcher.execute_with_undo("my_test_func();", undo_name="Test Action")
    assert result == {"comp_id": 1, "name": "MainComp"}
    assert len(backend.execution_log) == 1
    assert "Test Action" in backend.execution_log[0][0]


def test_dispatcher_error_unboxing():
    """Verify AEDispatcher bubbles ExtendScript errors into AEScriptExecutionError."""
    backend = MockBridgeBackend({
        "fail_func": '{"status": "error", "message": "ReferenceError: foo is not defined", "line": 15, "stack": "test.jsx:15"}'
    })
    dispatcher = AEDispatcher(backend=backend)

    with pytest.raises(AEScriptExecutionError) as exc_info:
        dispatcher.execute_with_undo("fail_func();")

    assert "ReferenceError: foo is not defined" in str(exc_info.value)
    assert exc_info.value.line == 15
    assert exc_info.value.stack == "test.jsx:15"


def test_dispatcher_timeout_handling():
    """Verify dispatcher propagates timeout errors."""
    backend = MockBridgeBackend()
    dispatcher = AEDispatcher(backend=backend)

    with pytest.raises(AETimeoutError):
        dispatcher.execute_with_undo("SIMULATE_TIMEOUT")


def test_dispatcher_com_error_handling():
    """Verify dispatcher propagates COM errors."""
    backend = MockBridgeBackend()
    dispatcher = AEDispatcher(backend=backend)

    with pytest.raises(AECOMError):
        dispatcher.execute_with_undo("SIMULATE_COM_ERROR")


def test_find_afterfx_executable_env(monkeypatch, tmp_path):
    """Verify AFTER_EFFECTS_PATH environment variable is respected."""
    from bridge.ae_dispatch import find_afterfx_executable

    fake_ae = tmp_path / "AfterFX.exe"
    fake_ae.write_text("fake binary")

    monkeypatch.setenv("AFTER_EFFECTS_PATH", str(fake_ae))
    found = find_afterfx_executable()
    assert found == str(fake_ae)


def test_is_ae_running():
    """Verify is_ae_running returns a boolean without throwing."""
    from bridge.ae_dispatch import is_ae_running
    assert isinstance(is_ae_running(), bool)


def test_create_default_backend():
    """Verify create_default_backend returns a valid BridgeBackend instance."""
    from bridge.ae_dispatch import create_default_backend
    backend = create_default_backend()
    assert isinstance(backend, BridgeBackend)


def test_cli_backend_not_running(monkeypatch):
    """Verify CLIBridgeBackend raises AENotRunningError when AE is not running."""
    from bridge.ae_dispatch import CLIBridgeBackend
    import bridge.ae_dispatch as dispatch_module

    monkeypatch.setattr(dispatch_module, "is_ae_running", lambda: False)

    backend = CLIBridgeBackend()
    with pytest.raises(AENotRunningError):
        backend.connect()

    with pytest.raises(AENotRunningError):
        backend.execute("return 1;")


def test_cli_backend_execute_success(monkeypatch, tmp_path):
    """Verify CLIBridgeBackend creates temporary JSX and reads output JSON successfully."""
    from bridge.ae_dispatch import CLIBridgeBackend
    import bridge.ae_dispatch as dispatch_module
    import subprocess
    import json

    monkeypatch.setattr(dispatch_module, "is_ae_running", lambda: True)

    fake_ae = tmp_path / "AfterFX.exe"
    fake_ae.write_text("fake binary")

    backend = CLIBridgeBackend(ae_path=str(fake_ae), default_timeout=5.0)

    def mock_subprocess_run(cmd, capture_output=True, text=True, timeout=10.0, check=False):
        # cmd = [ae_path, "-r", input_jsx]
        input_jsx_path = cmd[2]
        # Inspect input_jsx to find output_json path
        with open(input_jsx_path, "r", encoding="utf-8") as f:
            jsx_content = f.read()
        import re
        m = re.search(r'new File\("([^"]+)"\)', jsx_content)
        if m:
            out_path = m.group(1)
            with open(out_path, "w", encoding="utf-8") as out_f:
                out_f.write(json.dumps({"status": "success", "result": 12345}))
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    res = backend.execute("return 12345;", timeout=5.0)
    assert res is not None
    data = json.loads(res)
    assert data.get("result") == 12345
