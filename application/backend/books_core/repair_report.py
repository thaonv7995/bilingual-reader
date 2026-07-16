"""Persist page-level validation failures for targeted repair runs."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from books_core.io import atomic_write_json


_PAGE_FAILURE = re.compile(
    r"^FAIL\s+(?P<lang>[^/\s]+)/page_(?P<page>\d+)\.html:\s*(?P<message>.+)$"
)
_EXTRACTOR_FAILURE = re.compile(
    r"^FAIL extractor did not create referenced figure:\s*"
    r"page\s+(?P<page>\d+):\s*(?P<message>.+)$",
    re.I,
)


def repair_report_path(book_root: Path) -> Path:
    return Path(book_root) / "work" / "repair-report.json"


def classify_issue(message: str) -> str:
    lowered = message.lower()
    if (
        "overflow" in lowered
        or "clipped text/content" in lowered
        or "rendered page width" in lowered
        or "rendered page height" in lowered
        or "exactly one a4 sheet" in lowered
    ):
        return "layout_overflow"
    if "missing image:" in lowered or "empty image" in lowered:
        return "missing_asset"
    if "no meaningful visible content" in lowered or "blank page shell" in lowered:
        return "blank_content"
    if "missing css:" in lowered or "missing js:" in lowered:
        return "missing_asset"
    return "html_validation"


def parse_validation_failures(output: str) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    page_categories: dict[int, set[str]] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        match = _PAGE_FAILURE.match(line)
        extractor_match = _EXTRACTOR_FAILURE.match(line)
        if match:
            page = int(match.group("page"))
            lang = match.group("lang")
            message = match.group("message").strip()
            category = classify_issue(message)
        elif extractor_match:
            page = int(extractor_match.group("page"))
            lang = "all"
            message = (
                "Extractor did not create referenced figure: "
                + extractor_match.group("message").strip()
            )
            category = "missing_asset"
        else:
            continue
        issues.append(
            {
                "page": page,
                "lang": lang,
                "category": category,
                "message": message,
            }
        )
        page_categories.setdefault(page, set()).add(category)

    pages = [
        {"page": page, "categories": sorted(categories)}
        for page, categories in sorted(page_categories.items())
    ]
    return {"pages": pages, "issues": issues}


def write_repair_report(book_root: Path, output: str, *, stage: str) -> dict[str, Any] | None:
    parsed = parse_validation_failures(output)
    if not parsed["pages"]:
        return None
    report = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        **parsed,
    }
    path = repair_report_path(book_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, report)
    return report


def read_repair_report(book_root: Path) -> dict[str, Any] | None:
    path = repair_report_path(book_root)
    if not path.is_file():
        return None
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("pages"), list):
            return None
        return data
    except (OSError, ValueError):
        return None


def clear_repair_report(book_root: Path) -> None:
    repair_report_path(book_root).unlink(missing_ok=True)
