"""Deterministic source-page geometry used to keep HTML faithful to the PDF.

The profile is intentionally conservative: it describes the source page and
does not attempt to "fix" it.  Renderers and overflow repair code can use it
to decide whether spacing may be reduced or whether the page must be split.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import fitz


def _rect(values: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(v) for v in values)
    except (TypeError, ValueError):
        return None
    return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None


def _density(free_ratio: float) -> str:
    if free_ratio >= 0.14:
        return "roomy"
    if free_ratio >= 0.06:
        return "balanced"
    if free_ratio >= 0:
        return "tight"
    return "overfull-source"


def build_source_profile(source_pdf: Path, diagnosis: Path | None = None) -> dict[str, Any]:
    """Build a stable geometry profile from one-page source PDF."""
    with fitz.open(source_pdf) as doc:
        page = doc[0]
        page_rect = page.rect
        blocks = page.get_text("blocks")
        text_rects = [fitz.Rect(b[:4]) for b in blocks if len(b) >= 5 and str(b[4]).strip()]
        images = [fitz.Rect(i["bbox"]) for i in page.get_image_info()]

    content_rects = text_rects + images
    content = None
    if content_rects:
        content = fitz.Rect(
            min(r.x0 for r in content_rects),
            min(r.y0 for r in content_rects),
            max(r.x1 for r in content_rects),
            max(r.y1 for r in content_rects),
        )
    content_height = content.height if content else 0.0
    free_ratio = (page_rect.height - content_height) / page_rect.height if page_rect.height else 0.0

    profile: dict[str, Any] = {
        "schema_version": "1.0",
        "source_pdf": str(source_pdf),
        "page_size_pt": [round(page_rect.width, 2), round(page_rect.height, 2)],
        "content_bounds_pt": [round(v, 2) for v in content] if content else None,
        "text_block_count": len(text_rects),
        "image_count": len(images),
        "content_height_pt": round(content_height, 2),
        "free_space_ratio": round(free_ratio, 4),
        "density": _density(free_ratio),
        "fit_policy": {
            "min_body_font_pt": 10.5 if free_ratio >= 0.06 else 11.0,
            "allow_global_scale": free_ratio >= 0.14,
            "allow_split": free_ratio < 0.06,
        },
    }
    if diagnosis and diagnosis.is_file():
        try:
            profile["visual_diagnosis"] = json.loads(diagnosis.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            profile["visual_diagnosis"] = None
    return profile


def load_source_profile(html_path: Path, page_num: int) -> dict[str, Any] | None:
    """Find a stored profile next to the page or in its work directory."""
    candidates = [
        html_path.parent / f"page_{page_num:04d}.source-profile.json",
        html_path.parent.parent / "work" / f"page_{page_num:04d}" / "source-profile.json",
    ]
    for path in candidates:
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
    return None
