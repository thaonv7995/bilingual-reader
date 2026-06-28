#!/usr/bin/env python3
"""Script to assemble and render books in chunks of 50 pages to HTML and PDF."""

import sys
import asyncio
import re
import json
from pathlib import Path

# Allow imports from backend
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from books_core.paths import BookPaths
from books_core.io import atomic_write_text

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

async def render_pdf_file(html_path: Path, pdf_path: Path):
    from playwright.async_api import async_playwright
    
    async with async_playwright() as pw:
        print(f"Launching Chromium for {html_path.name}...")
        browser = await pw.chromium.launch()
        context = await browser.new_context(viewport={"width": 794, "height": 1123})
        page = await context.new_page()
        abs_url = f"file://{html_path.resolve()}"
        print(f"Loading page {abs_url}...")
        await page.goto(abs_url, wait_until="load", timeout=30000)
        
        print(f"Printing PDF to {pdf_path.name}...")
        await page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            margin={"top": "0px", "right": "0px", "bottom": "0px", "left": "0px"},
            prefer_css_page_size=True
        )
        await browser.close()

def assemble_part_html(book: BookPaths, pages_list: list[int], lang: str, output_name: str):
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

    for n in pages_list:
        page_path = book.page_lang_html(n, lang)
        if not page_path.is_file():
            print(f"Warning: Page {n} does not exist. Skipping.")
            continue
        html_content = page_path.read_text(encoding="utf-8")
        body = _extract_body(html_content)
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
  <title>{title} - Part</title>
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
    out_path = book.output_dir / output_name
    atomic_write_text(out_path, combined)
    return out_path

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 assemble_and_render_parts.py <book_dir>")
        sys.exit(1)
        
    book_dir = Path(sys.argv[1]).resolve()
    book = BookPaths.open(book_dir)
    lang = "en-ipa"
    
    pages_dir = book.pages_dir(lang)
    if not pages_dir.is_dir():
        print(f"Error: No pages found for {lang} at {pages_dir}")
        sys.exit(1)
        
    # Get all page numbers
    all_pages = []
    for p in sorted(pages_dir.glob("page_*.html")):
        try:
            all_pages.append(int(p.stem.split("_")[1]))
        except ValueError:
            continue
            
    if not all_pages:
        print("No pages found to assemble.")
        sys.exit(1)
        
    # Split into 50-page chunks
    chunk_size = 50
    chunks = [all_pages[i:i + chunk_size] for i in range(0, len(all_pages), chunk_size)]
    
    print(f"Total pages: {len(all_pages)}. Splitting into {len(chunks)} parts (50 pages each).")
    
    for idx, chunk in enumerate(chunks):
        part_num = idx + 1
        start_p = chunk[0]
        end_p = chunk[-1]
        
        html_name = f"book.en-ipa.part{part_num:02d}.html"
        pdf_name = f"book.en-ipa.part{part_num:02d}.pdf"
        
        print(f"\n--- Part {part_num} (Pages {start_p} to {end_p}) ---")
        
        # 1. Assemble HTML
        html_path = assemble_part_html(book, chunk, lang, html_name)
        print(f"  Assembled HTML: {html_path.name}")
        
        # 2. Render to PDF
        pdf_path = book.output_dir / pdf_name
        asyncio.run(render_pdf_file(html_path, pdf_path))
        print(f"  Generated PDF: {pdf_path.name}")
        
    print("\nAll parts assembled and rendered successfully!")

if __name__ == "__main__":
    main()
