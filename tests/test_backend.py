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
