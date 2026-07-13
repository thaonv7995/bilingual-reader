#!/usr/bin/env python3
"""Replace vector-figure image placeholders with clipped inline PDF SVG."""

from __future__ import annotations

import html as html_module
import json
import re
import sys
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from books_core.io import atomic_write_text  # noqa: E402
from books_core.visual_diagnostics import (  # noqa: E402
    diagnosis_path,
    ensure_visual_diagnosis,
)


FIGURE_BLOCK_RE = re.compile(r"<figure\b(?P<attrs>[^>]*)>(?P<body>.*?)</figure>", re.I | re.S)
IMG_RE = re.compile(r"<img\b[^>]*>", re.I | re.S)
FIGURE_LABEL_RE = re.compile(
    r"(?:Figure|Fig\.|Hình)\s+([A-Za-z\d]+(?:[-._]\d+)?)",
    re.I,
)


def _canonical_figure_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _prefix_svg_ids(svg: str, prefix: str) -> str:
    ids = re.findall(r'\bid="([^"]+)"', svg)
    for old in sorted(set(ids), key=len, reverse=True):
        new = f"{prefix}{old}"
        svg = re.sub(rf'\bid="{re.escape(old)}"', f'id="{new}"', svg)
        svg = svg.replace(f"url(#{old})", f"url(#{new})")
        svg = svg.replace(f'xlink:href="#{old}"', f'xlink:href="#{new}"')
        svg = svg.replace(f'href="#{old}"', f'href="#{new}"')
    return svg


def _clipped_page_svg(page: fitz.Page, figure: dict, page_num: int) -> str:
    # Prefer the padded crop so strokes touching the art bounds are not clipped.
    bbox = figure.get("crop_bbox") or figure.get("art_bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError(f"Figure {figure.get('id')} has no valid art_bbox")
    x0, y0, x1, y1 = (float(value) for value in bbox)
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"Figure {figure.get('id')} has an empty art_bbox")
    svg = page.get_svg_image(text_as_path=False)
    prefix = f"pdfv-{page_num:04d}-{_canonical_figure_id(str(figure.get('id')))}-"
    svg = _prefix_svg_ids(svg, prefix)
    label = html_module.escape(str(figure.get("label") or f"Figure {figure.get('id')}"), quote=True)
    root = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        'class="pdf-vector-diagram" role="img" '
        f'aria-label="{label}" viewBox="{x0:g} {y0:g} {x1 - x0:g} {y1 - y0:g}" '
        'preserveAspectRatio="xMidYMid meet" '
        'style="display:block;width:100%;height:auto;overflow:hidden">'
    )
    svg = re.sub(r"<svg\b[^>]*>", root, svg, count=1, flags=re.I | re.S)
    return svg


def _block_figure_id(block: str, page_num: int) -> str | None:
    match = FIGURE_LABEL_RE.search(re.sub(r"<[^>]+>", " ", block))
    if match:
        return match.group(1)
    image_match = re.search(
        rf"page_{page_num:04d}_fig_([A-Za-z0-9_.-]+)\.png",
        block,
        re.I,
    )
    return image_match.group(1) if image_match else None


def materialize_page(book_root: Path, page_num: int) -> list[Path]:
    diagnosis_file = diagnosis_path(book_root, page_num)
    diagnosis = (
        json.loads(diagnosis_file.read_text(encoding="utf-8"))
        if diagnosis_file.is_file()
        else ensure_visual_diagnosis(book_root, page_num)
    )
    vector_figures = {
        _canonical_figure_id(str(figure.get("id"))): figure
        for figure in diagnosis.get("figures", [])
        if figure.get("strategy") == "reconstruct-html-svg"
    }
    if not vector_figures:
        return []

    pdf_path = book_root / "work" / f"page_{page_num:04d}" / "source.pdf"
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)
    changed: list[Path] = []
    with fitz.open(pdf_path) as document:
        page = document[0]
        svg_by_id = {
            figure_id: _clipped_page_svg(page, figure, page_num)
            for figure_id, figure in vector_figures.items()
        }
        for html_path in sorted((book_root / "output").glob(f"*/page_{page_num:04d}.html")):
            source = html_path.read_text(encoding="utf-8")

            def replace(match: re.Match[str]) -> str:
                block = match.group(0)
                if "<svg" in block.lower() or not IMG_RE.search(block):
                    return block
                figure_id = _block_figure_id(block, page_num)
                canonical_id = _canonical_figure_id(figure_id or "")
                svg = svg_by_id.get(canonical_id)
                if not svg:
                    return block
                updated = IMG_RE.sub(svg, block, count=1)
                if "data-visual-strategy=" not in updated:
                    updated = updated.replace(
                        "<figure",
                        '<figure data-visual-strategy="reconstruct-html-svg"',
                        1,
                    )
                return updated

            output = FIGURE_BLOCK_RE.sub(replace, source)
            if output != source:
                atomic_write_text(html_path, output)
                changed.append(html_path)
    return changed


def _target_pages(book_root: Path, args: list[str]) -> list[int]:
    if args:
        return sorted({int(value) for value in args})
    return [
        int(path.parent.name.split("_")[1])
        for path in sorted((book_root / "work").glob("page_*/source.pdf"))
    ]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: materialize_vector_figures.py <book-root> [page ...]", file=sys.stderr)
        return 2
    book_root = Path(argv[1]).expanduser().resolve()
    try:
        for page_num in _target_pages(book_root, argv[2:]):
            changed = materialize_page(book_root, page_num)
            if changed:
                print(f"page {page_num:04d}: materialized inline SVG in {len(changed)} language page(s)")
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"FAIL vector materialization: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
