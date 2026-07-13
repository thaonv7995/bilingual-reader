"""Diagnose whether PDF figures should be reconstructed or raster-cropped."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from books_core.io import atomic_write_json


FIGURE_RE = re.compile(
    r"^(?:Figure|Fig\.|Hình)\s+([A-Za-z\d]+(?:[-.]\d+)?)(?:\s|[:.]|$)",
    re.IGNORECASE,
)


def _rect_list(rect: fitz.Rect) -> list[float]:
    return [round(float(value), 3) for value in (rect.x0, rect.y0, rect.x1, rect.y1)]


def _expanded(rect: fitz.Rect, amount: float, page_rect: fitz.Rect) -> fitz.Rect:
    result = fitz.Rect(
        rect.x0 - amount,
        rect.y0 - amount,
        rect.x1 + amount,
        rect.y1 + amount,
    )
    result &= page_rect
    return result


def _rect_distance(left: fitz.Rect, right: fitz.Rect) -> float:
    dx = max(left.x0 - right.x1, right.x0 - left.x1, 0.0)
    dy = max(left.y0 - right.y1, right.y0 - left.y1, 0.0)
    return math.hypot(dx, dy)


def _touches(left: fitz.Rect, right: fitz.Rect, gap: float = 12.0) -> bool:
    return _rect_distance(left, right) <= gap


def _text_lines(page: fitz.Page) -> list[tuple[str, fitz.Rect]]:
    lines: list[tuple[str, fitz.Rect]] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if text:
                lines.append((text, fitz.Rect(line["bbox"])))
    return lines


def _figure_labels(page: fitz.Page) -> list[tuple[str, str, fitz.Rect]]:
    labels: list[tuple[str, str, fitz.Rect]] = []
    for text, rect in _text_lines(page):
        match = FIGURE_RE.match(text)
        if match:
            labels.append((match.group(1), text, rect))
    return sorted(labels, key=lambda item: (item[2].y0, item[2].x0))


def _visual_clusters(page: fitz.Page) -> list[dict[str, Any]]:
    page_rect = page.rect
    items: list[dict[str, Any]] = []
    for drawing in page.get_drawings():
        rect = fitz.Rect(drawing["rect"])
        if rect.width < 3 and rect.height < 3:
            continue
        if rect.width > page_rect.width * 0.95 and rect.height > page_rect.height * 0.95:
            continue
        items.append(
            {
                "rect": rect,
                "drawing_count": 1,
                "drawing_items": len(drawing.get("items", [])),
                "image_count": 0,
            }
        )
    for image in page.get_image_info():
        rect = fitz.Rect(image["bbox"])
        if rect.width < 3 or rect.height < 3:
            continue
        items.append(
            {
                "rect": rect,
                "drawing_count": 0,
                "drawing_items": 0,
                "image_count": 1,
            }
        )

    clusters: list[dict[str, Any]] = []
    for item in items:
        touching = [cluster for cluster in clusters if _touches(cluster["rect"], item["rect"])]
        if not touching:
            clusters.append(dict(item))
            continue
        target = touching[0]
        target["rect"] |= item["rect"]
        target["drawing_count"] += item["drawing_count"]
        target["drawing_items"] += item["drawing_items"]
        target["image_count"] += item["image_count"]
        for extra in touching[1:]:
            target["rect"] |= extra["rect"]
            target["drawing_count"] += extra["drawing_count"]
            target["drawing_items"] += extra["drawing_items"]
            target["image_count"] += extra["image_count"]
            clusters.remove(extra)
    return clusters


def _caption_position(art: fitz.Rect, caption: fitz.Rect) -> str:
    vertical_overlap = min(art.y1, caption.y1) - max(art.y0, caption.y0)
    horizontal_overlap = min(art.x1, caption.x1) - max(art.x0, caption.x0)
    if vertical_overlap > 0 and caption.x0 >= art.x1 - 3:
        return "right"
    if vertical_overlap > 0 and caption.x1 <= art.x0 + 3:
        return "left"
    if horizontal_overlap > 0 and caption.y0 >= art.y1 - 3:
        return "below"
    if horizontal_overlap > 0 and caption.y1 <= art.y0 + 3:
        return "above"
    return "overlapping"


def diagnose_pdf_page(pdf_path: Path, *, page_num: int) -> dict[str, Any]:
    """Return deterministic figure strategies and crop bounds for one page PDF."""
    with fitz.open(pdf_path) as document:
        page = document[0]
        page_rect = page.rect
        labels = _figure_labels(page)
        clusters = _visual_clusters(page)
        lines = _text_lines(page)
        figures: list[dict[str, Any]] = []

        for figure_id, label, caption_rect in labels:
            candidates = [
                cluster
                for cluster in clusters
                if _rect_distance(cluster["rect"], caption_rect)
                <= max(page_rect.width * 0.35, 80.0)
            ]
            if not candidates:
                figures.append(
                    {
                        "id": figure_id,
                        "label": label,
                        "strategy": "extract-raster",
                        "reason": "No reliable vector or embedded-image region was detected near the caption.",
                        "caption_bbox": _rect_list(caption_rect),
                        "art_bbox": None,
                        "crop_bbox": None,
                    }
                )
                continue

            cluster = min(candidates, key=lambda item: _rect_distance(item["rect"], caption_rect))
            art_rect = cluster["rect"]
            diagram_lines = [
                text
                for text, line_rect in lines
                if line_rect.intersects(_expanded(art_rect, 4.0, page_rect))
                and not FIGURE_RE.match(text)
            ]
            simple_vector = (
                cluster["image_count"] == 0
                and 0 < cluster["drawing_count"] <= 80
                and cluster["drawing_items"] <= 500
                and len(diagram_lines) <= 40
            )
            strategy = "reconstruct-html-svg" if simple_vector else "extract-raster"
            if simple_vector:
                reason = (
                    f"Simple vector diagram: {cluster['drawing_count']} drawing objects, "
                    f"{len(diagram_lines)} text lines, no embedded raster image."
                )
            elif cluster["image_count"]:
                reason = "Embedded raster image detected; preserve it with a PDF crop."
            else:
                reason = "Vector content is too complex for reliable semantic reconstruction."

            figures.append(
                {
                    "id": figure_id,
                    "label": label,
                    "strategy": strategy,
                    "reason": reason,
                    "caption_position": _caption_position(art_rect, caption_rect),
                    "caption_bbox": _rect_list(caption_rect),
                    "art_bbox": _rect_list(art_rect),
                    "crop_bbox": _rect_list(_expanded(art_rect, 7.0, page_rect)),
                    "drawing_count": cluster["drawing_count"],
                    "drawing_items": cluster["drawing_items"],
                    "image_count": cluster["image_count"],
                    "text_line_count": len(diagram_lines),
                }
            )

        return {
            "schema_version": "1.0",
            "page": page_num,
            "source_pdf": str(pdf_path),
            "page_bbox": _rect_list(page_rect),
            "figures": figures,
        }


def diagnosis_path(book_root: Path, page_num: int) -> Path:
    return book_root / "work" / f"page_{page_num:04d}" / "visual-diagnosis.json"


def ensure_visual_diagnosis(
    book_root: Path,
    page_num: int,
    *,
    force: bool = False,
) -> dict[str, Any]:
    pdf_path = book_root / "work" / f"page_{page_num:04d}" / "source.pdf"
    if not pdf_path.is_file():
        return {
            "schema_version": "1.0",
            "page": page_num,
            "source_pdf": str(pdf_path),
            "figures": [],
            "warning": "source.pdf is missing",
        }
    output_path = diagnosis_path(book_root, page_num)
    if not force and output_path.is_file() and output_path.stat().st_mtime >= pdf_path.stat().st_mtime:
        return json.loads(output_path.read_text(encoding="utf-8"))
    diagnosis = diagnose_pdf_page(pdf_path, page_num=page_num)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_path, diagnosis)
    return diagnosis
