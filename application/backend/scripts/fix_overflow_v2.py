#!/usr/bin/env python3
"""
Smart overflow fixer v2:
- Index pages (162+): convert to 3-column grid
- Lesson pages: target-specific CSS reduction
- Runs iteratively with browser verification
"""
import sys, json, asyncio, pathlib, re, bs4

BOOK_DIR = pathlib.Path("/Users/thaonv/Desktop/Books HTML/books/english-idioms-in-use-advanced/output")
A4_HEIGHT_PX = 1123
TOLERANCE_PX = 5

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


def has_index_layout(html: str) -> bool:
    return 'index-columns' in html or 'index-entry' in html or 'index-col' in html


def fix_index_page(html: str, overflow_px: int) -> str:
    """Switch index from 2-column to 3-column and reduce font sizes."""
    # Remove old fix
    html = re.sub(r'/\* === SMART FIX v2.*?=== \*/', '', html, flags=re.DOTALL)
    
    # Scale factor for font/margin
    scale = max(0.72, 1.0 - overflow_px / (A4_HEIGHT_PX * 3))
    font_size = round(8.2 * scale, 2)
    line_height = round(1.22 * scale, 3)
    margin = round(0.8 * scale, 2)
    padding_top = round(10 * scale, 1)
    
    fix = f"""
/* === SMART FIX v2 (index, scale={scale:.3f}) === */
.prose-page {{
  padding-top: {padding_top}mm !important;
  padding-bottom: 12mm !important;
}}
.index-columns {{
  grid-template-columns: 1fr 1fr 1fr !important;
  gap: 0 5mm !important;
}}
.index-entry {{
  font-size: {font_size}pt !important;
  line-height: {line_height} !important;
  margin-bottom: {margin}mm !important;
}}
.index-entry strong {{
  font-size: {round(font_size + 0.5, 2)}pt !important;
}}
.index-title {{
  font-size: 18pt !important;
  margin-bottom: 1.5mm !important;
}}
.index-intro {{
  font-size: 8.5pt !important;
  margin-bottom: 3mm !important;
}}
"""
    return html.replace('</style>', fix + '\n  </style>', 1)


def fix_lesson_page(html: str, overflow_px: int) -> str:
    """Reduce spacing and font sizes for lesson/exercise pages."""
    # Remove old fix
    html = re.sub(r'/\* === SMART FIX v2.*?=== \*/', '', html, flags=re.DOTALL)
    
    available = A4_HEIGHT_PX
    scale = max(0.78, available / (available + overflow_px * 1.4))
    
    font_size = round(9.8 * scale, 2)
    line_height = round(1.32 * scale, 3)
    line_height = max(1.15, line_height)
    p_margin = round(2.0 * scale, 2)
    block_margin = round(3.0 * scale, 2)
    section_margin = round(4.0 * scale, 2)
    
    fix = f"""
/* === SMART FIX v2 (lesson, scale={scale:.3f}) === */
.prose-page {{
  padding-top: {round(8 * scale, 1)}mm !important;
  padding-bottom: {round(10 * scale, 1)}mm !important;
  font-size: {font_size}pt !important;
  line-height: {line_height} !important;
}}
.prose-page p,
.prose-page li {{
  font-size: {font_size}pt !important;
  line-height: {line_height} !important;
  margin-bottom: {p_margin}mm !important;
}}
.exercise-block,
.idiom-block,
.definition-block,
.example-block {{
  margin-bottom: {block_margin}mm !important;
}}
.exercise-instruction,
.idiom-def,
.entry-text {{
  font-size: {font_size}pt !important;
  line-height: {line_height} !important;
}}
.section-header,
.unit-header {{
  margin-bottom: {section_margin}mm !important;
}}
.exercises-title {{
  font-size: {round(17 * scale, 1)}pt !important;
  margin-bottom: {round(3 * scale, 1)}mm !important;
}}
.two-col-layout, .exercise-columns {{
  gap: {round(4 * scale, 1)}mm !important;
}}
"""
    return html.replace('</style>', fix + '\n  </style>', 1)


def redistribute_index_columns(html: str) -> str:
    """When switching from 2 to 3 columns, redistribute entries evenly."""
    soup = bs4.BeautifulSoup(html, 'html.parser')
    col_container = soup.find(class_='index-columns')
    if not col_container:
        return html
    
    # Collect all entries from existing columns
    all_entries = []
    for col in col_container.find_all(class_='index-col'):
        all_entries.extend(col.find_all(class_='index-entry'))
    
    if len(all_entries) < 6:
        return html
    
    # Split into 3 equal groups
    n = len(all_entries)
    per_col = (n + 2) // 3
    
    # Clear existing columns and rebuild with 3
    col_container.clear()
    
    for c in range(3):
        new_col = soup.new_tag('div', attrs={'class': 'index-col', 'id': f'col-{c+1}'})
        start = c * per_col
        end = min(start + per_col, n)
        for entry in all_entries[start:end]:
            new_col.append(entry.__copy__())
        col_container.append(new_col)
    
    return str(soup)


async def fix_overflow(lang: str):
    overflow_json = pathlib.Path(f"/tmp/overflow_{lang}.json")
    remaining_json = pathlib.Path(f"/tmp/overflow_{lang}_remaining.json")
    
    # Use remaining from previous run if exists
    source = remaining_json if remaining_json.exists() else overflow_json
    if not source.exists():
        print(f"No overflow data found. Run check_overflow.py first.")
        return
    
    overflow_pages = json.loads(source.read_text())
    print(f"Fixing {len(overflow_pages)} overflowing {lang.upper()} pages using smart fixer v2...")
    
    from playwright.async_api import async_playwright
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context(viewport={"width": 794, "height": A4_HEIGHT_PX})
        page = await context.new_page()
        
        fixed_count = 0
        still_overflowing = []
        
        for item in overflow_pages:
            html_path = pathlib.Path(item['path'])
            if not html_path.exists():
                continue
            
            initial_overflow = item['overflowPx']
            page_num = item['page']
            original_html = html_path.read_text(encoding='utf-8')
            
            is_index = has_index_layout(original_html)
            print(f"\n  [{lang}/page_{page_num:04d}] {'(index)' if is_index else '(lesson)'} overflow={initial_overflow}px", flush=True)
            
            best_overflow = initial_overflow
            best_html = None
            
            for attempt in range(5):
                current_overflow = best_overflow if best_html else initial_overflow
                
                if is_index:
                    new_html = fix_index_page(original_html, current_overflow)
                    if attempt == 0:
                        # First attempt: also redistribute entries into 3 columns
                        try:
                            new_html = redistribute_index_columns(new_html)
                        except Exception as e:
                            print(f"    redistribute failed: {e}", flush=True)
                else:
                    new_html = fix_lesson_page(original_html, current_overflow)
                
                tmp = html_path.parent / f"_tmp_{html_path.name}"
                tmp.write_text(new_html, encoding='utf-8')
                new_overflow = await measure_overflow(page, tmp)
                tmp.unlink()
                
                print(f"    attempt {attempt+1}: overflow={new_overflow}px", flush=True)
                
                if new_overflow < best_overflow:
                    best_overflow = new_overflow
                    best_html = new_html
                
                if new_overflow <= TOLERANCE_PX:
                    break
            
            if best_html and best_overflow < initial_overflow:
                html_path.write_text(best_html, encoding='utf-8')
                if best_overflow <= TOLERANCE_PX:
                    fixed_count += 1
                    print(f"    ✓ FIXED", flush=True)
                else:
                    print(f"    ~ REDUCED {initial_overflow}→{best_overflow}px", flush=True)
                    still_overflowing.append({**item, 'overflowPx': best_overflow})
            else:
                print(f"    ✗ No improvement", flush=True)
                still_overflowing.append(item)
        
        await browser.close()
    
    print(f"\n{'='*55}")
    print(f"{lang.upper()}: Fully fixed {fixed_count}/{len(overflow_pages)} pages")
    if still_overflowing:
        print(f"  Still overflowing ({len(still_overflowing)}): {[p['page'] for p in still_overflowing]}")
    
    remaining_json.write_text(json.dumps(still_overflowing, indent=2))


if __name__ == "__main__":
    import subprocess, sys
    # Check bs4
    try:
        import bs4
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'beautifulsoup4'], check=True)
    
    lang = sys.argv[1] if len(sys.argv) > 1 else "en"
    asyncio.run(fix_overflow(lang))
