#!/usr/bin/env python3
"""
Scale transform fixer: uses CSS transform: scale() on the article element
to shrink heavily overflowing pages that can't be fixed with font adjustments.
This preserves layout structure while fitting everything on the A4 sheet.
"""
import sys, json, asyncio, pathlib, re

BOOK_DIR = pathlib.Path("/Users/thaonv/Desktop/Books HTML/books/english-idioms-in-use-advanced/output")
A4_HEIGHT_PX = 1123
TOLERANCE_PX = 8

async def measure_overflow(page, html_path):
    await page.goto(f"file://{html_path}", wait_until="domcontentloaded")
    return await page.evaluate("""() => {
        const sheet = document.querySelector('.book-page--sheet');
        if (!sheet) return -1;
        const sheetRect = sheet.getBoundingClientRect();
        let maxBottom = sheetRect.top;
        for (const el of sheet.querySelectorAll('*')) {
            if (el.classList.contains('page-nav')) continue;
            if (window.getComputedStyle(el).position === 'fixed') continue;
            const r = el.getBoundingClientRect();
            if (r.bottom > maxBottom && r.width > 0 && r.height > 0) maxBottom = r.bottom;
        }
        return Math.round(maxBottom - sheetRect.bottom);
    }""")


async def measure_content_natural_height(page, html_path):
    """Measure full content height without overflow:hidden clipping."""
    await page.goto(f"file://{html_path}", wait_until="domcontentloaded")
    return await page.evaluate("""() => {
        const sheet = document.querySelector('.book-page--sheet');
        const article = sheet ? sheet.querySelector('article, .sheet-flow') : null;
        if (!article) return 1123;
        // Temporarily remove height constraint
        const origStyle = sheet.style.cssText;
        sheet.style.height = 'auto';
        sheet.style.maxHeight = 'none';
        sheet.style.overflow = 'visible';
        const h = sheet.scrollHeight;
        sheet.style.cssText = origStyle;
        return h;
    }""")


def apply_scale_fix(html: str, scale: float, natural_height: int) -> str:
    """Apply CSS transform: scale() to shrink the article to fit."""
    # Remove old scale fixes
    html = re.sub(r'/\* === SCALE FIX.*?=== \*/', '', html, flags=re.DOTALL)
    # Remove old v1/v2 fixes that might conflict
    html = re.sub(r'/\* === AUTO OVERFLOW FIX.*?=== \*/', '', html, flags=re.DOTALL)
    html = re.sub(r'/\* === SMART FIX v2.*?=== \*/', '', html, flags=re.DOTALL)

    # The scale transform shrinks but the DOM element still takes original space
    # We need to also adjust the container dimensions
    # Strategy: scale the article, then compensate with negative margin
    compensation = round((1 - scale) * natural_height / 2, 1)
    
    fix = f"""
/* === SCALE FIX (scale={scale:.4f}) === */
.book-page--sheet {{
  overflow: hidden !important;
}}
.sheet-flow {{
  transform: scale({scale:.4f});
  transform-origin: top center;
  /* Compensate for scale reducing effective height */
  margin-top: -{compensation}px;
  height: {round(natural_height * scale)}px;
  overflow: visible;
  width: 100%;
  min-height: unset !important;
}}
"""
    return html.replace('</style>', fix + '\n  </style>', 1)


async def fix_with_scale(lang: str):
    remaining_json = pathlib.Path(f"/tmp/overflow_{lang}_remaining.json")
    if not remaining_json.exists():
        # Fall back to original overflow scan
        remaining_json = pathlib.Path(f"/tmp/overflow_{lang}.json")
    
    if not remaining_json.exists():
        print(f"No overflow data. Run check_overflow.py first.")
        return
    
    overflow_pages = json.loads(remaining_json.read_text())
    print(f"Scale-fixing {len(overflow_pages)} remaining overflowing {lang.upper()} pages...")
    
    from playwright.async_api import async_playwright
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context(viewport={"width": 794, "height": A4_HEIGHT_PX})
        page_obj = await context.new_page()
        
        fixed = 0
        still_bad = []
        
        for item in overflow_pages:
            html_path = pathlib.Path(item['path'])
            if not html_path.exists():
                continue
            
            overflow_px = item['overflowPx']
            page_num = item['page']
            print(f"\n  [{lang}/page_{page_num:04d}] overflow={overflow_px}px → computing scale...", flush=True)
            
            # Measure natural content height with overflow:hidden removed
            natural_h = await measure_content_natural_height(page_obj, html_path)
            if natural_h <= 0:
                natural_h = A4_HEIGHT_PX + overflow_px
            
            # Target: content fits in A4 height
            # scale = A4_HEIGHT / natural_h (with small buffer)
            target_scale = (A4_HEIGHT_PX - TOLERANCE_PX) / natural_h
            target_scale = max(0.60, min(0.98, target_scale))
            
            print(f"    natural_h={natural_h}px, scale={target_scale:.4f}", flush=True)
            
            original_html = html_path.read_text(encoding='utf-8')
            new_html = apply_scale_fix(original_html, target_scale, natural_h)
            
            tmp = html_path.parent / f"_tmp_{html_path.name}"
            tmp.write_text(new_html, encoding='utf-8')
            new_overflow = await measure_overflow(page_obj, tmp)
            tmp.unlink()
            
            print(f"    result: overflow={new_overflow}px", flush=True)
            
            if new_overflow <= TOLERANCE_PX:
                html_path.write_text(new_html, encoding='utf-8')
                fixed += 1
                print(f"    ✓ FIXED", flush=True)
            else:
                # Try a slightly more aggressive scale
                target_scale2 = target_scale * (A4_HEIGHT_PX / (A4_HEIGHT_PX + new_overflow))
                target_scale2 = max(0.60, target_scale2)
                new_html2 = apply_scale_fix(original_html, target_scale2, natural_h)
                tmp.write_text(new_html2, encoding='utf-8')
                new_overflow2 = await measure_overflow(page_obj, tmp)
                tmp.unlink()
                
                print(f"    retry scale={target_scale2:.4f} → overflow={new_overflow2}px", flush=True)
                
                if new_overflow2 <= TOLERANCE_PX:
                    html_path.write_text(new_html2, encoding='utf-8')
                    fixed += 1
                    print(f"    ✓ FIXED", flush=True)
                elif new_overflow2 < overflow_px:
                    html_path.write_text(new_html2, encoding='utf-8')
                    print(f"    ~ REDUCED {overflow_px}→{new_overflow2}px", flush=True)
                    still_bad.append({**item, 'overflowPx': new_overflow2})
                else:
                    print(f"    ✗ No improvement", flush=True)
                    still_bad.append(item)
        
        await browser.close()
    
    print(f"\n{'='*55}")
    print(f"{lang.upper()}: Scale-fixed {fixed}/{len(overflow_pages)} pages")
    if still_bad:
        print(f"  Still overflowing ({len(still_bad)}): {[p['page'] for p in still_bad]}")
    
    pathlib.Path(f"/tmp/overflow_{lang}_remaining.json").write_text(json.dumps(still_bad, indent=2))


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "en"
    asyncio.run(fix_with_scale(lang))
