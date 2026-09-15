"""
BridgeBackend Abstract Base Class & Error Hierarchy for After Effects IPC.
Provides a vendor-agnostic interface for executing ExtendScript code
via COM, WebSockets, or socket-based panel relays.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class AEBridgeError(Exception):
    """Base exception for all After Effects bridge errors."""
    pass


class AENotRunningError(AEBridgeError):
    """Raised when Adobe After Effects is not running or COM server is unavailable."""
    pass


class AETimeoutError(AEBridgeError):
    """Raised when an ExtendScript execution times out (e.g. modal dialog blocking or hang)."""
    pass


class AEScriptExecutionError(AEBridgeError):
    """Raised when ExtendScript execution fails with an error in After Effects."""
    def __init__(self, message: str, line: Optional[int] = None, stack: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.stack = stack

    def __str__(self) -> str:
        line_info = f" (line {self.line})" if self.line is not None else ""
        stack_info = f"\nStack trace:\n{self.stack}" if self.stack else ""
        return f"{self.message}{line_info}{stack_info}"


class AECOMError(AEBridgeError):
    """Raised when an underlying Windows COM dispatch failure occurs."""
    def __init__(self, message: str, hresult: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.hresult = hresult

    def __str__(self) -> str:
        hr_info = f" [HRESULT: 0x{self.hresult & 0xFFFFFFFF:08X}]" if self.hresult is not None else ""
        return f"{self.message}{hr_info}"


class BridgeBackend(ABC):
    """
    Abstract base class for After Effects script execution backends.
    Allows swappable IPC mechanisms (COM, WebSocket CEP relay, TCP socket).
    """

    @abstractmethod
    def connect(self) -> None:
        """Establish or verify connection to the After Effects session."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect and release resources."""
        pass

    @abstractmethod
    def is_alive(self) -> bool:
        """Check if the backend is actively connected to After Effects."""
        pass

    @abstractmethod
    def execute(self, script: str, timeout: Optional[float] = None) -> str:
        """
        Execute an ExtendScript string and return the raw string result.

        Args:
            script: The ExtendScript code string to execute.
            timeout: Maximum execution time in seconds.

        Returns:
            The raw string returned by After Effects.

        Raises:
            AENotRunningError: If After Effects is not reachable.
            AETimeoutError: If execution exceeds the timeout limit.
            AEScriptExecutionError: If script encounters an uncaught error.
            AECOMError: If an IPC transport error occurs.
        """
        pass

    @abstractmethod
    def get_version(self) -> str:
        """Return the After Effects version string (e.g. '25.0')."""
        pass
