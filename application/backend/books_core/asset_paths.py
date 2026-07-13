"""Asset URL rules for per-page vs assembled book HTML."""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

# Per-page: output/<lang>/page_NNNN.html → output/assets/
PER_PAGE_ASSET_PREFIX = "../assets/"

# Assembled: output/book.html → output/assets/
ASSEMBLED_ASSET_PREFIX = "assets/"

_IMG_SRC_RE = re.compile(
    r"<img\s+[^>]*\bsrc\s*=\s*([\"'])(.*?)\1",
    re.IGNORECASE | re.DOTALL,
)
_VALID_IMG = re.compile(
    r"^(\.\./assets/|assets/)images/[a-zA-Z0-9_./-]+\.(png|jpg|jpeg|gif|webp|svg)$"
)

# Rewrite every per-page asset prefix when joining into output/book*.html
_PER_PAGE_ASSET_RE = re.compile(r"""(\.\./assets/)""")
_URL_ATTR_RE = re.compile(
    r"(?P<head>\b(?:src|href|poster|data)\s*=\s*)(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)
_SRCSET_ATTR_RE = re.compile(
    r"(?P<head>\bsrcset\s*=\s*)(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)
_CSS_URL_RE = re.compile(
    r"(?P<head>url\(\s*(?:[\"'])?)assets/",
    re.IGNORECASE,
)


def normalize_per_page_asset_paths(html: str) -> str:
    """Rewrite legacy bare asset URLs for HTML under output/<lang>/."""

    def rewrite_url_attr(match: re.Match[str]) -> str:
        value = match.group("value")
        if value.startswith(ASSEMBLED_ASSET_PREFIX):
            value = PER_PAGE_ASSET_PREFIX + value[len(ASSEMBLED_ASSET_PREFIX) :]
        return f'{match.group("head")}{match.group("quote")}{value}{match.group("quote")}'

    def rewrite_srcset_attr(match: re.Match[str]) -> str:
        value = re.sub(
            r"(^|,\s*)assets/",
            lambda m: f"{m.group(1)}{PER_PAGE_ASSET_PREFIX}",
            match.group("value"),
            flags=re.IGNORECASE,
        )
        return f'{match.group("head")}{match.group("quote")}{value}{match.group("quote")}'

    html = _URL_ATTR_RE.sub(rewrite_url_attr, html)
    html = _SRCSET_ATTR_RE.sub(rewrite_srcset_attr, html)
    return _CSS_URL_RE.sub(rf"\g<head>{PER_PAGE_ASSET_PREFIX}", html)


def normalize_per_page_asset_file(path: Path) -> bool:
    """Canonicalize asset URLs in one page file and report whether it changed."""
    original = path.read_text(encoding="utf-8")
    normalized = normalize_per_page_asset_paths(original)
    if normalized == original:
        return False
    path.write_text(normalized, encoding="utf-8")
    return True


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
    if context.startswith("per-page") and not src.startswith(PER_PAGE_ASSET_PREFIX):
        issues.append(f"per-page HTML must use ../assets/: {src!r}")
    return issues


def lint_images_in_html(
    html: str,
    *,
    context: str,
    book_root: Path | None = None,
) -> list[str]:
    issues: list[str] = []
    for m in _IMG_SRC_RE.finditer(html):
        src = m.group(2)
        src_issues = lint_image_src(src, context=context)
        issues.extend(src_issues)
        if src_issues:
            continue
        if book_root is not None:
            if context.startswith("assembled"):
                path = book_root / "output" / src
            elif src.startswith(PER_PAGE_ASSET_PREFIX):
                path = book_root / "output" / src.removeprefix("../")
            else:
                page_context = context.removeprefix("per-page ")
                lang = page_context.split("/", 1)[0]
                path = book_root / "output" / lang / src
            if not path.is_file():
                issues.append(f"missing image file {path.relative_to(book_root)} ({context})")
    return issues
