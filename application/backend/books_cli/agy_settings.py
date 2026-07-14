"""AGY authentication and quota helpers used by the Studio settings screen."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def credential_paths(home: Path | None = None) -> list[Path]:
    """Return files that actually carry AGY OAuth credentials.

    ``jetski_state.pbtxt`` is deliberately excluded: it stores CLI state, not
    the OAuth session, and deleting it makes logout unnecessarily destructive.
    """
    root = (home or Path.home()).expanduser()
    return [
        root / ".gemini/antigravity-cli/antigravity-oauth-token",
        root / ".gemini/credentials.json",
    ]


def credentials_present(home: Path | None = None) -> bool:
    return any(path.is_file() and path.stat().st_size > 0 for path in credential_paths(home))


def remove_credentials(home: Path | None = None) -> list[Path]:
    removed: list[Path] = []
    for path in credential_paths(home):
        if path.exists():
            path.unlink()
            removed.append(path)
    return removed


def strip_terminal_output(output: str) -> str:
    return ANSI_ESCAPE.sub("", output).replace("\r", "")


def parse_quota_output(output: str) -> dict[str, Any]:
    """Parse one interactive ``/quota`` snapshot and its auth state."""
    text = strip_terminal_output(output)
    lowered = text.lower()
    quota: dict[str, Any] = {"account": "", "groups": []}

    acc_match = re.search(r"Account:\s*([^\n]+)", text, flags=re.IGNORECASE)
    if acc_match:
        quota["account"] = acc_match.group(1).strip()

    lines = text.split("\n")
    current_group: dict[str, Any] | None = None
    current_limit: dict[str, Any] | None = None
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if (
            re.fullmatch(r"[A-Z0-9][A-Z0-9\s&]+", stripped or "")
            and index + 1 < len(lines)
            and "Models within this group:" in lines[index + 1]
        ):
            if current_group:
                if current_limit:
                    current_group["limits"].append(current_limit)
                    current_limit = None
                quota["groups"].append(current_group)
            current_group = {
                "name": stripped,
                "models": lines[index + 1].split("Models within this group:", 1)[1].strip(),
                "limits": [],
            }
            index += 2
            continue

        if current_group and re.fullmatch(r"[A-Za-z\s]+Limit", stripped or ""):
            if current_limit:
                current_group["limits"].append(current_limit)
            percent = 0.0
            info = ""
            if index + 1 < len(lines):
                match = re.search(r"([0-9]+(?:\.[0-9]+)?)%", lines[index + 1])
                if match:
                    percent = float(match.group(1))
            if index + 2 < len(lines):
                info = lines[index + 2].strip()
            current_limit = {
                "name": stripped,
                "percent": percent,
                "info": info,
            }
            index += 3
            continue
        index += 1

    if current_group:
        if current_limit:
            current_group["limits"].append(current_limit)
        quota["groups"].append(current_group)

    if "currently not signed in" in lowered or "select login method" in lowered:
        state = "disconnected"
        message = "AGY CLI is not signed in."
    elif "eligibility check failed" in lowered:
        state = "needs_verification"
        message = "Google account verification is required before AGY can run pipeline commands."
    elif quota["account"] and quota["groups"]:
        state = "connected"
        message = "AGY CLI is authenticated and ready."
    elif quota["account"]:
        state = "error"
        message = "AGY account was detected, but quota data could not be read."
    else:
        state = "error"
        message = "Could not determine AGY authentication state from the CLI output."

    return {
        "state": state,
        "message": message,
        "quota": quota,
        "raw_has_quota": bool(quota["groups"]),
    }
