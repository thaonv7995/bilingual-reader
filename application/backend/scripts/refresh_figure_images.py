#!/usr/bin/env python3
"""Update figure <img> tags from figures.manifest.json — safe full-tag replace."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _figure_ids_in_html(html: str) -> list[str]:
    ids: list[str] = []
    for m in re.finditer(
        r"<figcaption>[^<]*(?:Figure|Hình)\s+(\d+[-.]\d+)",
        html,
        flags=re.IGNORECASE,
    ):
        ids.append(m.group(1))
    for m in re.finditer(r'alt="(?:Figure|Hình)\s+(\d+[-.]\d+)"', html, flags=re.IGNORECASE):
        if m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


def _replace_img_in_figure(html: str, fig_id: str, info: dict) -> str:
    """Replace the <img> inside the figure that references fig_id."""
    src = f'../assets/{info["file"]}'
    w, h = info["width"], info["height"]

    # Match figure block containing this fig_id in figcaption or alt
    pattern = (
        rf'(<figure class="diagram">.*?<img\s+)[^>]+(>.*?'
        rf'(?:Figure|Hình)\s+{re.escape(fig_id)}.*?</figure>)'
    )

    def repl(m: re.Match[str]) -> str:
        # Preserve alt from existing tag if present
        block = m.group(0)
        alt_m = re.search(r'alt="([^"]*)"', block)
        alt = alt_m.group(1) if alt_m else f"Figure {fig_id}"
        return (
            f'{m.group(1)}src="{src}" width="{w}" height="{h}" alt="{alt}"{m.group(2)}'
        )

    return re.sub(pattern, repl, html, count=1, flags=re.DOTALL | re.IGNORECASE)


def refresh_page(html_path: Path, manifest: dict[str, list]) -> bool:
    page_key = f"page_{int(html_path.stem.split('_')[1]):04d}"
    figs = {f["figure"]: f for f in manifest.get(page_key, [])}
    if not figs:
        return False

    html = html_path.read_text(encoding="utf-8")
    original = html

    for fig_id, info in figs.items():
        html = _replace_img_in_figure(html, fig_id, info)

    if "figures-page.css" not in html and figs:
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
        print("Usage: refresh_figure_images.py <book-root>", file=sys.stderr)
        return 2
    book = Path(argv[1]).resolve()
    manifest_path = book / "output/assets/figures.manifest.json"
    if not manifest_path.is_file():
        print(f"Missing {manifest_path}", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed = 0
    for pages_dir in sorted((book / "output").iterdir()):
        if not pages_dir.is_dir():
            continue
        for path in sorted(pages_dir.glob("page_*.html")):
            if refresh_page(path, manifest):
                changed += 1
                print(f"{pages_dir.name}/{path.name}")
    print(f"refreshed {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
