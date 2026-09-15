"""
Thread-Safe COM Execution Wrapper for Adobe After Effects.
Uses pywin32 to invoke DoScript() on an active After Effects session
with explicit timeout handling, modal dialog detection, auto-reconnect,
and structured error bubbling.
"""

import os
import sys
import json
import time
import queue
import logging
import threading
import subprocess
import tempfile
from typing import Any, Dict, Optional, Tuple, Union

try:
    import win32com.client
    import pythoncom
    import pywintypes
    HAS_PYWIN32 = True
except ImportError:
    HAS_PYWIN32 = False

from .backend import (
    BridgeBackend,
    AEBridgeError,
    AENotRunningError,
    AETimeoutError,
    AEScriptExecutionError,
    AECOMError,
)

logger = logging.getLogger("ae_mcp.bridge.ae_dispatch")

# Known COM HRESULT constants
RPC_E_CALL_REJECTED = -2147418111       # 0x80010001
RPC_E_SERVERCALL_RETRYLATER = -2147417846 # 0x8001010A
RPC_E_DISCONNECTED = -2147417848        # 0x80010108
CO_E_NOTINITIALIZED = -2147221008       # 0x800401F0
DISP_E_UNKNOWNNAME = -2147352570        # 0x80020006


class _COMTask:
    """Internal task item for COM worker thread."""
    def __init__(self, action: str, payload: Any = None):
        self.action = action
        self.payload = payload
        self.result_event = threading.Event()
        self.result: Any = None
        self.exception: Optional[Exception] = None


class COMBridgeBackend(BridgeBackend):
    """
    Production-grade Windows COM bridge for Adobe After Effects.
    Runs all COM interactions in a dedicated single-threaded apartment (STA)
    worker thread to prevent UI hangs, isolate COM apartment state,
    and enforce strict timeout policies when modal dialogs are open.
    """

    DEFAULT_TIMEOUT: float = 15.0  # seconds

    def __init__(self, app_id: str = "AfterEffects.Application", default_timeout: float = DEFAULT_TIMEOUT):
        self.app_id = app_id
        self.default_timeout = default_timeout
        self._worker_thread: Optional[threading.Thread] = None
        self._task_queue: "queue.Queue[Optional[_COMTask]]" = queue.Queue()
        self._lock = threading.Lock()
        self._is_connected = False
        self._version_cache: Optional[str] = None
        self._start_worker()

    def _start_worker(self) -> None:
        """Start the dedicated COM worker thread."""
        with self._lock:
            if self._worker_thread and self._worker_thread.is_alive():
                return
            self._task_queue = queue.Queue()
            self._worker_thread = threading.Thread(
                target=self._com_worker_loop,
                name="AfterEffects-COM-Worker",
                daemon=True,
            )
            self._worker_thread.start()

    def _com_worker_loop(self) -> None:
        """Worker thread loop maintaining COM STA apartment."""
        if not HAS_PYWIN32:
            logger.error("pywin32 is not installed. COM backend will be unavailable.")
            return

        pythoncom.CoInitialize()
        ae_app = None

        try:
            while True:
                task = self._task_queue.get()
                if task is None:
                    # Termination sentinel
                    break

                try:
                    if task.action == "connect":
                        ae_app = self._internal_connect()
                        task.result = True

                    elif task.action == "disconnect":
                        ae_app = None
                        task.result = True

                    elif task.action == "is_alive":
                        task.result = self._internal_is_alive(ae_app)

                    elif task.action == "get_version":
                        if ae_app is None or not self._internal_is_alive(ae_app):
                            ae_app = self._internal_connect()
                        version_script = "app.version;"
                        raw = ae_app.DoScript(version_script)
                        task.result = str(raw).strip()

                    elif task.action == "execute":
                        script = task.payload
                        if ae_app is None or not self._internal_is_alive(ae_app):
                            ae_app = self._internal_connect()
                        raw_result = ae_app.DoScript(script)
                        task.result = str(raw_result) if raw_result is not None else ""

                    else:
                        task.exception = ValueError(f"Unknown task action: {task.action}")

                except pywintypes.com_error as ce:
                    hr = ce.hresult if hasattr(ce, "hresult") else None
                    msg = str(ce)
                    if hr in (RPC_E_CALL_REJECTED, RPC_E_SERVERCALL_RETRYLATER):
                        task.exception = AETimeoutError(
                            "After Effects is busy or a modal dialog is open. "
                            "Please dismiss any alerts/dialogs in After Effects and try again."
                        )
                    elif hr == RPC_E_DISCONNECTED:
                        task.exception = AENotRunningError("After Effects session disconnected or terminated.")
                        ae_app = None
                    else:
                        task.exception = AECOMError(f"COM error invoking After Effects: {msg}", hresult=hr)
                except Exception as ex:
                    task.exception = ex
                finally:
                    task.result_event.set()
        finally:
            ae_app = None
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    def _internal_connect(self) -> Any:
        """Connect to active or registered After Effects instance."""
        if not HAS_PYWIN32:
            raise AECOMError("pywin32 (win32com) is not installed on this system.")

        try:
            # Try to dispatch to running or registered AfterEffects.Application
            app = win32com.client.Dispatch(self.app_id)
            # Verify communication with a lightweight ping
            _ = app.version
            self._is_connected = True
            return app
        except pywintypes.com_error as ce:
            self._is_connected = False
            hr = getattr(ce, "hresult", None)
            raise AENotRunningError(
                f"Could not connect to Adobe After Effects ({self.app_id}). "
                "Ensure After Effects is running on this Windows machine."
            ) from ce
        except Exception as e:
            self._is_connected = False
            raise AENotRunningError(f"Failed to initialize After Effects COM dispatch: {e}") from e

    def _internal_is_alive(self, ae_app: Any) -> bool:
        """Check if an existing COM object can respond to a ping."""
        if ae_app is None:
            return False
        try:
            _ = ae_app.version
            return True
        except Exception:
            return False

    def _dispatch_task(self, action: str, payload: Any = None, timeout: Optional[float] = None) -> Any:
        """Submit a task to the worker thread and wait for completion with timeout."""
        effective_timeout = timeout if timeout is not None else self.default_timeout

        # Ensure worker is alive
        if not self._worker_thread or not self._worker_thread.is_alive():
            self._start_worker()

        task = _COMTask(action, payload)
        self._task_queue.put(task)

        finished = task.result_event.wait(timeout=effective_timeout)
        if not finished:
            # The COM call is blocked, likely due to a modal dialog or UI lockup in AE
            logger.warning("COM task '%s' timed out after %s seconds.", action, effective_timeout)
            # Flag connection as suspect and restart worker loop so future calls don't deadlock
            self._recycle_worker()
            raise AETimeoutError(
                f"After Effects failed to respond within {effective_timeout}s. "
                "A modal dialog (e.g. Save, Render, Missing Footage, Preferences) or UI hang "
                "is likely blocking the main thread. Please switch to After Effects and dismiss any open dialogs."
            )

        if task.exception is not None:
            raise task.exception

        return task.result

    def _recycle_worker(self) -> None:
        """Forcibly discard the old worker queue and launch a clean worker thread."""
        with self._lock:
            # Tell old thread to terminate if it ever unblocks
            try:
                self._task_queue.put_nowait(None)
            except Exception:
                pass
            self._is_connected = False
            self._start_worker()

    def connect(self) -> None:
        """Establish connection to After Effects."""
        self._dispatch_task("connect", timeout=self.default_timeout)

    def disconnect(self) -> None:
        """Release COM dispatch connection."""
        try:
            self._dispatch_task("disconnect", timeout=3.0)
        except Exception:
            pass
        self._is_connected = False

    def is_alive(self) -> bool:
        """Check if active After Effects connection is responsive."""
        try:
            return bool(self._dispatch_task("is_alive", timeout=3.0))
        except Exception:
            return False

    def get_version(self) -> str:
        """Retrieve After Effects version string."""
        if self._version_cache:
            return self._version_cache
        version = self._dispatch_task("get_version", timeout=5.0)
        self._version_cache = version
        return version

    def execute(self, script: str, timeout: Optional[float] = None) -> str:
        """
        Execute raw ExtendScript code in After Effects.
        """
        return self._dispatch_task("execute", payload=script, timeout=timeout)


def find_afterfx_executable() -> Optional[str]:
    """Auto-detect AfterFX.exe location via env, registry, or standard directories."""
    env_path = os.environ.get("AFTER_EFFECTS_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    if sys.platform == "win32":
        try:
            import winreg
            for reg_sub in [
                r"AfterEffects.Project.25\protocol\StdFileEditing\server",
                r"AfterEffects.Project.24\protocol\StdFileEditing\server",
                r"AfterEffects.Project.23\protocol\StdFileEditing\server",
                r"AfterEffects.Project\protocol\StdFileEditing\server",
            ]:
                try:
                    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, reg_sub) as key:
                        val, _ = winreg.QueryValueEx(key, "")
                        if val and os.path.isfile(val):
                            return val
                except (FileNotFoundError, OSError):
                    continue
        except Exception:
            pass

    candidates = [
        r"C:\Program Files\Adobe\Adobe After Effects 2025\Support Files\AfterFX.exe",
        r"C:\Program Files\Adobe\Adobe After Effects 2024\Support Files\AfterFX.exe",
        r"C:\Program Files\Adobe\Adobe After Effects 2023\Support Files\AfterFX.exe",
        r"C:\Program Files\Adobe\Adobe After Effects 2022\Support Files\AfterFX.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def is_ae_running() -> bool:
    """Check if After Effects (AfterFX.exe) process is currently running."""
    try:
        import psutil
        for proc in psutil.process_iter(["name"]):
            name = proc.info.get("name")
            if name and "afterfx" in name.lower():
                return True
    except Exception:
        try:
            res = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq AfterFX.exe"],
                capture_output=True,
                text=True,
                check=False
            )
            return "AfterFX.exe" in res.stdout
        except Exception:
            pass
    return False


class CLIBridgeBackend(BridgeBackend):
    """
    Production-grade Windows CLI IPC bridge for Adobe After Effects.
    Communicates with AfterFX.exe using the '-r' flag and atomic temporary files
    for ExtendScript execution and JSON result retrieval.
    """

    DEFAULT_TIMEOUT: float = 15.0

    def __init__(self, ae_path: Optional[str] = None, default_timeout: float = DEFAULT_TIMEOUT):
        self.ae_path = ae_path or find_afterfx_executable()
        self.default_timeout = default_timeout
        self._version_cache: Optional[str] = None
        self._lock = threading.Lock()
        self._ipc_dir = os.path.join(tempfile.gettempdir(), "ae_mcp_ipc")
        os.makedirs(self._ipc_dir, exist_ok=True)

    def connect(self) -> None:
        if not self.is_alive():
            raise AENotRunningError(
                "Adobe After Effects is not currently running. "
                "Please launch Adobe After Effects and open a composition."
            )

    def disconnect(self) -> None:
        pass

    def is_alive(self) -> bool:
        return is_ae_running()

    def get_version(self) -> str:
        if self._version_cache:
            return self._version_cache
        if self.is_alive():
            try:
                res = self.execute("return app.version;", timeout=5.0)
                if res and res.strip():
                    self._version_cache = res.strip().strip('"')
                    return self._version_cache
            except Exception:
                pass
        return "25.0"

    def execute(self, script: str, timeout: Optional[float] = None) -> str:
        effective_timeout = timeout if timeout is not None else self.default_timeout

        if not self.is_alive():
            raise AENotRunningError(
                "Adobe After Effects is not currently running. "
                "Please launch Adobe After Effects and open a composition."
            )

        if not self.ae_path or not os.path.isfile(self.ae_path):
            raise AENotRunningError(
                f"After Effects executable not found at: {self.ae_path}. "
                "Please verify your Adobe After Effects installation."
            )

        with self._lock:
            task_id = f"{int(time.time() * 1000)}_{threading.get_ident()}"
            input_jsx = os.path.join(self._ipc_dir, f"cmd_{task_id}.jsx")
            output_json = os.path.join(self._ipc_dir, f"out_{task_id}.json")
            escaped_out_path = output_json.replace("\\", "/")

            encoded_script = json.dumps(script)
            wrapper_jsx = f"""(function() {{
    var __out = new File("{escaped_out_path}");
    try {{
        if (!__out.parent.exists) {{
            __out.parent.create();
        }}
        var __raw = eval({encoded_script});
        __out.encoding = "UTF-8";
        __out.open("w");
        if (__raw !== undefined && __raw !== null) {{
            __out.write(typeof __raw === "string" ? __raw : String(__raw));
        }} else {{
            __out.write('{{"status":"success","result":null}}');
        }}
        __out.close();
    }} catch (err) {{
        try {{
            __out.encoding = "UTF-8";
            __out.open("w");
            var cleanErr = err.toString().replace(/\\\\/g, "\\\\\\\\").replace(/"/g, '\\\\"');
            __out.write('{{"status":"error","message":"' + cleanErr + '"}}');
            __out.close();
        }} catch(e) {{}}
    }}
}})();
"""
            try:
                with open(input_jsx, "w", encoding="utf-8") as f:
                    f.write(wrapper_jsx)

                try:
                    p = subprocess.Popen(
                        [self.ae_path, "-r", input_jsx],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    try:
                        p.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        pass
                except Exception as e:
                    raise AEBridgeError(f"Failed to invoke AfterFX.exe: {e}") from e

                start_time = time.time()
                while time.time() - start_time < effective_timeout:
                    if os.path.isfile(output_json) and os.path.getsize(output_json) > 0:
                        time.sleep(0.05)
                        try:
                            with open(output_json, "r", encoding="utf-8") as out_f:
                                content = out_f.read()
                            if content.strip():
                                return content
                        except Exception:
                            pass
                    time.sleep(0.1)

                raise AETimeoutError(
                    f"After Effects did not respond within {effective_timeout}s. "
                    "Ensure 'Allow Scripts to Write Files and Access Network' is enabled in "
                    "Edit > Preferences > Scripting & Expressions, and check for open modal dialogs."
                )
            finally:
                for p in (input_jsx, output_json):
                    if os.path.isfile(p):
                        try:
                            os.remove(p)
                        except OSError:
                            pass


def create_default_backend() -> BridgeBackend:
    """
    Auto-detect the optimal execution backend for the current environment.
    Uses COM if registered, otherwise falls back to the native Windows CLI IPC backend.
    """
    if HAS_PYWIN32:
        try:
            import win32com.client
            _ = win32com.client.Dispatch("AfterEffects.Application")
            return COMBridgeBackend()
        except Exception:
            pass
    return CLIBridgeBackend()


class AEDispatcher:
    """
    High-level After Effects dispatcher and ExtendScript execution manager.
    Wraps scripts with ES3-compatible JSON serialization, undo groups,
    and automatic error unboxing.
    """

    def __init__(self, backend: Optional[BridgeBackend] = None):
        self.backend: BridgeBackend = backend or create_default_backend()

    def execute_with_undo(
        self,
        code: str,
        undo_name: str = "AI Action",
        timeout: Optional[float] = None
    ) -> Any:
        """
        Wrap arbitrary ExtendScript code in an undo group and try/catch block,
        executing it safely and returning parsed JSON results.

        Args:
            code: ExtendScript source code to execute.
            undo_name: Name that will appear in After Effects' Edit > Undo menu.
            timeout: Execution timeout in seconds.

        Returns:
            The parsed result (dict, list, str, number, bool, or None) returned by the script.

        Raises:
            AEScriptExecutionError: If the script threw an exception in AE.
            AETimeoutError: If execution timed out.
            AENotRunningError: If AE is not reachable.
        """
        # Embed a compact ES3 JSON serializer and error envelope
        wrapped_script = self._build_execution_envelope(code, undo_name)
        raw_output = self.backend.execute(wrapped_script, timeout=timeout)

        if not raw_output or raw_output.strip() == "":
            return None

        try:
            envelope = json.loads(raw_output)
        except json.JSONDecodeError:
            # If output is not JSON, return as raw string
            return raw_output

        if isinstance(envelope, dict):
            status = envelope.get("status")
            if status == "error":
                err_msg = envelope.get("message", "Unknown ExtendScript error")
                line = envelope.get("line")
                stack = envelope.get("stack")
                raise AEScriptExecutionError(err_msg, line=line, stack=stack)
            elif status == "success":
                return envelope.get("result")

        return envelope

    @staticmethod
    def _build_execution_envelope(code: str, undo_name: str) -> str:
        """
        Build an ES3-compatible wrapper around the user script.
        Includes a lightweight ES3 JSON stringifier so native JSON is not required.
        """
        # Clean undo name
        clean_undo = undo_name.replace('"', '\\"').replace("\n", " ")

        return f"""
(function() {{
    // Lightweight ES3 JSON serializer
    var JSON3 = (function() {{
        function esc(s) {{
            return '"' + s.replace(/\\\\/g, '\\\\\\\\')
                           .replace(/"/g, '\\\\"')
                           .replace(/\\n/g, '\\\\n')
                           .replace(/\\r/g, '\\\\r')
                           .replace(/\\t/g, '\\\\t') + '"';
        }}
        function str(val) {{
            if (val === null || val === undefined) return 'null';
            if (typeof val === 'number' || typeof val === 'boolean') return String(val);
            if (typeof val === 'string') return esc(val);
            if (val instanceof Array) {{
                var res = [];
                for (var i = 0; i < val.length; i++) {{
                    res.push(str(val[i]));
                }}
                return '[' + res.join(',') + ']';
            }}
            if (typeof val === 'object') {{
                var pairs = [];
                for (var k in val) {{
                    if (val.hasOwnProperty(k)) {{
                        pairs.push(esc(String(k)) + ':' + str(val[k]));
                    }}
                }}
                return '{{' + pairs.join(',') + '}}';
            }}
            return 'null';
        }}
        return {{ stringify: str }};
    }})();

    try {{
        if (!app.project) {{
            return JSON3.stringify({{
                status: "error",
                message: "No active project open in Adobe After Effects.",
                line: 0,
                stack: "app.project is null"
            }});
        }}

        app.beginUndoGroup("{clean_undo}");

        var __userResult = (function() {{
{code}
        }})();

        app.endUndoGroup();

        return JSON3.stringify({{
            status: "success",
            result: __userResult !== undefined ? __userResult : null
        }});
    }} catch (err) {{
        try {{
            app.endUndoGroup();
        }} catch(e) {{}}

        return JSON3.stringify({{
            status: "error",
            message: err.toString(),
            line: err.line ? err.line : null,
            stack: err.stack ? err.stack : (err.fileName ? (err.fileName + ":" + err.line) : err.toString())
        }});
    }}
}})();
"""
