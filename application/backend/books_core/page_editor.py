"""Safe read, validation, backup, and save operations for Studio page editing."""

from __future__ import annotations

import hashlib
import json
import re
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
MAX_BACKUPS_PER_STYLESHEET = 20
STYLESHEET_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.css$", re.IGNORECASE)


def _language(lang: str) -> str:
    normalized = str(lang or "").strip().lower()
    if normalized not in EDITOR_LANGUAGES:
        raise ValueError("Editor language must be 'en' or 'vi'")
    return normalized


def page_source_path(book_root: Path, page: int, lang: str) -> Path:
    if int(page) < 1:
        raise ValueError("Page number must be positive")
    return Path(book_root) / "output" / _language(lang) / f"page_{int(page):04d}.html"


def _stylesheet_name(filename: str) -> str:
    normalized = str(filename or "").strip()
    if not STYLESHEET_NAME_PATTERN.fullmatch(normalized) or Path(normalized).name != normalized:
        raise ValueError("Stylesheet must be a direct .css file in output/assets")
    return normalized


def stylesheet_source_path(book_root: Path, filename: str) -> Path:
    return Path(book_root) / "output" / "assets" / _stylesheet_name(filename)


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


def list_stylesheet_sources(book_root: Path) -> list[dict[str, Any]]:
    assets = Path(book_root) / "output" / "assets"
    if not assets.is_dir():
        return []
    stylesheets: list[dict[str, Any]] = []
    for path in sorted(assets.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or not STYLESHEET_NAME_PATTERN.fullmatch(path.name):
            continue
        stylesheets.append(
            {
                "filename": path.name,
                "path": f"output/assets/{path.name}",
                "bytes": path.stat().st_size,
                "updated_at": datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        )
    return stylesheets


def read_stylesheet_source(book_root: Path, filename: str) -> dict[str, Any]:
    path = stylesheet_source_path(book_root, filename)
    if not path.is_file():
        raise FileNotFoundError(path)
    css = path.read_text(encoding="utf-8")
    return {
        "filename": path.name,
        "path": f"output/assets/{path.name}",
        "css": css,
        "revision": source_revision(css),
        "bytes": len(css.encode("utf-8")),
        "updated_at": datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).isoformat(),
    }


def _css_structure_issues(css: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    stack: list[tuple[str, int]] = []
    matching = {"}": "{", "]": "[", ")": "("}
    quote: str | None = None
    quote_line = 1
    in_comment = False
    comment_line = 1
    escaped = False
    line = 1
    index = 0
    while index < len(css):
        char = css[index]
        next_char = css[index + 1] if index + 1 < len(css) else ""
        if char == "\n":
            line += 1
        if in_comment:
            if char == "*" and next_char == "/":
                in_comment = False
                index += 2
                continue
            index += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char == "/" and next_char == "*":
            in_comment = True
            comment_line = line
            index += 2
            continue
        if char in {'"', "'"}:
            quote = char
            quote_line = line
        elif char in "{[(":
            stack.append((char, line))
        elif char in "}])":
            expected = matching[char]
            if not stack or stack[-1][0] != expected:
                issues.append(
                    {"type": "structure", "message": f"Unexpected '{char}' on line {line}"}
                )
            else:
                stack.pop()
        index += 1

    if in_comment:
        issues.append(
            {"type": "structure", "message": f"Unterminated comment opened on line {comment_line}"}
        )
    if quote:
        issues.append(
            {"type": "structure", "message": f"Unterminated string opened on line {quote_line}"}
        )
    for opener, opener_line in reversed(stack):
        issues.append(
            {"type": "structure", "message": f"Unclosed '{opener}' opened on line {opener_line}"}
        )
    return issues


def validate_stylesheet_source(css: str) -> dict[str, Any]:
    encoded_size = len(css.encode("utf-8"))
    issues: list[dict[str, str]] = []
    if encoded_size > MAX_EDITOR_BYTES:
        issues.append(
            {
                "type": "size",
                "message": f"CSS exceeds the {MAX_EDITOR_BYTES // (1024 * 1024)} MB editor limit",
            }
        )
    if "\x00" in css:
        issues.append({"type": "structure", "message": "CSS contains a null byte"})
    issues.extend(_css_structure_issues(css))
    return {
        "valid": not issues,
        "issues": issues,
        "bytes": encoded_size,
        "lines": css.count("\n") + 1,
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


def _backup_stylesheet(path: Path, book_root: Path) -> Path:
    backup_dir = Path(book_root) / "work" / "editor-backups" / "assets" / path.name
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup = backup_dir / f"{stamp}.css"
    shutil.copy2(path, backup)
    backups = sorted(backup_dir.glob("*.css"), reverse=True)
    for stale in backups[MAX_BACKUPS_PER_STYLESHEET:]:
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


def save_stylesheet_source(
    book_root: Path,
    filename: str,
    css: str,
    *,
    expected_revision: str,
) -> dict[str, Any]:
    path = stylesheet_source_path(book_root, filename)
    if not path.is_file():
        raise FileNotFoundError(path)
    current = path.read_text(encoding="utf-8")
    current_revision = source_revision(current)
    if expected_revision != current_revision:
        raise RuntimeError("Stylesheet changed after the editor loaded it; reload before saving")

    validation = validate_stylesheet_source(css)
    if not validation["valid"]:
        messages = "; ".join(issue["message"] for issue in validation["issues"][:5])
        raise ValueError(f"Cannot save invalid CSS: {messages}")

    if css == current:
        return {
            "saved": False,
            "revision": current_revision,
            "backup": None,
            "invalidated": [],
            "validation": validation,
        }

    backup = _backup_stylesheet(path, Path(book_root))
    atomic_write_text(path, css, encoding="utf-8")
    invalidated = list(
        dict.fromkeys(
            _invalidate_derived_outputs(Path(book_root), "en")
            + _invalidate_derived_outputs(Path(book_root), "vi")
        )
    )
    return {
        "saved": True,
        "revision": source_revision(css),
        "backup": str(backup.relative_to(Path(book_root))),
        "invalidated": invalidated,
        "validation": validation,
    }
