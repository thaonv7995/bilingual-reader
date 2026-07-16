"""AGY authentication and quota helpers used by the Studio settings screen."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from html import unescape
from pathlib import Path
from typing import Any


ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
OSC_ESCAPE = re.compile(r"\x1b\][^\x07]*(?:\x07|\x1b\\)")
OSC_LINK = re.compile(r"\x1b\]8;[^;]*;(https?://[^\x07\x1b]+)(?:\x07|\x1b\\)")
HTTP_URL = re.compile(r"https?://[^\s\x00-\x1f\x7f<>\"']+")
AGY_KEYCHAIN_SERVICE = "gemini"
AGY_KEYCHAIN_ACCOUNT = "antigravity"


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


def keychain_credential_present() -> bool:
    """Check AGY's current macOS Keychain entry without reading its secret."""
    if sys.platform != "darwin" or not shutil.which("security"):
        return False
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                AGY_KEYCHAIN_ACCOUNT,
                "-s",
                AGY_KEYCHAIN_SERVICE,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def credentials_present(home: Path | None = None) -> bool:
    file_credentials = any(
        path.is_file() and path.stat().st_size > 0 for path in credential_paths(home)
    )
    # Passing an explicit home is primarily used for isolated operations/tests;
    # never mix the real user's Keychain into that result.
    return file_credentials or (home is None and keychain_credential_present())


def remove_credentials(home: Path | None = None) -> list[Path]:
    removed: list[Path] = []
    for path in credential_paths(home):
        if path.exists():
            path.unlink()
            removed.append(path)
    if home is None and sys.platform == "darwin" and shutil.which("security"):
        try:
            subprocess.run(
                [
                    "security",
                    "delete-generic-password",
                    "-a",
                    AGY_KEYCHAIN_ACCOUNT,
                    "-s",
                    AGY_KEYCHAIN_SERVICE,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    return removed


def strip_terminal_output(output: str) -> str:
    return ANSI_ESCAPE.sub("", OSC_ESCAPE.sub("", output)).replace("\r", "")


def extract_oauth_url(output: str) -> str | None:
    """Extract an OAuth URL from plain text or an OSC-8 terminal hyperlink."""
    candidates = OSC_LINK.findall(output)
    candidates.extend(HTTP_URL.findall(strip_terminal_output(output)))
    if not candidates:
        # Some terminal renderers leave the OSC payload behind after stripping
        # only the ESC byte. Searching the raw stream is a useful final fallback.
        candidates.extend(HTTP_URL.findall(output))

    cleaned: list[str] = []
    for candidate in candidates:
        url = unescape(candidate).rstrip(".,;:!?)]}\x07")
        if url not in cleaned:
            cleaned.append(url)
    if not cleaned:
        return None

    preferred_markers = (
        "accounts.google.",
        "oauth",
        "/auth/",
        "gemini-code-assist",
        "antigravity",
    )
    return next(
        (url for url in cleaned if any(marker in url.lower() for marker in preferred_markers)),
        cleaned[0],
    )


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
