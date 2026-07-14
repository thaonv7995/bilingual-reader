"""Keep extracted raster resolution separate from PDF display dimensions."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import re
from typing import Any, Mapping


PDF_POINTS_PER_INCH = 72.0
CSS_PIXELS_PER_INCH = 96.0
MM_PER_INCH = 25.4
_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE | re.DOTALL)
_IMG_SRC_RE = re.compile(r"\bsrc\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class FigureDisplayDimensions:
    """Dimensions used by HTML, independent of the PNG raster resolution."""

    width_px: int
    height_px: int
    width_mm: float | None = None

    @property
    def width_css(self) -> str | None:
        if self.width_mm is None:
            return None
        value = f"{self.width_mm:.3f}".rstrip("0").rstrip(".")
        return f"{value}mm"


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and number > 0 else None


def _display_points(info: Mapping[str, Any]) -> tuple[float, float] | None:
    width = _positive_number(info.get("display_width_pt"))
    height = _positive_number(info.get("display_height_pt"))
    if width is not None and height is not None:
        return width, height

    clip = info.get("clip")
    if not isinstance(clip, (list, tuple)) or len(clip) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(value) for value in clip)
    except (TypeError, ValueError):
        return None
    width = _positive_number(x1 - x0)
    height = _positive_number(y1 - y0)
    if width is None or height is None:
        return None
    return width, height


def figure_display_dimensions(info: Mapping[str, Any]) -> FigureDisplayDimensions:
    """Return CSS display dimensions while supporting old manifests without clips."""
    points = _display_points(info)
    if points is not None:
        width_pt, height_pt = points
        return FigureDisplayDimensions(
            width_px=max(1, round(width_pt * CSS_PIXELS_PER_INCH / PDF_POINTS_PER_INCH)),
            height_px=max(1, round(height_pt * CSS_PIXELS_PER_INCH / PDF_POINTS_PER_INCH)),
            width_mm=width_pt * MM_PER_INCH / PDF_POINTS_PER_INCH,
        )

    # Legacy manifests did not distinguish raster and display dimensions. Keep
    # their established behavior when the source PDF crop is unavailable.
    width = (
        _positive_number(info.get("width"))
        or _positive_number(info.get("raster_width"))
        or 1
    )
    height = (
        _positive_number(info.get("height"))
        or _positive_number(info.get("raster_height"))
        or 1
    )
    return FigureDisplayDimensions(width_px=round(width), height_px=round(height))


def figure_display_style(info: Mapping[str, Any]) -> str | None:
    """Return a print-accurate inline style for manifests with PDF geometry."""
    width_css = figure_display_dimensions(info).width_css
    if width_css is None:
        return None
    return f"width: {width_css}; max-width: 100%; height: auto;"


def _set_img_attr(tag: str, name: str, value: str) -> str:
    pattern = re.compile(
        rf"(\s{name}\s*=\s*)([\"']).*?\2",
        re.IGNORECASE | re.DOTALL,
    )
    if pattern.search(tag):
        return pattern.sub(lambda match: f'{match.group(1)}"{value}"', tag, count=1)
    insert_at = tag.rfind("/>") if tag.rstrip().endswith("/>") else tag.rfind(">")
    return f'{tag[:insert_at].rstrip()} {name}="{value}"{tag[insert_at:]}'


def _set_display_style(tag: str, display_style: str) -> str:
    """Replace only sizing declarations, preserving unrelated inline styles."""
    style_match = re.search(
        r"\sstyle\s*=\s*([\"'])(.*?)\1",
        tag,
        flags=re.IGNORECASE | re.DOTALL,
    )
    existing = style_match.group(2) if style_match else ""
    kept = []
    for declaration in existing.split(";"):
        declaration = declaration.strip()
        if not declaration or ":" not in declaration:
            continue
        name = declaration.split(":", 1)[0].strip().lower()
        if name not in {"width", "max-width", "height"}:
            kept.append(declaration)
    merged = "; ".join([*kept, display_style.rstrip(";")]) + ";"
    return _set_img_attr(tag, "style", merged)


def apply_figure_display_to_img_tag(tag: str, info: Mapping[str, Any]) -> str:
    """Apply PDF display geometry to one image tag without lowering PNG quality."""
    dimensions = figure_display_dimensions(info)
    tag = _set_img_attr(tag, "width", str(dimensions.width_px))
    tag = _set_img_attr(tag, "height", str(dimensions.height_px))
    display_style = figure_display_style(info)
    if display_style:
        tag = _set_display_style(tag, display_style)
    return tag


def normalize_figure_display_html(
    html: str,
    figures: list[Mapping[str, Any]],
) -> str:
    """Repair extracted figure sizes in existing page HTML during repack."""
    figures_by_name = {
        Path(str(info.get("file") or "")).name: info
        for info in figures
        if info.get("file")
    }
    if not figures_by_name:
        return html

    def replace_img(match: re.Match[str]) -> str:
        tag = match.group(0)
        src_match = _IMG_SRC_RE.search(tag)
        if not src_match:
            return tag
        filename = Path(src_match.group(2).split("?", 1)[0].split("#", 1)[0]).name
        info = figures_by_name.get(filename)
        return apply_figure_display_to_img_tag(tag, info) if info else tag

    return _IMG_TAG_RE.sub(replace_img, html)
