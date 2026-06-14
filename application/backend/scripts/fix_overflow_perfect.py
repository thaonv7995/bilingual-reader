#!/usr/bin/env python3
import sys
import json
import asyncio
import pathlib
import re
import argparse

BOOK_DIR = pathlib.Path("/Users/thaonv/Desktop/Books HTML/books/english-idioms-in-use-advanced/output")
A4_HEIGHT_PX = 1123
TARGET_CONTENT_HEIGHT = 1040  # 1123px - 83px bottom clearance (22mm)

def has_index_layout(html: str) -> bool:
    return 'index-columns' in html or 'index-entry' in html or 'index-col' in html

def get_index_override(level: int) -> str:
    if level == 0:
        return """
/* === SMART FIX v3 (Level 0: Index Default) === */
.index-columns {
  grid-template-columns: 1fr 1fr 1fr !important;
  gap: 0 6mm !important;
}
.prose-page {
  padding-top: 10mm !important;
  padding-bottom: 12mm !important;
}
"""
    elif level == 1:
        return """
/* === SMART FIX v3 (Level 1: Index Mild) === */
.index-columns {
  grid-template-columns: 1fr 1fr 1fr !important;
  gap: 0 5mm !important;
}
.index-entry {
  font-size: 8.2pt !important;
  line-height: 1.25 !important;
  margin-bottom: 0.8mm !important;
}
.index-entry strong {
  font-size: 9.0pt !important;
}
.index-title {
  font-size: 18pt !important;
  margin-bottom: 1.5mm !important;
}
.index-intro {
  font-size: 8.5pt !important;
  margin-bottom: 3mm !important;
}
.prose-page {
  padding-top: 8mm !important;
  padding-bottom: 12mm !important;
}
"""
    elif level == 2:
        return """
/* === SMART FIX v3 (Level 2: Index Moderate) === */
.index-columns {
  grid-template-columns: 1fr 1fr 1fr !important;
  gap: 0 4mm !important;
}
.index-entry {
  font-size: 7.8pt !important;
  line-height: 1.2 !important;
  margin-bottom: 0.6mm !important;
}
.index-entry strong {
  font-size: 8.5pt !important;
}
.index-title {
  font-size: 16pt !important;
  margin-bottom: 1.2mm !important;
}
.index-intro {
  font-size: 8.0pt !important;
  margin-bottom: 2.5mm !important;
}
.prose-page {
  padding-top: 6mm !important;
  padding-bottom: 12mm !important;
}
"""
    elif level == 3:
        return """
/* === SMART FIX v3 (Level 3: Index Dense) === */
.index-columns {
  grid-template-columns: 1fr 1fr 1fr !important;
  gap: 0 3mm !important;
}
.index-entry {
  font-size: 7.4pt !important;
  line-height: 1.15 !important;
  margin-bottom: 0.4mm !important;
}
.index-entry strong {
  font-size: 8.0pt !important;
}
.index-title {
  font-size: 14pt !important;
  margin-bottom: 1mm !important;
}
.index-intro {
  font-size: 7.5pt !important;
  margin-bottom: 2mm !important;
}
.prose-page {
  padding-top: 5mm !important;
  padding-bottom: 12mm !important;
}
"""
    return ""

def get_dense_override(level: int) -> str:
    if level == 0:
        return ""
    elif level == 1:
        return """
/* === SMART FIX v3 (Level 1: Mild) === */
.prose-page {
  font-size: 10.2pt !important;
  line-height: 1.32 !important;
  padding-top: 10mm !important;
  padding-bottom: 16mm !important;
}
.prose-page p, .prose-page li {
  font-size: 10.2pt !important;
  line-height: 1.32 !important;
  margin-bottom: 2.5mm !important;
}
.exercise-item, .matching-item, .dialogue-row, .definition-item, .idioms-table td, .idioms-table th {
  font-size: 8.8pt !important;
  line-height: 1.28 !important;
}
.exercise-instruction, .idiom-def, .entry-text {
  font-size: 8.8pt !important;
  line-height: 1.28 !important;
}
.exercise-block, .idiom-block, .definition-block, .example-block {
  margin-bottom: 3.5mm !important;
}
.prose-page h2.section-title {
  font-size: 11pt !important;
  margin-bottom: 2mm !important;
}
.unit-header {
  margin-bottom: 4mm !important;
}
.idioms-table th, .idioms-table td {
  padding: 1.5mm 2.5mm !important;
}
.dialogue-box {
  padding: 2.5mm 3.5mm !important;
  margin-bottom: 3mm !important;
}
"""
    elif level == 2:
        return """
/* === SMART FIX v3 (Level 2: Moderate) === */
.prose-page {
  font-size: 9.5pt !important;
  line-height: 1.25 !important;
  padding-top: 8mm !important;
  padding-bottom: 12mm !important;
}
.prose-page p, .prose-page li {
  font-size: 9.5pt !important;
  line-height: 1.25 !important;
  margin-bottom: 2mm !important;
}
.exercise-item, .matching-item, .dialogue-row, .definition-item, .idioms-table td, .idioms-table th {
  font-size: 8.2pt !important;
  line-height: 1.22 !important;
}
.exercise-instruction, .idiom-def, .entry-text {
  font-size: 8.2pt !important;
  line-height: 1.22 !important;
}
.exercise-block, .idiom-block, .definition-block, .example-block {
  margin-bottom: 2.8mm !important;
}
.prose-page h2.section-title {
  font-size: 10pt !important;
  margin-bottom: 1.5mm !important;
}
.unit-header {
  margin-bottom: 3mm !important;
}
.idioms-table th, .idioms-table td {
  padding: 1.2mm 2mm !important;
}
.dialogue-box {
  padding: 2mm 3mm !important;
  margin-bottom: 2.5mm !important;
}
"""
    elif level == 3:
        return """
/* === SMART FIX v3 (Level 3: Dense) === */
.prose-page {
  font-size: 9.0pt !important;
  line-height: 1.2 !important;
  padding-top: 6mm !important;
  padding-bottom: 10mm !important;
}
.prose-page p, .prose-page li {
  font-size: 9.0pt !important;
  line-height: 1.2 !important;
  margin-bottom: 1.5mm !important;
}
.exercise-item, .matching-item, .dialogue-row, .definition-item, .idioms-table td, .idioms-table th {
  font-size: 7.8pt !important;
  line-height: 1.18 !important;
}
.exercise-instruction, .idiom-def, .entry-text {
  font-size: 7.8pt !important;
  line-height: 1.18 !important;
}
.exercise-block, .idiom-block, .definition-block, .example-block {
  margin-bottom: 2.2mm !important;
}
.prose-page h2.section-title {
  font-size: 9.5pt !important;
  margin-bottom: 1.2mm !important;
}
.unit-header {
  margin-bottom: 2.5mm !important;
}
.idioms-table th, .idioms-table td {
  padding: 1mm 1.5mm !important;
}
.dialogue-box {
  padding: 1.5mm 2.2mm !important;
  margin-bottom: 2mm !important;
}
"""
    return ""

def get_scale_override(scale: float) -> str:
    return f"""
/* === SCALE FIX (scale={scale:.4f}) === */
.book-page--sheet {{
  overflow: hidden !important;
}}
.sheet-flow {{
  transform: scale({scale:.4f}) !important;
  transform-origin: top center !important;
  height: {round(1123 / scale, 1)}px !important;
  min-height: {round(1123 / scale, 1)}px !important;
  margin-top: 0px !important;
  overflow: visible !important;
  width: 100% !important;
  padding-bottom: {round(50 / scale, 1)}px !important;
}}
.book-footer {{
  position: absolute !important;
  bottom: {round(10 / scale, 2)}mm !important;
  left: var(--book-margin-x) !important;
  right: var(--book-margin-x) !important;
}}
"""

def clean_html(html: str) -> str:
    # Find style tag boundaries
    style_start = html.find('<style>')
    style_end = html.find('</style>')
    if style_start == -1 or style_end == -1:
        return html
        
    style_content = html[style_start:style_end]
    
    # Injected styles are not indented (start at column 0, i.e., right after a newline)
    patterns = [
        r'\n/\* ===',
        r'\n\.prose-page\s*\{',
        r'\n\.book-page--sheet\s*\{',
        r'\n\.sheet-flow\s*\{',
        r'\n\.book-footer\s*\{'
    ]
    
    first_idx = len(style_content)
    for p in patterns:
        m = re.search(p, style_content)
        if m:
            first_idx = min(first_idx, m.start())
            
    if first_idx < len(style_content):
        # Truncate injected overrides and leave original clean styles
        cleaned_style = style_content[:first_idx].rstrip() + '\n  '
        return html[:style_start] + cleaned_style + html[style_end:]
        
    return html

async def measure_page_height(page, html_path: pathlib.Path) -> int:
    await page.goto(f"file://{html_path.resolve()}", wait_until="domcontentloaded")
    
    # Measure content natural height
    h = await page.evaluate("""() => {
        const sheet = document.querySelector('.book-page--sheet');
        const flow = document.querySelector('.sheet-flow');
        if (!sheet || !flow) return -1;
        
        const origSheetStyle = sheet.style.cssText;
        const origFlowStyle = flow.style.cssText;
        
        sheet.style.setProperty('height', 'auto', 'important');
        sheet.style.setProperty('max-height', 'none', 'important');
        sheet.style.setProperty('overflow', 'visible', 'important');
        
        flow.style.setProperty('height', 'auto', 'important');
        flow.style.setProperty('min-height', 'unset', 'important');
        flow.style.setProperty('max-height', 'none', 'important');
        flow.style.setProperty('overflow', 'visible', 'important');
        flow.style.setProperty('padding-bottom', '0px', 'important');
        
        const h = flow.scrollHeight;
        
        sheet.style.cssText = origSheetStyle;
        flow.style.cssText = origFlowStyle;
        
        return h;
    }""")
    return h

async def check_real_overflow(page, html_path: pathlib.Path) -> float:
    """Check how much the page overflows in its current style configuration."""
    await page.goto(f"file://{html_path.resolve()}", wait_until="domcontentloaded")
    overflow = await page.evaluate("""() => {
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
    return overflow

async def process_single_page(browser, html_path: pathlib.Path, is_dry_run=False):
    num = int(html_path.stem.split("_")[1])
    lang = html_path.parent.name
    
    original_html = html_path.read_text(encoding='utf-8')
    cleaned = clean_html(original_html)
    
    # Write to a temp file to measure
    tmp_path = html_path.parent / f"_tmp_opt_{html_path.name}"
    tmp_path.write_text(cleaned, encoding='utf-8')
    
    # Use a fresh context and page for each task to run in parallel safely
    context = await browser.new_context(viewport={"width": 794, "height": A4_HEIGHT_PX})
    page = await context.new_page()
    
    try:
        is_index = has_index_layout(cleaned)
        
        best_level = 0
        best_height = -1
        best_html = cleaned
        
        if is_index:
            # For index pages, Level 0 is the default 3-column layout
            # Test levels 0, 1, 2, 3
            for level in [0, 1, 2, 3]:
                override_css = get_index_override(level)
                test_html = cleaned.replace('</style>', override_css + '\n  </style>', 1)
                tmp_path.write_text(test_html, encoding='utf-8')
                
                h_level = await measure_page_height(page, tmp_path)
                if best_height == -1 or h_level < best_height:
                    best_height = h_level
                    best_level = level
                    best_html = test_html
                    
                if best_height <= TARGET_CONTENT_HEIGHT:
                    break
        else:
            # Measure baseline height first for lesson pages
            h_baseline = await measure_page_height(page, tmp_path)
            if h_baseline <= 0:
                print(f"  [{lang}/page_{num:04d}] Skipped: no sheet-flow element found.")
                return None
            best_height = h_baseline
            
            # Test levels 1, 2, 3
            for level in [1, 2, 3]:
                if best_height <= TARGET_CONTENT_HEIGHT:
                    break
                    
                override_css = get_dense_override(level)
                test_html = cleaned.replace('</style>', override_css + '\n  </style>', 1)
                tmp_path.write_text(test_html, encoding='utf-8')
                
                h_level = await measure_page_height(page, tmp_path)
                if h_level < best_height:
                    best_height = h_level
                    best_level = level
                    best_html = test_html
                    
        # Apply scale factor on top of the best HTML if it still doesn't fit
        scale = 1.0
        final_html = best_html
        
        if best_height > TARGET_CONTENT_HEIGHT:
            scale = TARGET_CONTENT_HEIGHT / best_height
            scale = max(0.64, min(0.98, scale))
            scale_css = get_scale_override(scale)
            final_html = best_html.replace('</style>', scale_css + '\n  </style>', 1)
            
        # Write final HTML to verify real overflow
        tmp_path.write_text(final_html, encoding='utf-8')
        real_overflow = await check_real_overflow(page, tmp_path)
        
        if not is_dry_run:
            html_path.write_text(final_html, encoding='utf-8')
            
        page_type = "index" if is_index else "lesson"
        print(f"  [{lang}/page_{num:04d}] ({page_type}) best_h={best_height}px (Level {best_level}) → Scale={scale:.4f} → RealOverflow={real_overflow}px", flush=True)
        
        return {
            "page": num,
            "lang": lang,
            "page_type": page_type,
            "best_level": best_level,
            "best_height": best_height,
            "scale": scale,
            "real_overflow": real_overflow
        }
    finally:
        await context.close()
        if tmp_path.exists():
            tmp_path.unlink()

async def worker(sem, browser, html_path, results, is_dry_run):
    async with sem:
        try:
            res = await process_single_page(browser, html_path, is_dry_run)
            if res:
                results.append(res)
        except Exception as e:
            print(f"Error processing {html_path.name}: {e}", file=sys.stderr, flush=True)

async def main():
    parser = argparse.ArgumentParser(description="Hybrid layout and font size scaler to fix overflow issues.")
    parser.add_argument("lang", nargs="?", default="all", help="Language: 'en', 'vi', or 'all'")
    parser.add_argument("page", nargs="?", type=int, default=None, help="Specific page number to run")
    parser.add_argument("--concurrency", type=int, default=8, help="Number of parallel workers")
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes to disk")
    args = parser.parse_args()
    
    from playwright.async_api import async_playwright
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        
        langs = ["en", "vi"] if args.lang == "all" else [args.lang]
        sem = asyncio.Semaphore(args.concurrency)
        
        for lang in langs:
            print(f"\nProcessing {lang.upper()} pages in parallel (concurrency={args.concurrency})...", flush=True)
            lang_dir = BOOK_DIR / lang
            if args.page:
                pages = [lang_dir / f"page_{args.page:04d}.html"]
            else:
                pages = sorted(lang_dir.glob("page_*.html"))
                
            results = []
            tasks = [worker(sem, browser, p, results, args.dry_run) for p in pages if p.exists()]
            
            await asyncio.gather(*tasks)
            
            # Write results report
            report_file = pathlib.Path(f"/tmp/perfect_fix_{lang}_report.json")
            report_file.write_text(json.dumps(results, indent=2))
            print(f"Finished {lang.upper()}. Report saved to {report_file}", flush=True)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
