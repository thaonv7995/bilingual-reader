#!/usr/bin/env python3
"""
Auto-fix overflow in pages by progressively reducing font sizes and spacing.
For each overflowing page:
  1. Detects overflow amount
  2. Calculates a scale factor
  3. Injects a CSS override into the page's <style> block
  4. Re-checks and iterates until fit or gives up
"""
import sys, json, asyncio, pathlib, re

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from books_core.source_profile import load_source_profile

BOOK_DIR = pathlib.Path("/Users/thaonv/Desktop/Books HTML/books/english-idioms-in-use-advanced/output")
A4_HEIGHT_PX = 1123
TOLERANCE_PX = 5

OVERFLOW_JSON_EN = pathlib.Path("/tmp/overflow_en.json")
OVERFLOW_JSON_VI = pathlib.Path("/tmp/overflow_vi.json")

# CSS to inject to reduce content size - targeting common prose and index elements
FIX_CSS_TEMPLATE = """
/* === AUTO OVERFLOW FIX (scale={scale:.3f}) === */
.prose-page {{
  padding-top: {padding_top}mm !important;
  padding-bottom: {padding_bottom}mm !important;
  font-size: {font_size}pt !important;
  line-height: {line_height} !important;
}}
.prose-page p,
.prose-page li,
.prose-page .index-entry,
.exercise-instruction,
.exercise-block {{
  font-size: {font_size}pt !important;
  line-height: {line_height} !important;
  margin-bottom: {p_margin}mm !important;
}}
.prose-page h1, .exercises-title, .index-title {{
  font-size: {h1_size}pt !important;
  margin-bottom: {h1_margin}mm !important;
}}
.prose-page h2, .section-subtitle {{
  font-size: {h2_size}pt !important;
  margin-bottom: {h2_margin}mm !important;
}}
.exercise-block {{
  margin-bottom: {block_margin}mm !important;
}}
"""

def compute_fix_params(overflow_px: int, base_font: float = 10.5):
    """Compute CSS parameters to reduce page content height by overflow_px."""
    # A4 usable height in px: ~1123px (297mm at 96dpi)
    # We need to reduce total content by overflow_px
    # Scale = available / (available + overflow)
    available = A4_HEIGHT_PX - TOLERANCE_PX
    scale = available / (available + overflow_px)
    # Never use the old 0.72 fallback: it makes dense pages unreadably small.
    scale = max(0.92, min(0.96, scale))
    
    font_size = round(base_font * scale, 2)
    line_height = round(1.35 * scale + (1 - scale) * 1.1, 3)
    line_height = max(1.1, min(1.45, line_height))
    p_margin = round(2.5 * scale, 2)
    h1_size = round(18 * scale, 1)
    h1_margin = round(3 * scale, 2)
    h2_size = round(13 * scale, 1)
    h2_margin = round(2 * scale, 2)
    block_margin = round(3.5 * scale, 2)
    padding_top = round(10 * scale, 1)
    padding_bottom = round(12 * scale, 1)
    
    return dict(
        scale=scale, font_size=font_size, line_height=line_height,
        p_margin=p_margin, h1_size=h1_size, h1_margin=h1_margin,
        h2_size=h2_size, h2_margin=h2_margin, block_margin=block_margin,
        padding_top=padding_top, padding_bottom=padding_bottom
    )


def inject_fix_css(html_path: pathlib.Path, params: dict) -> str:
    """Inject fix CSS into the page's <style> block. Returns new HTML."""
    html = html_path.read_text(encoding='utf-8')
    fix_css = FIX_CSS_TEMPLATE.format(**params)
    
    # Remove any existing AUTO OVERFLOW FIX block
    html = re.sub(
        r'\n?\s*/\* === AUTO OVERFLOW FIX.*?=== \*/.*?(?=\n\s*(?:/\*|</style>))',
        '',
        html,
        flags=re.DOTALL
    )
    
    # Inject before </style>
    html = html.replace('</style>', fix_css + '\n  </style>', 1)
    return html


async def check_overflow_for_page(page, html_path: pathlib.Path) -> int:
    """Returns overflow in px for a given page (already loaded)."""
    result = await page.evaluate("""() => {
        const sheet = document.querySelector('.book-page--sheet');
        if (!sheet) return -1;
        const sheetRect = sheet.getBoundingClientRect();
        const sheetBottom = sheetRect.bottom;
        const allEls = sheet.querySelectorAll('*');
        let maxBottom = sheetRect.top;
        for (const el of allEls) {
            if (el.classList.contains('page-nav')) continue;
            const style = window.getComputedStyle(el);
            if (style.position === 'fixed') continue;
            const rect = el.getBoundingClientRect();
            if (rect.bottom > maxBottom && rect.width > 0 && rect.height > 0) {
                maxBottom = rect.bottom;
            }
        }
        return Math.round(maxBottom - sheetBottom);
    }""")
    return result


async def fix_overflow(lang: str):
    overflow_json = OVERFLOW_JSON_EN if lang == 'en' else OVERFLOW_JSON_VI
    if not overflow_json.exists():
        print(f"No overflow data found for {lang}. Run check_overflow.py first.")
        return
    
    overflow_pages = json.loads(overflow_json.read_text())
    print(f"Fixing {len(overflow_pages)} overflowing {lang.upper()} pages...")
    
    from playwright.async_api import async_playwright
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context(viewport={"width": 794, "height": A4_HEIGHT_PX})
        page = await context.new_page()
        
        fixed = 0
        still_overflowing = []
        
        for item in overflow_pages:
            html_path = pathlib.Path(item['path'])
            initial_overflow = item['overflowPx']
            page_num = item['page']
            profile = load_source_profile(html_path, page_num)
            policy = (profile or {}).get("fit_policy", {})
            density = (profile or {}).get("density", "unknown")
            
            print(f"\n  [{lang}/page_{page_num:04d}] overflow={initial_overflow}px", flush=True)

            # A tight source page must be repaired structurally (or split), not
            # globally scaled.  Preserve the issue for the page-level repair UI.
            if density in {"tight", "overfull-source"} or initial_overflow > 80:
                print(
                    f"    ! source-aware hold: density={density}, "
                    f"overflow={initial_overflow}px; skipping global scale",
                    flush=True,
                )
                still_overflowing.append({
                    **item,
                    "repair": "source-aware-local-or-split",
                    "source_density": density,
                    "min_body_font_pt": policy.get("min_body_font_pt", 11.0),
                })
                continue
            
            # Iterative fix - try up to 4 passes with increasing aggressiveness
            current_overflow = initial_overflow
            best_html = None
            best_overflow = initial_overflow
            
            for attempt in range(4):
                params = compute_fix_params(current_overflow)
                new_html = inject_fix_css(html_path, params)
                
                # Write temp, load in browser, check
                tmp_path = html_path.parent / f"_tmp_{html_path.name}"
                tmp_path.write_text(new_html, encoding='utf-8')
                
                await page.goto(f"file://{tmp_path}", wait_until="domcontentloaded")
                new_overflow = await check_overflow_for_page(page, html_path)
                
                tmp_path.unlink()
                
                print(f"    attempt {attempt+1}: scale={params['scale']:.3f} → overflow={new_overflow}px", flush=True)
                
                if new_overflow < best_overflow:
                    best_overflow = new_overflow
                    best_html = new_html
                
                if new_overflow <= TOLERANCE_PX:
                    break
                
                # Next pass: use the remaining overflow
                current_overflow = new_overflow
            
            if best_html is not None and best_overflow < initial_overflow:
                html_path.write_text(best_html, encoding='utf-8')
                if best_overflow <= TOLERANCE_PX:
                    print(f"    ✓ FIXED (final overflow={best_overflow}px)", flush=True)
                    fixed += 1
                else:
                    print(f"    ~ REDUCED {initial_overflow}→{best_overflow}px (still overflowing)", flush=True)
                    still_overflowing.append({**item, 'overflowPx': best_overflow})
            else:
                print(f"    ✗ Could not fix", flush=True)
                still_overflowing.append(item)
        
        await browser.close()
    
    print(f"\n{'='*55}")
    print(f"{lang.upper()}: Fixed {fixed}/{len(overflow_pages)} pages")
    if still_overflowing:
        print(f"  Still overflowing: {[p['page'] for p in still_overflowing]}")
    
    # Update overflow json with remaining issues
    updated = pathlib.Path(f"/tmp/overflow_{lang}_remaining.json")
    updated.write_text(json.dumps(still_overflowing, indent=2))
    return still_overflowing


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "en"
    asyncio.run(fix_overflow(lang))
