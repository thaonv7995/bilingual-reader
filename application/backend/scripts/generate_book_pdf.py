#!/usr/bin/env python3
"""Script to compile HTML books to PDF using Playwright."""

import sys
import asyncio
from pathlib import Path

async def generate_pdf(html_path: Path, pdf_path: Path):
    from playwright.async_api import async_playwright
    
    async with async_playwright() as pw:
        print("Launching Chromium...")
        browser = await pw.chromium.launch()
        context = await browser.new_context(viewport={"width": 794, "height": 1123})
        page = await context.new_page()
        
        print(f"Loading {html_path}...")
        # Resolve path to absolute file:// URL
        abs_url = f"file://{html_path.resolve()}"
        await page.goto(abs_url, wait_until="networkidle", timeout=60000)
        broken_images = await page.eval_on_selector_all(
            "img",
            "imgs => imgs.filter(img => !img.complete || img.naturalWidth === 0).map(img => img.currentSrc || img.src)",
        )
        if broken_images:
            raise RuntimeError(f"Cannot generate PDF with broken images: {broken_images}")
        
        print(f"Generating PDF at {pdf_path}...")
        # Print to PDF with standard A4 size and no margins to let A4 CSS sub-sheets work perfectly
        await page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            margin={"top": "0px", "right": "0px", "bottom": "0px", "left": "0px"},
            prefer_css_page_size=True
        )
        await browser.close()
    print("PDF generation complete!")

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 generate_book_pdf.py <input.html> <output.pdf>")
        sys.exit(1)
        
    html_path = Path(sys.argv[1])
    pdf_path = Path(sys.argv[2])
    
    if not html_path.is_file():
        print(f"Error: {html_path} does not exist.")
        sys.exit(1)
        
    # Ensure parent output directory exists
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    
    asyncio.run(generate_pdf(html_path, pdf_path))

if __name__ == "__main__":
    main()
