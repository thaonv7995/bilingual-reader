"""Print assembled HTML books to verified A4 PDFs with headless Chromium."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import pymupdf as fitz


_BROWSER_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)

_PRINT_SAFETY_CSS = """
@media print {
  html, body { overflow: visible !important; }
  body.book-full .book-full__main { display: block !important; }
  .book-sheet { break-inside: avoid !important; page-break-inside: avoid !important; }
  .book-page { overflow: hidden !important; }
}
"""


def find_chromium() -> Path:
    configured = os.environ.get("BOOKS_CHROME_BIN") or os.environ.get("CHROME_PATH")
    candidates = ([configured] if configured else []) + list(_BROWSER_CANDIDATES)
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        discovered = shutil.which(name)
        if discovered:
            candidates.append(discovered)
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise FileNotFoundError(
        "Chromium/Google Chrome was not found. Install chromium or set BOOKS_CHROME_BIN."
    )


def _validate_pdf(pdf_path: Path, *, expected_pages: int) -> dict[str, Any]:
    if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        raise RuntimeError(f"PDF export did not create a non-empty file: {pdf_path}")
    with fitz.open(pdf_path) as document:
        actual_pages = document.page_count
        if actual_pages != expected_pages:
            raise RuntimeError(
                f"PDF page count mismatch: HTML has {expected_pages} sheets, PDF has {actual_pages} pages"
            )
        non_a4: list[int] = []
        for index, page in enumerate(document, start=1):
            width, height = page.rect.width, page.rect.height
            if abs(width - 595.28) > 3 or abs(height - 841.89) > 3:
                non_a4.append(index)
        if non_a4:
            raise RuntimeError(f"PDF contains non-A4 pages: {non_a4[:10]}")
    return {
        "path": str(pdf_path),
        "pages": actual_pages,
        "bytes": pdf_path.stat().st_size,
    }


async def export_html_pdf(
    html_path: Path,
    pdf_path: Path,
    *,
    browser_path: Path | None = None,
    timeout_ms: int = 180_000,
) -> dict[str, Any]:
    """Print one assembled book HTML atomically and verify page count/A4 size."""
    html_path = Path(html_path).resolve()
    pdf_path = Path(pdf_path).resolve()
    if not html_path.is_file():
        raise FileNotFoundError(f"Assembled HTML not found: {html_path}")
    browser_path = browser_path or find_chromium()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    temp_pdf = pdf_path.with_name(f".{pdf_path.name}.tmp")
    temp_pdf.unlink(missing_ok=True)

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed; reinstall/update Books Studio.") from exc

    expected_pages = 0
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=str(browser_path),
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--allow-file-access-from-files",
                ],
            )
            try:
                page = await browser.new_page(viewport={"width": 794, "height": 1123})
                page.set_default_timeout(timeout_ms)
                await page.emulate_media(media="print")
                await page.goto(html_path.as_uri(), wait_until="load", timeout=timeout_ms)
                await page.add_style_tag(content=_PRINT_SAFETY_CSS)
                await page.evaluate(
                    """async () => {
                      if (document.fonts && document.fonts.ready) await document.fonts.ready;
                      await Promise.all(Array.from(document.images).map((image) => {
                        if (image.complete) return Promise.resolve();
                        return new Promise((resolve) => {
                          image.addEventListener('load', resolve, {once: true});
                          image.addEventListener('error', resolve, {once: true});
                        });
                      }));
                    }"""
                )
                broken_images = await page.eval_on_selector_all(
                    "img",
                    "images => images.filter(image => !image.complete || image.naturalWidth === 0)"
                    ".map(image => image.currentSrc || image.src)",
                )
                if broken_images:
                    raise RuntimeError(f"Cannot export PDF with broken images: {broken_images[:10]}")
                expected_pages = await page.locator(".book-sheet").count()
                if expected_pages == 0:
                    expected_pages = await page.locator(".book-page.book-page--sheet").count()
                if expected_pages == 0:
                    raise RuntimeError("Assembled HTML contains no printable book sheets")
                await page.pdf(
                    path=str(temp_pdf),
                    format="A4",
                    print_background=True,
                    display_header_footer=False,
                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                    prefer_css_page_size=True,
                )
            finally:
                await browser.close()

        result = _validate_pdf(temp_pdf, expected_pages=expected_pages)
        temp_pdf.replace(pdf_path)
        result["path"] = str(pdf_path)
        result["bytes"] = pdf_path.stat().st_size
        return result
    except Exception:
        temp_pdf.unlink(missing_ok=True)
        raise
