"""Safe read, validation, backup, and save operations for Studio page editing."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from books_core.book_layout import _verify_html_assets
from books_core.io import atomic_write_text
from books_core.validation import ArtifactValidationError, validate_draft_html
from books_core.visual_diagnostics import (
    diagnosis_path,
    validate_agent_visual_plan,
    validate_html_against_visual_plan,
)


EDITOR_LANGUAGES = {"en", "vi"}
MAX_EDITOR_BYTES = 5 * 1024 * 1024
MAX_BACKUPS_PER_LANGUAGE = 20


def _language(lang: str) -> str:
    normalized = str(lang or "").strip().lower()
    if normalized not in EDITOR_LANGUAGES:
        raise ValueError("Editor language must be 'en' or 'vi'")
    return normalized


def page_source_path(book_root: Path, page: int, lang: str) -> Path:
    if int(page) < 1:
        raise ValueError("Page number must be positive")
    return Path(book_root) / "output" / _language(lang) / f"page_{int(page):04d}.html"


def source_revision(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8")).hexdigest()


def read_page_source(book_root: Path, page: int, lang: str) -> dict[str, Any]:
    path = page_source_path(book_root, page, lang)
    if not path.is_file():
        raise FileNotFoundError(path)
    html = path.read_text(encoding="utf-8")
    return {
        "page": int(page),
        "lang": _language(lang),
        "html": html,
        "revision": source_revision(html),
        "bytes": len(html.encode("utf-8")),
        "updated_at": datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).isoformat(),
    }


def validate_page_source(book_root: Path, page: int, lang: str, html: str) -> dict[str, Any]:
    path = page_source_path(book_root, page, lang)
    issues: list[dict[str, str]] = []
    encoded_size = len(html.encode("utf-8"))
    if encoded_size > MAX_EDITOR_BYTES:
        issues.append(
            {
                "type": "size",
                "message": f"HTML exceeds the {MAX_EDITOR_BYTES // (1024 * 1024)} MB editor limit",
            }
        )
    try:
        validate_draft_html(html)
    except (ArtifactValidationError, ValueError) as exc:
        issues.append({"type": "structure", "message": str(exc)})

    for message in _verify_html_assets(path, html, ignore_page_figures=False):
        issues.append({"type": "asset", "message": message})

    plan_path = diagnosis_path(Path(book_root), int(page))
    if plan_path.is_file():
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            validate_agent_visual_plan(plan, page_num=int(page))
            for message in validate_html_against_visual_plan(
                html, plan, page_num=int(page)
            ):
                issues.append({"type": "visual-plan", "message": message})
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            issues.append({"type": "visual-plan", "message": str(exc)})

    return {
        "valid": not issues,
        "issues": issues,
        "bytes": encoded_size,
        "lines": html.count("\n") + 1,
    }


def _backup_page(path: Path, book_root: Path, page: int, lang: str) -> Path:
    backup_dir = Path(book_root) / "work" / f"page_{int(page):04d}" / "editor-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup = backup_dir / f"{stamp}-{_language(lang)}.html"
    shutil.copy2(path, backup)
    backups = sorted(backup_dir.glob(f"*-{_language(lang)}.html"), reverse=True)
    for stale in backups[MAX_BACKUPS_PER_LANGUAGE:]:
        stale.unlink(missing_ok=True)
    return backup


def _invalidate_derived_outputs(book_root: Path, lang: str) -> list[str]:
    book_root = Path(book_root)
    output = book_root / "output"
    language = _language(lang)
    names = ("book.html", "book.pdf") if language == "en" else ("book.vi.html", "book.vi.pdf")
    candidates = [output / name for name in names]
    candidates.extend(
        [
            book_root.parent / f"{book_root.name}.bkb",
            book_root.parent / "bkbs" / f"{book_root.name}.bkb",
        ]
    )
    invalidated: list[str] = []
    for path in candidates:
        if path.is_file():
            path.unlink()
            try:
                invalidated.append(str(path.relative_to(book_root)))
            except ValueError:
                invalidated.append(str(path))
    return invalidated


def save_page_source(
    book_root: Path,
    page: int,
    lang: str,
    html: str,
    *,
    expected_revision: str,
) -> dict[str, Any]:
    path = page_source_path(book_root, page, lang)
    if not path.is_file():
        raise FileNotFoundError(path)
    current = path.read_text(encoding="utf-8")
    current_revision = source_revision(current)
    if expected_revision != current_revision:
        raise RuntimeError("Page changed after the editor loaded it; reload before saving")

    validation = validate_page_source(book_root, page, lang, html)
    if not validation["valid"]:
        messages = "; ".join(issue["message"] for issue in validation["issues"][:5])
        raise ValueError(f"Cannot save invalid page HTML: {messages}")

    if html == current:
        return {
            "saved": False,
            "revision": current_revision,
            "backup": None,
            "invalidated": [],
            "validation": validation,
        }

    backup = _backup_page(path, Path(book_root), page, lang)
    atomic_write_text(path, html, encoding="utf-8")
    invalidated = _invalidate_derived_outputs(Path(book_root), lang)
    return {
        "saved": True,
        "revision": source_revision(html),
        "backup": str(backup.relative_to(Path(book_root))),
        "invalidated": invalidated,
        "validation": validation,
    }
