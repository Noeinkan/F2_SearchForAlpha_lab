"""
Stop requests: how ``sfa kill`` asks a running paper runner to stop.

A signal cannot do this job on Windows. There, ``os.kill(pid, SIGTERM)`` is
TerminateProcess, which ends the process on the spot: no order cancelled, no
position closed, no clean disconnect. So ``sfa kill`` writes a small request
file next to the PID file and waits. The runner's heartbeat picks it up, stops
itself (closing its position first when ``flatten`` is set), writes what it did
to a result file, and exits. Only a runner that does not answer is terminated
the hard way.

Files, all under ``state/running/``:

    <name>.pid           written by the runner at start (lib.store.state)
    <name>.stop.json     the request, written by sfa kill, removed by the runner
    <name>.stopped.json  the outcome, written by the runner, removed by sfa kill
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from lib.store import state as state_store


def _dir(pid_dir: Path | None) -> Path:
    return Path(pid_dir) if pid_dir else state_store.PID_DIR


def request_path(name: str, pid_dir: Path | None = None) -> Path:
    return _dir(pid_dir) / f"{name}.stop.json"


def result_path(name: str, pid_dir: Path | None = None) -> Path:
    return _dir(pid_dir) / f"{name}.stopped.json"


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    # Written whole and renamed into place, so the other process never reads
    # half a file.
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _read(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def request_stop(name: str, *, flatten: bool, pid_dir: Path | None = None) -> Path:
    path = request_path(name, pid_dir)
    _unlink(result_path(name, pid_dir))  # a leftover outcome must not answer this request
    _write_atomic(path, {"flatten": bool(flatten)})
    return path


def read_stop_request(name: str, pid_dir: Path | None = None) -> dict[str, Any] | None:
    return _read(request_path(name, pid_dir))


def stop_request_pending(name: str, pid_dir: Path | None = None) -> bool:
    return request_path(name, pid_dir).exists()


def clear_stop_request(name: str, pid_dir: Path | None = None) -> None:
    _unlink(request_path(name, pid_dir))


def write_stop_result(name: str, result: dict[str, Any], pid_dir: Path | None = None) -> None:
    _write_atomic(result_path(name, pid_dir), result)


def pop_stop_result(name: str, pid_dir: Path | None = None) -> dict[str, Any] | None:
    path = result_path(name, pid_dir)
    result = _read(path)
    if result is not None:
        _unlink(path)
    return result
