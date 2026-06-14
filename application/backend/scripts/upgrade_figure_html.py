#!/usr/bin/env python3
"""Replace ascii-figure diagrams with PDF-extracted PNGs where available."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _fig_id_from_caption(html: str) -> str | None:
    m = re.search(r"Figure\s+(\d+[-.]\d+)", html, re.I)
    return m.group(1) if m else None


def upgrade_page(html_path: Path, manifest: dict[str, list]) -> bool:
    page_key = f"page_{int(html_path.stem.split('_')[1]):04d}"
    figs = {f["figure"]: f for f in manifest.get(page_key, [])}
    if not figs:
        return False

    html = html_path.read_text(encoding="utf-8")
    original = html

    def repl(match: re.Match[str]) -> str:
        block = match.group(0)
        fig_id = _fig_id_from_caption(block)
        if not fig_id or fig_id not in figs:
            return block
        info = figs[fig_id]
        cap_m = re.search(r"<figcaption>(.*?)</figcaption>", block, re.DOTALL)
        caption = cap_m.group(0) if cap_m else ""
        return (
            f'<figure class="diagram">\n'
            f'  <img src="../assets/{info["file"]}" width="{info["width"]}" height="{info["height"]}" '
            f'alt="Figure {fig_id}">\n'
            f"  {caption}\n"
            f"</figure>"
        )

    html = re.sub(
        r'<figure class="diagram">.*?<pre class="ascii-figure">.*?</pre>\s*</figure>',
        repl,
        html,
        flags=re.DOTALL,
    )

    if "figures-page.css" not in html:
        html = html.replace(
            '<link rel="stylesheet" href="../assets/prose-page.css">',
            '<link rel="stylesheet" href="../assets/prose-page.css">\n'
            '  <link rel="stylesheet" href="../assets/figures-page.css">',
            1,
        )

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
    pages_dir = book / "output" / "en"
    changed = 0
    for path in sorted(pages_dir.glob("page_*.html")):
        if upgrade_page(path, manifest):
            changed += 1
            print(f"upgraded {path.name}")
    print(f"Done — {changed} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
