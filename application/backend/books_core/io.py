"""Small filesystem helpers for durable artifact writes."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any


def _fsync_dir(path: Path) -> None:
    """Best-effort directory fsync so renames survive process crashes."""
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes via temp file + fsync + atomic rename."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    finally:
        if tmp.exists():
            tmp.unlink()


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(path: Path, data: Any, *, indent: int = 2) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=indent)
    atomic_write_text(path, text, encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))
