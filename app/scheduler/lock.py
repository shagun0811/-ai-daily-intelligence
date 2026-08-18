"""Prevent two pipeline runs from writing SQLite at the same time."""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType

from app.config.settings import get_settings


class OverlapError(RuntimeError):
    """A pipeline run is already in progress."""


class PipelineLock:
    def __init__(self, path: Path | None = None) -> None:
        settings = get_settings()
        self.path = path or (settings.data_dir / "pipeline.lock")

    def __enter__(self) -> "PipelineLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            previous = self.path.read_text(encoding="utf-8").strip()
            if _pid_is_running(previous):
                raise OverlapError(f"pipeline already running (lock pid={previous or 'unknown'})")
            self.path.unlink(missing_ok=True)
        self.path.write_text(str(os.getpid()), encoding="utf-8")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


def _pid_is_running(raw_pid: str) -> bool:
    try:
        pid = int(raw_pid)
    except ValueError:
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_pid_exists(pid)
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _windows_pid_exists(pid: int) -> bool:
    """Query whether a PID exists without signaling it. os.kill is unsafe on Windows."""
    import ctypes

    SYNCHRONIZE = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    return False
