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
    lang: str | None = None,
    output_name: str | None = None,
) -> dict[str, object]:
    """
    Join output/<lang>/page_NNNN.html → output/book.html (one file, print-ready).
    """
    lang = lang or book.default_lang()
    if output_name is None:
        if lang == book.default_lang():
            output_name = "book.html"
        else:
            output_name = f"book.{lang}.html"
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

    ipa_style = ""
    if lang == "en-ipa":
        ipa_style = """
  <style>
    /* IPA Interlinear Translation Styles */
    .word-wrapper {
      display: inline-flex !important;
      flex-direction: column !important;
      align-items: center !important;
      vertical-align: top !important;
      margin-left: -0.03em !important;
      margin-right: -0.03em !important;
      line-height: 1.1 !important;
      text-indent: 0 !important;
    }
    .en-word {
      display: block !important;
    }
    .ipa-word {
      display: block !important;
      font-size: 0.74em !important;
      color: var(--book-ink, #111111) !important;
      font-family: Arial, Helvetica, sans-serif !important;
      text-transform: none !important;
      font-weight: normal !important;
      font-style: italic !important;
      margin-top: 0.5mm !important;
      user-select: none !important;
      text-align: center !important;
    }
    .book-page p, 
    .book-page li, 
    .book-page h1, 
    .book-page h2, 
    .book-page h3, 
    .book-page h4, 
    .book-page h5, 
    .book-page h6, 
    .book-page div:not(.toc-list):not(.toc-frontmatter):not(.toc-chapters):not(.toc-section):not(.word-wrapper) {
      line-height: 2.1 !important;
      text-align: left !important;
    }
    .book-page.book-page--sheet {
      height: auto !important;
      min-height: 0 !important;
      max-height: none !important;
      overflow: visible !important;
      background: transparent !important;
      box-shadow: none !important;
      padding: 0 !important;
      margin: 0 !important;
      width: auto !important;
    }
    .sheet-flow {
      height: auto !important;
      overflow: visible !important;
      padding: 0 !important;
      margin: 0 !important;
    }
    .ipa-sub-sheet {
      box-sizing: border-box;
      width: 210mm;
      height: 297mm;
      padding: 20mm 20mm 15mm 20mm;
      position: relative;
      background: white;
      box-shadow: 0 16px 44px rgba(15, 23, 42, 0.18);
      margin: 0 auto 10mm auto;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      justify-content: flex-start;
    }
    @media print {
      .ipa-sub-sheet {
        margin: 0 !important;
        box-shadow: none !important;
        page-break-after: always !important;
      }
      .book-page {
        height: auto !important;
        min-height: 0 !important;
        max-height: none !important;
        overflow: visible !important;
        page-break-after: avoid !important;
        page-break-before: avoid !important;
      }
    }
  </style>"""

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
  </style>{ipa_style}
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
