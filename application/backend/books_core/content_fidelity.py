"""Source-content and bilingual-structure fidelity gates.

These checks deliberately complement, rather than replace, visual QA.  PDF
text extraction cannot read labels embedded inside raster artwork, so tokens
inside finalized source-pixel crops are excluded from the source/HTML text
comparison.  Everything else must survive into the primary HTML page.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pymupdf as fitz

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_SKIP_TAGS = {"head", "style", "script", "noscript", "template", "title"}
_IGNORED_STRUCTURE_ATTRS = {
    "alt",
    "aria-description",
    "aria-label",
    "content",
    "lang",
    "placeholder",
    "title",
}


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.replace("\u00ad", "").replace("\u2011", "-")
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(normalized):
        token = match.group(0).casefold()
        # PDF text extraction occasionally emits isolated glyph fragments
        # (notably IPA marks or split ligatures). Keep real one-letter words
        # and numeric labels, but avoid treating those fragments as omissions.
        if len(token) == 1 and not token.isdigit() and token not in {"a", "i"}:
            continue
        if len(token) <= 2 and not any(char.isascii() for char in token):
            continue
        tokens.append(token)
    return tokens


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)


def visible_html_tokens(html: str) -> Counter[str]:
    parser = _VisibleTextParser()
    parser.feed(html)
    parser.close()
    return Counter(_tokens(" ".join(parser.parts)))


def _rect_from_values(values: Any) -> fitz.Rect | None:
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        return None
    try:
        rect = fitz.Rect(*(float(value) for value in values))
    except (TypeError, ValueError):
        return None
    return rect if rect.width > 0 and rect.height > 0 else None


def _protected_raster_rects(
    page: fitz.Page,
    plan: dict[str, Any] | None,
) -> list[fitz.Rect]:
    if not plan:
        return []
    rects: list[fitz.Rect] = []
    for figure in plan.get("figures") or []:
        if not isinstance(figure, dict) or figure.get("strategy") != "extract-raster":
            continue
        rect = _rect_from_values(figure.get("crop_bbox") or figure.get("art_bbox"))
        if rect is None:
            normalized = _rect_from_values(figure.get("bbox_normalized"))
            if normalized is not None and all(0 <= value <= 1 for value in normalized):
                rect = fitz.Rect(
                    page.rect.x0 + normalized.x0 * page.rect.width,
                    page.rect.y0 + normalized.y0 * page.rect.height,
                    page.rect.x1 - (1 - normalized.x1) * page.rect.width,
                    page.rect.y1 - (1 - normalized.y1) * page.rect.height,
                )
        if rect is not None:
            rects.append(rect & page.rect)
    return [rect for rect in rects if not rect.is_empty]


def _overlap_ratio(left: fitz.Rect, right: fitz.Rect) -> float:
    intersection = left & right
    if intersection.is_empty or left.get_area() <= 0:
        return 0.0
    return intersection.get_area() / left.get_area()


def source_page_tokens(
    source_pdf: Path,
    *,
    page_num: int,
    plan: dict[str, Any] | None = None,
) -> Counter[str]:
    """Extract source tokens, excluding text inside protected raster crops."""
    with fitz.open(source_pdf) as document:
        pdf_index = 0 if document.page_count == 1 else page_num - 1
        if page_num < 1 or pdf_index < 0 or pdf_index >= document.page_count:
            raise ValueError(f"source page {page_num} is outside the PDF")
        page = document[pdf_index]
        protected = _protected_raster_rects(page, plan)
        result: Counter[str] = Counter()
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = str(span.get("text") or "")
                    rect = _rect_from_values(span.get("bbox"))
                    if rect is not None and any(
                        _overlap_ratio(rect, crop) >= 0.5 for crop in protected
                    ):
                        continue
                    result.update(_tokens(text))
        return result


def validate_source_html_content(
    source_pdf: Path,
    html_path: Path,
    *,
    page_num: int,
    plan: dict[str, Any] | None = None,
) -> list[str]:
    """Require all extractable non-raster source text in the primary HTML."""
    if not source_pdf.is_file():
        return [f"missing source PDF: {source_pdf}"]
    if not html_path.is_file():
        return [f"missing HTML page: {html_path}"]
    source_counts = source_page_tokens(source_pdf, page_num=page_num, plan=plan)
    if not source_counts:
        figures = plan.get("figures") if isinstance(plan, dict) else []
        has_raster = any(
            isinstance(figure, dict) and figure.get("strategy") == "extract-raster"
            for figure in figures or []
        )
        if has_raster or (
            isinstance(plan, dict)
            and isinstance(plan.get("page_layout"), dict)
            and plan["page_layout"].get("facsimile") is True
        ):
            return []
        return [
            f"source page {page_num} has no extractable text and no finalized raster/facsimile plan"
        ]

    html_counts = visible_html_tokens(html_path.read_text(encoding="utf-8"))
    missing = source_counts - html_counts
    if not missing:
        return []
    missing_text = ", ".join(
        f"{token}×{count}" if count > 1 else token
        for token, count in missing.most_common(20)
    )
    return [
        f"source text missing from HTML ({sum(missing.values())} token(s)): {missing_text}"
    ]


class _StructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.signature: list[tuple[Any, ...]] = []

    def _attrs(self, attrs: list[tuple[str, str | None]]) -> tuple[tuple[str, str], ...]:
        selected = []
        for key, value in attrs:
            key = key.casefold()
            if key in _IGNORED_STRUCTURE_ATTRS:
                continue
            selected.append((key, value or ""))
        return tuple(sorted(selected))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.signature.append(("start", tag.casefold(), self._attrs(attrs)))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.signature.append(("startend", tag.casefold(), self._attrs(attrs)))

    def handle_endtag(self, tag: str) -> None:
        self.signature.append(("end", tag.casefold()))


def html_structure_signature(html: str) -> list[tuple[Any, ...]]:
    parser = _StructureParser()
    parser.feed(html)
    parser.close()
    return parser.signature


def validate_bilingual_structure(
    source_html: Path,
    translated_html: Path,
) -> list[str]:
    """Ensure translation edits text, not layout, assets, or visual structure."""
    if not source_html.is_file():
        return [f"missing source-language HTML: {source_html}"]
    if not translated_html.is_file():
        return [f"missing translated HTML: {translated_html}"]
    source = source_html.read_text(encoding="utf-8")
    translated = translated_html.read_text(encoding="utf-8")
    source_sig = html_structure_signature(source)
    translated_sig = html_structure_signature(translated)
    if source_sig == translated_sig:
        return []
    first = next(
        (
            index
            for index, pair in enumerate(zip(source_sig, translated_sig))
            if pair[0] != pair[1]
        ),
        min(len(source_sig), len(translated_sig)),
    )
    return [
        "translated HTML changed structural/layout signature at "
        f"token {first} (source length {len(source_sig)}, "
        f"translated length {len(translated_sig)})"
    ]
