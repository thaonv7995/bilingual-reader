#!/usr/bin/env python3
"""Extract figure regions from single-page source PDFs into PNG assets."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import fitz


FIGURE_RE = re.compile(r"^Figure\s+(\d+[-.]\d+)\.", re.I)


def _figure_labels(page: fitz.Page) -> list[tuple[str, str, fitz.Rect]]:
    """Return (fig_id, label_line, bbox) sorted top-to-bottom."""
    found: list[tuple[str, str, fitz.Rect]] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            parts = []
            line_rect: fitz.Rect | None = None
            for span in line.get("spans", []):
                parts.append(span.get("text", ""))
                r = fitz.Rect(span["bbox"])
                line_rect = r if line_rect is None else line_rect | r
            text = "".join(parts).strip()
            m = FIGURE_RE.match(text)
            if m and line_rect is not None:
                found.append((m.group(1), text, line_rect))
    found.sort(key=lambda x: x[2].y0)
    return found


def _footer_top(page: fitz.Page) -> float:
    """Y coordinate above footer/copyright band."""
    rect = page.rect
    for token in ("Copyright", "Robert C. Martin"):
        hits = page.search_for(token)
        if hits:
            return min(h.y0 for h in hits) - 4
    return rect.height - 48


def _drawing_band(page: fitz.Page, y0: float, y1: float) -> fitz.Rect | None:
    """Bounding box of vector drawings between y0 and y1."""
    band: fitz.Rect | None = None
    for path in page.get_drawings():
        r = fitz.Rect(path["rect"])
        if r.y1 < y0 or r.y0 > y1:
            continue
        if r.width < 8 and r.height < 8:
            continue
        band = r if band is None else band | r
    return band


def _image_band(page: fitz.Page, y0: float, y1: float) -> fitz.Rect | None:
    """Bounding box of embedded images between y0 and y1."""
    band: fitz.Rect | None = None
    for info in page.get_image_info():
        r = fitz.Rect(info["bbox"])
        if r.y1 < y0 or r.y0 > y1:
            continue
        band = r if band is None else band | r
    return band


def _diagram_text_band(page: fitz.Page, y0: float, y1: float) -> fitz.Rect | None:
    """BBox of UML / diagram text lines in a vertical band."""
    markers = ("+ ", "- ", "«", "»", "void ", "class ", "struct ", "enum ")
    names = ("Ellipse", "Circle", "User", "Base", "Derived", "Modem", "Subject")
    band: fitz.Rect | None = None
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
            if not text or len(text) > 80:
                continue
            if not (text.startswith(markers) or text in names or " : " in text):
                continue
            rect: fitz.Rect | None = None
            for span in line.get("spans", []):
                r = fitz.Rect(span["bbox"])
                rect = r if rect is None else rect | r
            if rect is None or rect.y1 < y0 or rect.y0 > y1:
                continue
            band = rect if band is None else band | rect
    return band


def _listing_top(page: fitz.Page, after_y: float) -> float | None:
    hits = page.search_for("Listing")
    below = [h for h in hits if h.y0 >= after_y - 2]
    return min(h.y0 for h in below) if below else None


def extract_figures(
    pdf_path: Path,
    out_dir: Path,
    *,
    page_num: int,
    dpi: int = 200,
) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    with fitz.open(pdf_path) as doc:
        page = doc[0]
        rect = page.rect
        labels = _figure_labels(page)
        if not labels:
            return manifest

        footer_y = _footer_top(page)
        scale = dpi / 72.0
        matrix = fitz.Matrix(scale, scale)

        margin_x = 28
        header_bottom = 130.0

        for i, (fig_id, label, caption_rect) in enumerate(labels):
            cap_y0 = caption_rect.y0
            cap_y1 = caption_rect.y1

            if i + 1 < len(labels):
                next_cap_y0 = labels[i + 1][2].y0
            else:
                next_cap_y0 = footer_y

            listing_y = _listing_top(page, cap_y1)
            prose_hits = page.search_for("In other words")
            prose_after = min((h.y0 for h in prose_hits if h.y0 > cap_y1), default=next_cap_y0)

            # Art may sit above or below the caption — search both bands.
            above_y0 = header_bottom if i == 0 else labels[i - 1][2].y1 + 4
            above_y1 = cap_y0 - 2
            below_y0 = cap_y1 + 2
            below_y1 = min(
                next_cap_y0 - 4,
                listing_y - 4 if listing_y else next_cap_y0 - 4,
                prose_after - 4,
                footer_y,
            )

            art_above = None
            for band_func in (_drawing_band, _image_band, _diagram_text_band):
                res = band_func(page, above_y0, above_y1)
                if res:
                    art_above = res if art_above is None else art_above | res

            art_below = None
            for band_func in (_drawing_band, _image_band, _diagram_text_band):
                res = band_func(page, below_y0, below_y1)
                if res:
                    art_below = res if art_below is None else art_below | res

            def _gap_to_caption(art: fitz.Rect) -> float:
                if art.y1 <= cap_y0:
                    return cap_y0 - art.y1
                if art.y0 >= cap_y1:
                    return art.y0 - cap_y1
                return 0.0

            candidates: list[tuple[float, str, fitz.Rect]] = []
            if art_above:
                candidates.append((_gap_to_caption(art_above), "above", art_above))
            if art_below:
                candidates.append((_gap_to_caption(art_below), "below", art_below))
            if candidates:
                _, where, art = min(candidates, key=lambda x: x[0])
                if where == "above":
                    y0 = max(header_bottom, art.y0 - 8)
                    y1 = min(cap_y1 + 10, art.y1 + 10)
                else:
                    y0 = max(cap_y0 - 6, art.y0 - 8)
                    y1 = min(below_y1, art.y1 + 12)
            else:
                y0 = max(header_bottom, cap_y0 - 120)
                y1 = min(below_y1, cap_y1 + 80)

            # Always include caption lines in the crop.
            y0 = min(y0, cap_y0 - 4)
            y1 = max(y1, cap_y1 + 4)

            if y1 - y0 < 24:
                continue

            clip = fitz.Rect(rect.x0 + margin_x, y0, rect.x1 - margin_x, y1)
            clip &= rect
            pix = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
            safe_id = fig_id.replace("-", "_").replace(".", "_")
            name = f"page_{page_num:04d}_fig_{safe_id}.png"
            out_path = out_dir / name
            pix.save(str(out_path))
            manifest.append(
                {
                    "figure": fig_id,
                    "label": label,
                    "file": f"images/{name}",
                    "width": pix.width,
                    "height": pix.height,
                    "clip": [clip.x0, clip.y0, clip.x1, clip.y1],
                }
            )
    return manifest


def process_book(book_root: Path, pages: list[int] | None = None) -> dict:
    work = book_root / "work"
    assets = book_root / "output" / "assets" / "images"
    manifest_path = book_root / "output" / "assets" / "figures.manifest.json"
    all_manifest: dict[str, list] = {}
    if manifest_path.is_file():
        all_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    targets: list[int] = []
    if pages:
        targets = pages
    else:
        for d in sorted(work.glob("page_*/source.pdf")):
            targets.append(int(d.parent.name.split("_")[1]))

    for n in sorted(targets):
        pdf = work / f"page_{n:04d}" / "source.pdf"
        if not pdf.is_file():
            continue
        figs = extract_figures(pdf, assets, page_num=n)
        if figs:
            all_manifest[f"page_{n:04d}"] = figs
            print(f"page {n:04d}: {len(figs)} figure(s)")

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(all_manifest, indent=2), encoding="utf-8")
    return all_manifest


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: extract_pdf_figures.py <book-root> [page ...]", file=sys.stderr)
        return 2
    book = Path(argv[1]).resolve()
    pages = [int(x) for x in argv[2:]] if len(argv) > 2 else None
    process_book(book, pages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
