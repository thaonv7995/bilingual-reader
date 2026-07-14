#!/usr/bin/env python3
"""Replace ascii-figure diagrams with PDF-extracted PNGs where available."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Allow imports from backend when run as a standalone script.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from books_core.asset_paths import normalize_per_page_asset_paths  # noqa: E402
from books_core.figure_dimensions import (  # noqa: E402
    figure_display_dimensions,
    figure_display_style,
)


def _fig_id_from_caption(html: str) -> str | None:
    visible_text = re.sub(r"<[^>]+>", " ", html)
    m = re.search(
        r"(?:Figure|Hình)\s+([A-Za-z\d]+(?:[-.]\d+)?)",
        visible_text,
        re.I,
    )
    return m.group(1) if m else None


def _ensure_figures_css(html: str) -> str:
    if "figures-page.css" in html:
        return html
    prose_link = re.compile(
        r"<link\b[^>]*href\s*=\s*([\"'])\.\./assets/prose-page\.css\1[^>]*>",
        re.IGNORECASE,
    )
    return prose_link.sub(
        lambda m: f'{m.group(0)}\n  <link rel="stylesheet" href="../assets/figures-page.css">',
        html,
        count=1,
    )


def upgrade_page(html_path: Path, manifest: dict[str, list]) -> bool:
    page_key = f"page_{int(html_path.stem.split('_')[1]):04d}"
    figs = {f["figure"]: f for f in manifest.get(page_key, [])}
    original = html_path.read_text(encoding="utf-8")
    html = normalize_per_page_asset_paths(original)
    if not figs:
        if html != original:
            html_path.write_text(html, encoding="utf-8")
            return True
        return False

    def repl(match: re.Match[str]) -> str:
        block = match.group(0)
        fig_id = _fig_id_from_caption(block)
        if not fig_id or fig_id not in figs:
            return block
        info = figs[fig_id]
        dimensions = figure_display_dimensions(info)
        display_style = figure_display_style(info)
        style_attr = f' style="{display_style}"' if display_style else ""
        cap_m = re.search(r"<figcaption>(.*?)</figcaption>", block, re.DOTALL)
        caption = cap_m.group(0) if cap_m else ""
        return (
            f'<figure class="diagram">\n'
            f'  <img src="../assets/{info["file"]}" width="{dimensions.width_px}" '
            f'height="{dimensions.height_px}"{style_attr} '
            f'alt="Figure {fig_id}">\n'
            f"  {caption}\n"
            f"</figure>"
        )

    html = re.sub(
        r'<figure\b[^>]*class=["\'][^"\']*\bdiagram\b[^"\']*["\'][^>]*>.*?'
        r'<pre\b[^>]*class=["\'][^"\']*\bascii-figure\b[^"\']*["\'][^>]*>.*?'
        r'</pre>\s*</figure>',
        repl,
        html,
        flags=re.DOTALL,
    )

    if figs:
        html = _ensure_figures_css(html)

    if html != original:
        html_path.write_text(html, encoding="utf-8")
        return True
    return False


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: upgrade_figure_html.py <book-root>", file=sys.stderr)
        return 2
    book = Path(argv[1]).resolve()
    manifest_path = book / "output" / "assets" / "figures.manifest.json"
    if not manifest_path.is_file():
        print(f"Missing {manifest_path} — run extract_pdf_figures.py first", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed = 0
    for pages_dir in sorted((book / "output").iterdir()):
        if not pages_dir.is_dir():
            continue
        for path in sorted(pages_dir.glob("page_*.html")):
            if upgrade_page(path, manifest):
                changed += 1
                print(f"upgraded {pages_dir.name}/{path.name}")
    print(f"Done — {changed} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
