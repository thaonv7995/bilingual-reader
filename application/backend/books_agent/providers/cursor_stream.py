"""Parse Cursor agent stream-json lines into human-readable live log."""

from __future__ import annotations

import json
from typing import Any, Callable


def _text_from_assistant(ev: dict[str, Any]) -> str:
    msg = ev.get("message") or {}
    parts: list[str] = []
    for block in msg.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and block.get("text"):
            parts.append(str(block["text"]))
    return "".join(parts)


def _tool_call_label(ev: dict[str, Any]) -> str:
    """Cursor stream-json: tool_call.readToolCall / writeToolCall / …"""
    sub = ev.get("subtype") or "?"
    nested = ev.get("tool_call")
    if not isinstance(nested, dict):
        return f"tool ({sub})"

    for key, payload in nested.items():
        if not isinstance(payload, dict):
            continue
        if "ToolCall" not in key and "toolcall" not in key.lower():
            continue
        tool_name = key.replace("ToolCall", "").replace("toolcall", "")
        args = payload.get("args") or {}
        path = (
            args.get("path")
            or args.get("file")
            or args.get("target")
            or args.get("command")
            or ""
        )
        if path:
            from pathlib import Path

            path = str(Path(str(path)).name)
        extra = path or str(args)[:80]
        return f"{tool_name} ({sub}){': ' + extra if extra else ''}"

    return f"tool ({sub})"


def _text_from_tool(ev: dict[str, Any]) -> str:
    return _tool_call_label(ev)


def format_cursor_event(ev: dict[str, Any]) -> str | None:
    """One display line (or chunk) per stream-json event."""
    typ = ev.get("type")
    sub = ev.get("subtype")

    if typ == "system":
        model = ev.get("model")
        if sub == "init":
            return f"[system] session started" + (f" model={model}" if model else "")
        return f"[system] {sub or typ}"

    if typ == "user":
        return None

    if typ == "thinking":
        if sub == "delta" and ev.get("text"):
            return ev["text"]
        if sub == "completed":
            return "\n"
        return None

    if typ == "assistant":
        text = _text_from_assistant(ev)
        return text if text else None

    if typ in ("tool_call", "tool", "tool_use", "tool_result", "tool_output"):
        label = _text_from_tool(ev)
        if sub == "started":
            return f"\n▶ {label}\n"
        if sub == "completed":
            return f"✓ {label}\n"
        return f"\n[tool] {label}\n"

    if typ == "result":
        return f"\n[result] {sub or 'done'}\n"

    if typ == "error":
        err = ev.get("message") or ev.get("error") or ev
        return f"\n[error] {err}\n"

    return None


def handle_cursor_stream_line(
    raw_line: str,
    on_chunk: Callable[[str], None],
    *,
    state: dict[str, Any],
) -> None:
    line = raw_line.strip()
    if not line:
        return
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        on_chunk(line + "\n")
        return

    chunk = format_cursor_event(ev)
    if not chunk:
        return

    if ev.get("type") == "thinking" and ev.get("subtype") == "delta":
        state["think"] = state.get("think", "") + chunk
        on_chunk(chunk)
        return

    if ev.get("type") == "thinking" and ev.get("subtype") == "completed":
        state.pop("think", None)
        on_chunk("\n")
        return

    on_chunk(chunk)
