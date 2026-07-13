#!/usr/bin/env python3
"""Update figure <img> tags from figures.manifest.json — safe full-tag replace."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Allow imports from backend when run as a standalone script.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from books_core.asset_paths import (  # noqa: E402
    normalize_per_page_asset_paths,
    resolve_relative_asset,
)


_FIGURE_BLOCK_RE = re.compile(r"<figure\b[^>]*>.*?</figure>", re.IGNORECASE | re.DOTALL)
_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE | re.DOTALL)
_IMG_SRC_RE = re.compile(r"\bsrc\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)


def _set_img_attr(tag: str, name: str, value: str) -> str:
    pattern = re.compile(
        rf"(\s{name}\s*=\s*)([\"']).*?\2",
        re.IGNORECASE | re.DOTALL,
    )
    if pattern.search(tag):
        return pattern.sub(lambda m: f'{m.group(1)}"{value}"', tag, count=1)
    insert_at = tag.rfind("/>") if tag.rstrip().endswith("/>") else tag.rfind(">")
    return f'{tag[:insert_at].rstrip()} {name}="{value}"{tag[insert_at:]}'


def _replace_img_in_figure(html: str, fig_id: str, info: dict) -> str:
    """Update only image URL/dimensions while preserving the rest of the tag."""
    src = f'../assets/{info["file"]}'
    expected_name = Path(info["file"]).name
    label_re = re.compile(
        rf"(?:Figure|Hình)\s+{re.escape(fig_id)}(?![.-]\d)",
        re.IGNORECASE,
    )
    updated = False

    def replace_block(match: re.Match[str]) -> str:
        nonlocal updated
        block = match.group(0)
        if updated:
            return block
        img_match = _IMG_TAG_RE.search(block)
        if not img_match:
            return block
        current_src = _IMG_SRC_RE.search(img_match.group(0))
        current_name = ""
        if current_src:
            current_name = Path(current_src.group(2).split("?", 1)[0]).name
        if not label_re.search(block) and current_name != expected_name:
            return block

        tag = img_match.group(0)
        tag = _set_img_attr(tag, "src", src)
        tag = _set_img_attr(tag, "width", str(info["width"]))
        tag = _set_img_attr(tag, "height", str(info["height"]))
        if not re.search(r"\balt\s*=", tag, flags=re.IGNORECASE):
            tag = _set_img_attr(tag, "alt", f"Figure {fig_id}")
        updated = True
        return f"{block[:img_match.start()]}{tag}{block[img_match.end():]}"

    return _FIGURE_BLOCK_RE.sub(replace_block, html)


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


def refresh_page(html_path: Path, manifest: dict[str, list]) -> bool:
    page_key = f"page_{int(html_path.stem.split('_')[1]):04d}"
    figs = {f["figure"]: f for f in manifest.get(page_key, [])}

    original = html_path.read_text(encoding="utf-8")
    html = normalize_per_page_asset_paths(original)

    for fig_id, info in figs.items():
        html = _replace_img_in_figure(html, fig_id, info)

    if figs:
        html = _ensure_figures_css(html)

    missing_refs: set[str] = set()
    for src_match in _IMG_SRC_RE.finditer(html):
        src = src_match.group(2)
        if "page_" in src and "_fig_" in src:
            if not resolve_relative_asset(html_path.parent, src).is_file():
                missing_refs.add(src)
    for src in sorted(missing_refs):
        print(f"WARN {html_path}: missing figure asset {src}", file=sys.stderr)

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
