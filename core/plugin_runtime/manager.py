"""Isolated plugin worker subprocess manager with JSON-RPC over stdio."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Protocol, cast

_ALLOWED_ENV = ("SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "PATH", "PATHEXT")


class WorkerError(RuntimeError):
    pass


class WorkerTimeout(WorkerError):
    pass


class WorkerCrashed(WorkerError):
    pass


@dataclass(frozen=True)
class WorkerIdentity:
    plugin_id: str
    version: str
    channel_id: str


def worker_environment(
    identity: WorkerIdentity, source: Mapping[str, str] | None = None
) -> dict[str, str]:
    source = os.environ if source is None else source
    env = {key: source[key] for key in _ALLOWED_ENV if key in source}
    env.update(
        {
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "YG_PLUGIN_ID": identity.plugin_id,
            "YG_PLUGIN_VERSION": identity.version,
            "YG_CHANNEL_ID": identity.channel_id,
        }
    )
    return env


class WorkerProcess:
    def __init__(
        self,
        command: list[str],
        identity: WorkerIdentity,
        *,
        cwd: Path,
        timeout: float = 30.0,
        idle_timeout: float = 300.0,
    ) -> None:
        self.command = command
        self.identity = identity
        self.cwd = cwd
        self.timeout = timeout
        self.idle_timeout = idle_timeout
        self.process: subprocess.Popen[str] | None = None
        self._next_id = 1
        self._last_used = time.monotonic()
        self._job: object | None = None

    def start(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return
        self.process = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            env=worker_environment(self.identity),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._job = _attach_kill_on_close_job(self.process)

    def call(self, method: str, params: dict[str, Any]) -> Any:
        self.start()
        process = self.process
        assert process is not None
        if process.poll() is not None:
            raise WorkerCrashed(f"worker exited with code {process.returncode}")
        request_id = self._next_id
        self._next_id += 1
        request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        assert process.stdin is not None
        try:
            process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise WorkerCrashed("worker pipe closed") from exc
        line = self._readline_with_timeout(process, self.timeout)
        self._last_used = time.monotonic()
        response = json.loads(line)
        if response.get("id") != request_id or response.get("jsonrpc") != "2.0":
            raise WorkerError("invalid JSON-RPC response")
        if "error" in response:
            raise WorkerError(str(response["error"]))
        return response.get("result")

    def shutdown_if_idle(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        if self.process is not None and now - self._last_used >= self.idle_timeout:
            self.close()
            return True
        return False

    def close(self) -> None:
        process, self.process = self.process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        _close_job(self._job)
        self._job = None

    def _readline_with_timeout(self, process: subprocess.Popen[str], timeout: float) -> str:
        assert process.stdout is not None
        result: list[str] = []
        error: list[BaseException] = []

        stdout: IO[str] = process.stdout

        def read() -> None:
            try:
                result.append(stdout.readline())
            except BaseException as exc:
                error.append(exc)

        thread = threading.Thread(target=read, daemon=True)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            self.close()
            raise WorkerTimeout(f"worker call exceeded {timeout:.3f}s")
        if error:
            raise WorkerCrashed("worker stdout failed") from error[0]
        if not result or result[0] == "":
            code = process.poll()
            raise WorkerCrashed(f"worker exited unexpectedly ({code})")
        return result[0]


class _WindowsPopen(Protocol):
    _handle: int


def _windows_process_handle(process: subprocess.Popen[str]) -> int:
    handle = getattr(process, "_handle", None)
    if not isinstance(handle, int):
        raise WorkerError("Windows subprocess handle unavailable")
    return cast(_WindowsPopen, process)._handle


def _attach_kill_on_close_job(process: subprocess.Popen[str]) -> object | None:
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise WorkerError("CreateJobObjectW failed")

    class BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [("ReadOperationCount", ctypes.c_ulonglong)] * 6

    class ExtendedLimit(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimit),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    info = ExtendedLimit()
    info.BasicLimitInformation.LimitFlags = 0x00002000
    if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        kernel32.CloseHandle(job)
        raise WorkerError("SetInformationJobObject failed")
    process_handle = wintypes.HANDLE(_windows_process_handle(process))
    if not kernel32.AssignProcessToJobObject(job, process_handle):
        kernel32.CloseHandle(job)
        raise WorkerError("AssignProcessToJobObject failed")
    return int(job)


def _close_job(job: object | None) -> None:
    if job is not None and os.name == "nt":
        import ctypes

        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(job)
