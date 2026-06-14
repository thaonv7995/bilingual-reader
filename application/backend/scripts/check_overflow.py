#!/usr/bin/env python3
"""
Accurate overflow detector: measures the actual bottom edge of content
within .book-page--sheet vs the sheet height (297mm = 1123px at 96dpi).
Uses getBoundingClientRect on the last child element.
"""
import sys, json, asyncio, pathlib

BOOK_DIR = pathlib.Path("/Users/thaonv/Desktop/Books HTML/books/english-idioms-in-use-advanced/output")
# A4 at 96dpi: 297mm = 1123px
A4_HEIGHT_PX = 1123

async def detect_overflow(lang: str):
    from playwright.async_api import async_playwright
    lang_dir = BOOK_DIR / lang
    pages = sorted(lang_dir.glob("page_*.html"))
    overflowing = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context(viewport={"width": 794, "height": A4_HEIGHT_PX})
        page = await context.new_page()

        for html_path in pages:
            num = int(html_path.stem.split("_")[1])
            await page.goto(f"file://{html_path}", wait_until="domcontentloaded")
            
            # Measure the bottom edge of all content inside .book-page--sheet
            result = await page.evaluate(f"""() => {{
                const sheet = document.querySelector('.book-page--sheet');
                if (!sheet) return {{ overflow: -1, maxBottom: -1, sheetBottom: -1 }};
                
                const sheetRect = sheet.getBoundingClientRect();
                const sheetBottom = sheetRect.bottom;
                
                // Check all descendants for their bottom edges
                const allEls = sheet.querySelectorAll('*');
                let maxBottom = sheetRect.top;
                
                for (const el of allEls) {{
                    // Skip nav and positioned overlays
                    if (el.classList.contains('page-nav')) continue;
                    const style = window.getComputedStyle(el);
                    if (style.position === 'fixed') continue;
                    
                    const rect = el.getBoundingClientRect();
                    if (rect.bottom > maxBottom && rect.width > 0 && rect.height > 0) {{
                        maxBottom = rect.bottom;
                    }}
                }}
                
                const overflow = Math.round(maxBottom - sheetBottom);
                return {{ overflow, maxBottom: Math.round(maxBottom), sheetBottom: Math.round(sheetBottom) }};
            }}""")
            
            overflow = result.get("overflow", -1)
            
            if overflow > 5:  # 5px tolerance
                overflowing.append({
                    "page": num,
                    "lang": lang,
                    "overflowPx": overflow,
                    "maxBottom": result.get("maxBottom"),
                    "sheetBottom": result.get("sheetBottom"),
                    "path": str(html_path)
                })
                print(f"  [OVERFLOW] {lang}/page_{num:04d}: +{overflow}px  (content bottom={result.get('maxBottom')}, sheet bottom={result.get('sheetBottom')})", flush=True)
            elif overflow < -50:
                print(f"  [UNDERFLOW] {lang}/page_{num:04d}: {overflow}px", flush=True)
            else:
                print(f"  [OK]       {lang}/page_{num:04d}", flush=True)

        await browser.close()

    out = pathlib.Path(f"/tmp/overflow_{lang}.json")
    out.write_text(json.dumps(overflowing, indent=2))
    print(f"\n{'='*55}")
    print(f"Found {len(overflowing)} overflowing {lang.upper()} pages → {out}")
    return overflowing


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "en"
    asyncio.run(detect_overflow(lang))
