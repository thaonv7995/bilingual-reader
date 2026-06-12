"""Merge per-page HTML into one full-book HTML file."""

from __future__ import annotations

import re
from pathlib import Path

from books_core.io import atomic_write_text
from books_core.paths import BookPaths


def _page_numbers(book: BookPaths, lang: str) -> list[int]:
    pages_dir = book.pages_dir(lang)
    if not pages_dir.is_dir():
        return []
    nums: list[int] = []
    for p in sorted(pages_dir.glob("page_*.html")):
        try:
            nums.append(int(p.stem.split("_")[1]))
        except ValueError:
            continue
    return nums


def _extract_body(html: str) -> str:
    """Pull printable content from a standalone page."""
    m = re.search(r"<article[^>]*>(.*)</article>", html, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"<main[^>]*>(.*)</main>", html, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"<body[^>]*>(.*)</body>", html, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return html.strip()


def assemble_book_html(
    book: BookPaths,
    *,
    lang: str | None = None,
    output_name: str = "book.html",
) -> dict[str, object]:
    """
    Join output/<lang>/page_NNNN.html → output/book.html (one file, print-ready).
    """
    lang = lang or book.default_lang()
    pages = _page_numbers(book, lang)
    if not pages:
        raise FileNotFoundError(
            f"No pages in {book.pages_dir(lang).relative_to(book.root)} — run render first."
        )

    meta = book.load_book_json()
    title = str(meta.get("title") or book.root.name)
    sections: list[str] = []

    assets = book.output_dir / "assets"
    extra_css: list[str] = ["assets/book.css", "assets/page-tokens.css", "assets/prose-page.css"]
    for name, href in (
        ("code-page.css", "assets/code-page.css"),
        ("figures-page.css", "assets/figures-page.css"),
    ):
        if (assets / name).is_file():
            extra_css.append(href)

    css_links = "\n".join(f'  <link rel="stylesheet" href="{href}">' for href in extra_css)

    for n in pages:
        page_path = book.page_lang_html(n, lang)
        html = page_path.read_text(encoding="utf-8")
        body = _extract_body(html)
        # Per-page HTML uses ../assets/; assembled book lives in output/ → assets/
        body = body.replace('src="../assets/', 'src="assets/')
        sections.append(
            f'<section class="book-sheet" id="page-{n:04d}" data-page="{n}">\n'
            f'  <main class="book-page book-page--sheet">\n'
            f'    <article class="sheet-flow prose-page">\n{body}\n'
            f"    </article>\n"
            f"  </main>\n"
            f"</section>"
        )

    combined = f"""<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
{css_links}
  <style>
    @media print {{
      .book-page {{ height: 296mm; }}
    }}
  </style>
</head>
<body class="book-standalone book-full">
  <main class="book-full__main">
{chr(10).join(sections)}
  </main>
</body>
</html>
"""
    out = book.output_dir / output_name
    atomic_write_text(out, combined)
    return {
        "ok": True,
        "book": str(book.root),
        "lang": lang,
        "pages": len(pages),
        "page_range": [pages[0], pages[-1]],
        "output": str(out.relative_to(book.root)),
    }
