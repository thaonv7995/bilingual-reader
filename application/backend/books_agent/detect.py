from __future__ import annotations

import shutil
import subprocess
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class DetectResult:
    id: str
    label: str
    installed: bool
    path: str | None
    version: str | None
    runnable: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run(argv: list[str], timeout: int = 12) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=None,
    )


def _version_line(path: str) -> str | None:
    for args in ([path, "--version"], [path, "-v"], [path, "version"]):
        try:
            r = _run(args)
            out = (r.stdout or r.stderr or "").strip().splitlines()
            if out:
                return out[0][:200]
            if r.returncode == 0:
                return "ok"
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            continue
    return None


def _auth_hint_from_output(text: str) -> str | None:
    lower = text.lower()
    for needle in (
        "not logged in",
        "not authenticated",
        "authentication required",
        "please log in",
        "login required",
        "sign in",
        "unauthorized",
    ):
        if needle in lower:
            return "CLI reported not authenticated — log in via terminal, then retry."
    return None


def detect_binary(provider_id: str, label: str, binary_names: list[str]) -> DetectResult:
    for name in binary_names:
        path = shutil.which(name)
        if not path:
            continue
        version = _version_line(path)
        runnable = version is not None
        message = f"Found on PATH: {path}"
        if version:
            message += f" ({version})"
        try:
            r = _run([path, "--help"])
            hint = _auth_hint_from_output((r.stdout or "") + (r.stderr or ""))
            if hint:
                return DetectResult(
                    id=provider_id,
                    label=label,
                    installed=True,
                    path=path,
                    version=version,
                    runnable=False,
                    message=hint,
                )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return DetectResult(
            id=provider_id,
            label=label,
            installed=True,
            path=path,
            version=version,
            runnable=runnable,
            message=message + " — assume authenticated if you use it in terminal.",
        )
    return DetectResult(
        id=provider_id,
        label=label,
        installed=False,
        path=None,
        version=None,
        runnable=False,
        message="Not on PATH. Install the CLI and ensure it is authenticated.",
    )
