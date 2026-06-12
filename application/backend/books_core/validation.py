"""HTML and process status validation."""

from __future__ import annotations

from typing import Any


class ArtifactValidationError(ValueError):
    """Raised when a pipeline artifact is structurally invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ArtifactValidationError(message)


def validate_process_status(data: dict[str, Any], *, page: int | None = None) -> None:
    _require(isinstance(data, dict), "process.status must be a JSON object")
    if page is not None:
        _require(int(data.get("page", page)) == page, "process.status page mismatch")
    _require(
        data.get("state") in {"idle", "queued", "running", "done", "failed", "cancelled"},
        "invalid process state",
    )
    _require(bool(data.get("step")), "process.status missing step")


def validate_draft_html(text: str) -> None:
    _require("<main" in text and "book-page" in text, "HTML missing A4 book-page shell")
    _require("<article" in text, "HTML missing semantic article")
    _require("pdf-render" not in text, "HTML includes forbidden pdf-render marker")
