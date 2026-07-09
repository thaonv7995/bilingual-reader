"""Asset URL rules for per-page vs assembled book HTML."""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

# Per-page: output/<lang>/page_NNNN.html → output/assets/
PER_PAGE_ASSET_PREFIX = "assets/"

# Assembled: output/book.html → output/assets/
ASSEMBLED_ASSET_PREFIX = "assets/"

_IMG_SRC_RE = re.compile(r'<img\s+[^>]*\bsrc="([^"]+)"', re.IGNORECASE)
_VALID_IMG = re.compile(
    r"^(\.\./assets/|assets/)images/[a-zA-Z0-9_./-]+\.(png|jpg|jpeg|gif|webp|svg)$"
)

# Rewrite every per-page asset prefix when joining into output/book*.html
_PER_PAGE_ASSET_RE = re.compile(r"""(\.\./assets/)""")


def rewrite_per_page_assets_to_assembled(html: str) -> str:
    """Map ../assets/... → assets/... for HTML that lives under output/."""
    return _PER_PAGE_ASSET_RE.sub(ASSEMBLED_ASSET_PREFIX, html)


def resolve_relative_asset(html_dir: Path, ref: str) -> Path:
    """Resolve a relative href/src against the directory that contains the HTML file."""
    clean = urllib.parse.unquote((ref or "").split("?", 1)[0].split("#", 1)[0])
    return (html_dir / clean).resolve()


def per_page_asset_base(book_root: Path, lang: str = "en") -> Path:
    """Directory that ../assets/ is relative to for standalone pages."""
    return (Path(book_root) / "output" / lang).resolve()


def lint_image_src(src: str, *, context: str) -> list[str]:
    """Return issues for a single img src value."""
    issues: list[str] = []
    if not _VALID_IMG.match(src):
        issues.append(f"invalid img src {src!r} in {context}")
        return issues
    if context.startswith("assembled") and src.startswith("../"):
        issues.append(f"assembled book must use assets/ not ../assets/: {src!r}")
    if context.startswith("per-page") and not src.startswith("assets/"):
        issues.append(f"per-page HTML must use assets/: {src!r}")
    return issues


def lint_images_in_html(
    html: str,
    *,
    context: str,
    book_root: Path | None = None,
) -> list[str]:
    issues: list[str] = []
    for m in _IMG_SRC_RE.finditer(html):
        src = m.group(1)
        issues.extend(lint_image_src(src, context=context))
        if book_root is not None:
            rel = src.removeprefix("../")
            path = book_root / "output" / rel
            if not path.is_file():
                issues.append(f"missing image file {path.relative_to(book_root)} ({context})")
    return issues
