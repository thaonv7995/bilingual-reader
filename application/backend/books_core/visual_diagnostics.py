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
    r"^(?:(?:Figure|Fig\.|Hình)\s+([A-Za-z\d]+(?:[-.]\d+)?)|"
    r"(\d{1,3})[.)])(?:\s|[:.]|$)",
    re.IGNORECASE,
)

VISUAL_STRATEGIES = {"reconstruct-html-svg", "extract-raster"}
HTML_PAGE_FIGURE_RE = re.compile(r"page_(\d{4})_fig_([A-Za-z0-9_.-]+)\.png", re.I)
HTML_VISUAL_ID_RE = re.compile(r"data-visual-id=[\"']([^\"']+)[\"']", re.I)


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
    image_rects = [fitz.Rect(image["bbox"]) for image in page.get_image_info()]
    for text, rect in _text_lines(page):
        match = FIGURE_RE.match(text)
        if not match:
            continue
        # A bare "1. ..." is only a figure caption when it is adjacent to an
        # embedded image. This avoids treating ordinary numbered prose as art.
        if match.group(2) and not any(
            _rect_distance(rect, image_rect) <= 48.0 for image_rect in image_rects
        ):
            continue
        labels.append((match.group(1) or match.group(2), text, rect))
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
            "producer": "deterministic-fallback",
            "page": page_num,
            "source_pdf": str(pdf_path),
            "page_bbox": _rect_list(page_rect),
            "figures": figures,
        }


def diagnosis_path(book_root: Path, page_num: int) -> Path:
    return book_root / "work" / f"page_{page_num:04d}" / "visual-diagnosis.json"


def visual_reference_path(book_root: Path, page_num: int) -> Path:
    return book_root / "work" / f"page_{page_num:04d}" / "source.png"


def ensure_visual_reference(
    book_root: Path,
    page_num: int,
    *,
    force: bool = False,
    dpi: int = 144,
) -> dict[str, Any]:
    """Render the complete PDF page that the vision agent must inspect."""
    pdf_path = book_root / "work" / f"page_{page_num:04d}" / "source.pdf"
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)
    output_path = visual_reference_path(book_root, page_num)
    if force or not output_path.is_file() or output_path.stat().st_mtime < pdf_path.stat().st_mtime:
        with fitz.open(pdf_path) as document:
            page = document[0]
            pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            pixmap.save(str(output_path))
    with fitz.open(pdf_path) as document:
        page_rect = document[0].rect
    with output_path.open("rb") as image_file:
        header = image_file.read(24)
    if len(header) < 24 or header[12:16] != b"IHDR":
        raise ValueError(f"Invalid visual reference PNG: {output_path}")
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    return {
        "path": str(output_path),
        "width": width,
        "height": height,
        "page_bbox": _rect_list(page_rect),
        "dpi": dpi,
    }


def _valid_bbox(values: Any, *, normalized: bool) -> bool:
    if not isinstance(values, list) or len(values) != 4:
        return False
    try:
        x0, y0, x1, y1 = (float(value) for value in values)
    except (TypeError, ValueError):
        return False
    if normalized and not all(0.0 <= value <= 1.0 for value in (x0, y0, x1, y1)):
        return False
    return x1 > x0 and y1 > y0


def validate_agent_visual_plan(data: Any, *, page_num: int) -> None:
    """Validate the raw JSON contract written by the vision agent."""
    if not isinstance(data, dict):
        raise ValueError("visual plan must be a JSON object")
    if int(data.get("page", -1)) != page_num:
        raise ValueError(f"visual plan page must be {page_num}")
    figures = data.get("figures")
    if not isinstance(figures, list):
        raise ValueError("visual plan figures must be an array")
    seen: set[str] = set()
    for index, figure in enumerate(figures, start=1):
        if not isinstance(figure, dict):
            raise ValueError(f"visual plan figure {index} must be an object")
        figure_id = str(figure.get("id") or "").strip()
        if not figure_id or figure_id in seen:
            raise ValueError(f"visual plan figure {index} has a missing or duplicate id")
        seen.add(figure_id)
        if figure.get("strategy") not in VISUAL_STRATEGIES:
            raise ValueError(f"visual plan figure {figure_id} has an invalid strategy")
        if not (
            _valid_bbox(figure.get("bbox_normalized"), normalized=True)
            or _valid_bbox(figure.get("art_bbox"), normalized=False)
        ):
            raise ValueError(f"visual plan figure {figure_id} has no valid bbox_normalized")
        caption_bbox = figure.get("caption_bbox_normalized")
        if caption_bbox is not None and not _valid_bbox(caption_bbox, normalized=True):
            raise ValueError(f"visual plan figure {figure_id} has an invalid caption bbox")


def _normalized_to_page(values: list[float], page_rect: fitz.Rect) -> fitz.Rect:
    return fitz.Rect(
        page_rect.x0 + float(values[0]) * page_rect.width,
        page_rect.y0 + float(values[1]) * page_rect.height,
        page_rect.x0 + float(values[2]) * page_rect.width,
        page_rect.y0 + float(values[3]) * page_rect.height,
    )


def _overlap_score(left: fitz.Rect, right: fitz.Rect) -> float:
    intersection = left & right
    if intersection.is_empty:
        return 0.0
    denominator = min(left.get_area(), right.get_area())
    return intersection.get_area() / denominator if denominator > 0 else 0.0


def _snap_agent_bbox(
    candidate: fitz.Rect,
    *,
    strategy: str,
    image_rects: list[fitz.Rect],
    vector_clusters: list[dict[str, Any]],
) -> tuple[fitz.Rect, str]:
    if strategy == "extract-raster" and image_rects:
        matches = [rect for rect in image_rects if _overlap_score(candidate, rect) >= 0.2]
        if matches:
            snapped = fitz.Rect(matches[0])
            for rect in matches[1:]:
                snapped |= rect
            return snapped, "embedded-image"
        nearest = min(image_rects, key=lambda rect: _rect_distance(candidate, rect))
        if _rect_distance(candidate, nearest) <= 24.0:
            return fitz.Rect(nearest), "embedded-image"
    if strategy == "reconstruct-html-svg" and vector_clusters:
        candidates = [cluster["rect"] for cluster in vector_clusters]
        matches = [rect for rect in candidates if _overlap_score(candidate, rect) >= 0.2]
        if matches:
            return fitz.Rect(max(matches, key=lambda rect: _overlap_score(candidate, rect))), "pdf-vector"
    return candidate, "agent-region"


def finalize_agent_visual_plan(book_root: Path, page_num: int) -> dict[str, Any]:
    """Validate agent vision output and snap approximate regions to PDF objects."""
    plan_path = diagnosis_path(book_root, page_num)
    pdf_path = book_root / "work" / f"page_{page_num:04d}" / "source.pdf"
    data = json.loads(plan_path.read_text(encoding="utf-8"))
    validate_agent_visual_plan(data, page_num=page_num)
    reference = ensure_visual_reference(book_root, page_num)
    with fitz.open(pdf_path) as document:
        page = document[0]
        page_rect = page.rect
        image_rects = [fitz.Rect(info["bbox"]) for info in page.get_image_info()]
        vector_clusters = _visual_clusters(page)
        figures: list[dict[str, Any]] = []
        for figure in data["figures"]:
            if _valid_bbox(figure.get("bbox_normalized"), normalized=True):
                candidate = _normalized_to_page(figure["bbox_normalized"], page_rect)
            else:
                candidate = fitz.Rect(figure["art_bbox"])
            candidate &= page_rect
            art_rect, snapped_to = _snap_agent_bbox(
                candidate,
                strategy=str(figure["strategy"]),
                image_rects=image_rects,
                vector_clusters=vector_clusters,
            )
            caption_bbox = figure.get("caption_bbox_normalized")
            caption_rect = (
                _normalized_to_page(caption_bbox, page_rect) & page_rect
                if caption_bbox is not None
                else None
            )
            normalized_figure = dict(figure)
            normalized_figure.update(
                {
                    "id": str(figure["id"]),
                    "art_bbox": _rect_list(art_rect),
                    "crop_bbox": _rect_list(_expanded(art_rect, 7.0, page_rect)),
                    "caption_bbox": _rect_list(caption_rect) if caption_rect else None,
                    "snapped_to": snapped_to,
                }
            )
            figures.append(normalized_figure)
    finalized = {
        "schema_version": "2.0",
        "producer": "agent-vision",
        "status": "finalized",
        "page": page_num,
        "source_pdf": str(pdf_path),
        "source_image": reference,
        "page_bbox": reference["page_bbox"],
        "figures": figures,
    }
    atomic_write_json(plan_path, finalized)
    return finalized


def agent_visual_plan_ready(book_root: Path, page_num: int) -> bool:
    path = diagnosis_path(book_root, page_num)
    if not path.is_file():
        return False
    pdf_path = book_root / "work" / f"page_{page_num:04d}" / "source.pdf"
    if pdf_path.is_file() and path.stat().st_mtime < pdf_path.stat().st_mtime:
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ready = (
            data.get("producer") == "agent-vision"
            and data.get("status") == "finalized"
            and int(data.get("page", -1)) == page_num
            and isinstance(data.get("figures"), list)
        )
        if ready:
            validate_agent_visual_plan(data, page_num=page_num)
        return ready
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def validate_html_against_visual_plan(
    html: str,
    plan: dict[str, Any],
    *,
    page_num: int,
) -> list[str]:
    """Ensure raster placeholders are derived from, and covered by, the plan."""
    canonical = lambda value: re.sub(r"[^a-z0-9]", "", str(value).lower())
    plan_figures = {
        canonical(figure.get("id")): figure
        for figure in plan.get("figures", [])
        if isinstance(figure, dict) and figure.get("id") is not None
    }
    html_ids = {
        canonical(match.group(2))
        for match in HTML_PAGE_FIGURE_RE.finditer(html)
        if int(match.group(1)) == page_num
    }
    tagged_ids = {
        canonical(match.group(1)) for match in HTML_VISUAL_ID_RE.finditer(html)
    }
    issues: list[str] = []
    for figure_id in sorted((html_ids | tagged_ids) - set(plan_figures)):
        issues.append(f"HTML references unplanned figure id {figure_id}")
    required_raster = {
        figure_id
        for figure_id, figure in plan_figures.items()
        if figure.get("strategy") == "extract-raster"
    }
    for figure_id in sorted(required_raster - html_ids):
        issues.append(f"visual plan raster figure {figure_id} has no HTML image placeholder")
    required_vector = {
        figure_id
        for figure_id, figure in plan_figures.items()
        if figure.get("strategy") == "reconstruct-html-svg"
    }
    for figure_id in sorted(required_vector - tagged_ids):
        issues.append(f"visual plan vector figure {figure_id} has no data-visual-id HTML figure")
    return issues


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
