#!/usr/bin/env python3
"""Batch processor to render and translate books in parallel using agy CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Allow imports from backend
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from books_core.paths import BookPaths
from books_core.pipeline.process import process_page
from books_core.repo import repo_root


def get_agy_binary() -> str:
    # Check common locations or PATH
    for path in ["/Users/thaonv/.local/bin/agy", "agy"]:
        if shutil.which(path):
            return path
    raise FileNotFoundError("Could not find agy binary on PATH or common locations.")


def translate_page(book: BookPaths, page: int, agy_bin: str) -> dict:
    page_str = f"{page:04d}"
    en_html = book.page_lang_html(page, "en")
    vi_html = book.page_lang_html(page, "vi")

    if not en_html.is_file():
        return {"ok": False, "page": page, "error": "English HTML page missing."}

    # Ensure output directory for vi exists
    vi_html.parent.mkdir(parents=True, exist_ok=True)

    # Prepare translate prompt
    agent_dir = book.page_work(page) / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = agent_dir / "prompt_translate.md"

    slug = book.root.name
    prompt_content = f"""# Phase: Translate page (`translate_page`)

You are a **page translator** for a bilingual digital library.

## Context
Book folder: `{book.root}`
Original page: `output/en/page_{page_str}.html`

## Goal
Translate all visible English content in the original page to natural and accurate Vietnamese, preserving layout fidelity and writing the translated result to `output/vi/page_{page_str}.html`.

## Inputs
1. Original page HTML: `output/en/page_{page_str}.html` (contains layout and text)
2. Glossary guidelines: `books/{slug}/translation/glossary-vi.md` (read for reference)

## Output
Write the translated HTML to: `output/vi/page_{page_str}.html`

## Strict Rules
1. **Preserve Layout and CSS**: Do not change HTML structure, classes, IDs, CSS stylesheets links (e.g. `../assets/...`), or javascript/inline styles. Keep the stand-alone A4 sheet wrapper structure:
   `<body class="book-standalone">` -> `<main class="book-page book-page--sheet">` -> `<article class="sheet-flow prose-page...">`
2. **Strict translation bounds**: Translate only user-visible English text blocks (e.g. headings, paragraphs, labels, list items, table text). Do NOT translate class names, ID attributes, file paths, image source tags (`src`), tag attributes (unless they are labels like `alt`, `title`, or `aria-label`), code fragments, syntax/grammar keywords, or links.
3. **No text expansion / overflow**: Keep translations concise. Ensure the entire page still fits on exactly ONE A4 sheet in print preview, exactly mirroring the layout of the English page.
4. **Glossary rules**: Follow the terminology rules in `books/{slug}/translation/glossary-vi.md`.
5. **No markdown tags or extra talk**: Output only the complete valid HTML file, writing it to `output/vi/page_{page_str}.html`. Do not reply with extra messages.

## Efficiency & Speed Directives (CRITICAL)
To avoid timing out, DO NOT perform redundant exploratory tool calls:
- Do NOT read any stylesheets, other pages' HTML, or search other directories.
- Translate the input English HTML and write the translated output HTML to output/vi/page_{page_str}.html immediately in 1-2 steps.
"""
    prompt_path.write_text(prompt_content, encoding="utf-8")

    cmd = [
        agy_bin,
        "--print-timeout", "15m",
        "--dangerously-skip-permissions",
    ]
    model = os.environ.get("ANTIGRAVITY_MODEL")
    if model:
        cmd.extend(["--model", model])
    cmd.extend([
        "--add-dir", str(book.root),
        "--add-dir", str(repo_root()),
        "--print", f"@{prompt_path}"
    ])

    try:
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=900,  # 15 min timeout
            cwd=str(book.root)
        )
        if proc.returncode != 0:
            err = f"agy failed with code {proc.returncode}. Stderr: {proc.stderr}\nStdout: {proc.stdout}"
            return {"ok": False, "page": page, "error": err}

        if not vi_html.is_file() or vi_html.stat().st_size == 0:
            # Fallback: Extract HTML from stdout if the subagent printed it instead of saving
            stdout_text = proc.stdout or ""
            html_content = ""
            match = re.search(r"```html\s*(.*?)\s*```", stdout_text, re.DOTALL | re.IGNORECASE)
            if match:
                html_content = match.group(1).strip()
            else:
                match_any = re.search(r"```\s*(.*?)\s*```", stdout_text, re.DOTALL)
                if match_any:
                    html_content = match_any.group(1).strip()
                else:
                    html_content = stdout_text.strip()

            if html_content.startswith("<!DOCTYPE html>") or "<html" in html_content:
                vi_html.write_text(html_content, encoding="utf-8")
            else:
                err = f"Translation completed but vi/page.html was not written and stdout did not contain valid HTML. Stderr: {proc.stderr}\nStdout: {proc.stdout}"
                return {"ok": False, "page": page, "error": err}

        # Success!
        return {"ok": True, "page": page}
    except Exception as e:
        return {"ok": False, "page": page, "error": str(e)}


def process_single_page(book: BookPaths, page: int, agy_bin: str, translate: bool) -> dict:
    # 1. Render EN page
    en_html = book.page_lang_html(page, "en")
    render_ok = True
    if not en_html.is_file() or en_html.stat().st_size == 0:
        try:
            res = process_page(book, page, provider="antigravity")
            render_ok = res.get("ok", False)
        except Exception as e:
            return {"ok": False, "page": page, "phase": "render", "error": str(e)}

    if not render_ok:
        return {"ok": False, "page": page, "phase": "render", "error": "Render returned not OK"}

    # 2. Translate to VI page
    if translate:
        vi_html = book.page_lang_html(page, "vi")
        if not vi_html.is_file() or vi_html.stat().st_size == 0:
            res = translate_page(book, page, agy_bin)
            if not res.get("ok"):
                return {"ok": False, "page": page, "phase": "translate", "error": res.get("error")}

    return {"ok": True, "page": page}


def main() -> int:
    parser = argparse.ArgumentParser(description="Parallel render and translate pages")
    parser.add_argument("--book", required=True, help="Path to book folder")
    parser.add_argument("--start-page", type=int, default=1, help="Start page")
    parser.add_argument("--end-page", type=int, help="End page")
    parser.add_argument("--threads", type=int, default=8, help="Number of parallel threads")
    parser.add_argument("--translate", action="store_true", help="Also translate pages to VI")
    args = parser.parse_args()

    book_root = Path(args.book).resolve()
    book = BookPaths.open(book_root)
    page_count = args.end_page if args.end_page else book.estimate_page_count()

    print(f"Processing book: {book_root.name} (pages {args.start_page} to {page_count})")
    
    agy_bin = get_agy_binary() if args.translate else ""
    
    # Identify pages that need processing
    pages_to_process = []
    for page in range(args.start_page, page_count + 1):
        en_html = book.page_lang_html(page, "en")
        vi_html = book.page_lang_html(page, "vi")
        need_render = not en_html.is_file() or en_html.stat().st_size == 0
        need_translate = args.translate and (not vi_html.is_file() or vi_html.stat().st_size == 0)
        
        if need_render or need_translate:
            pages_to_process.append(page)

    if pages_to_process:
        print(f"Starting rendering & translation for {len(pages_to_process)} pages using {args.threads} threads...")
        errors = {}
        with ThreadPoolExecutor(max_workers=args.threads) as executor:
            future_to_page = {
                executor.submit(process_single_page, book, p, agy_bin, args.translate): p
                for p in pages_to_process
            }
            for future in as_completed(future_to_page):
                p = future_to_page[future]
                try:
                    res = future.result()
                    if res.get("ok"):
                        print(f"  ✓ Processed Page {p} (EN & VI complete)")
                    else:
                        print(f"  ✗ Failed Page {p} during {res.get('phase')}: {res.get('error')}")
                        errors[p] = f"{res.get('phase')}: {res.get('error')}"
                except Exception as e:
                    print(f"  ✗ Failed Page {p}: {e}")
                    errors[p] = str(e)
        
        if errors:
            print(f"Processing finished with errors in {len(errors)} pages.")
    else:
        print("All pages already processed and translated.")

    # 3. Post-render and assembly pipeline
    print("Running post-render and assembly scripts...")
    py_bin = sys.executable or "python3"
    scripts_dir = _BACKEND / "scripts"

    # Runs scripts in sequence
    post_scripts = [
        ("extract_pdf_figures.py", []),
        ("upgrade_figure_html.py", []),
        ("refresh_figure_images.py", []),
        ("fix_book_layout.py", []),
        ("validate_page_fidelity.py", ["--lang", "all"]),
    ]

    for script_name, extra_args in post_scripts:
        script_path = scripts_dir / script_name
        if script_path.is_file():
            print(f"Running {script_name}...")
            cmd = [py_bin, str(script_path), str(book_root)] + extra_args
            subprocess.run(cmd, check=False)

    # Assemble EN
    print("Assembling EN book...")
    books_cli_bin = str(Path(_BACKEND).parent / ".venv" / "bin" / "books-cli")
    cmd_assemble_en = [
        py_bin,
        books_cli_bin,
        "assemble",
        "--book", str(book_root),
        "--lang", "en",
        "--output", "book.html"
    ]
    subprocess.run(cmd_assemble_en, check=False)

    # Assemble VI
    if args.translate:
        print("Assembling VI book...")
        cmd_assemble_vi = [
            py_bin,
            books_cli_bin,
            "assemble",
            "--book", str(book_root),
            "--lang", "vi",
            "--output", "book.vi.html"
        ]
        subprocess.run(cmd_assemble_vi, check=False)

    # Validate again
    print("Final validation...")
    cmd_val = [py_bin, str(scripts_dir / "validate_page_fidelity.py"), str(book_root), "--lang", "all"]
    subprocess.run(cmd_val, check=False)

    print("Batch processing complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
