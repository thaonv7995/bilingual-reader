#!/usr/bin/env python3
"""Direct processor using public Gemini API key to avoid daily-cloudcode quota limits."""

import argparse
import base64
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Allow imports from backend
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from books_core.paths import BookPaths
from books_agent.session import prepare_session
from books_core.repo import repo_root
from books_core.asset_paths import normalize_per_page_asset_file
from books_core.book_layout import _verify_html_assets
from books_core.validation import validate_draft_html
from books_core.io import atomic_write_json
from books_core.visual_diagnostics import (
    agent_visual_plan_ready,
    diagnosis_path,
    finalize_agent_visual_plan,
    validate_html_against_visual_plan,
    validate_agent_visual_plan,
)


import time
import urllib.error


def standalone_page_valid(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        normalize_per_page_asset_file(path)
        content = path.read_text(encoding="utf-8")
        validate_draft_html(content)
        return not _verify_html_assets(path, content, ignore_page_figures=True)
    except Exception:
        return False


def get_gemini_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")
    return key


def call_gemini_api(prompt_text: str, pdf_path: Path | None = None) -> str:
    api_key = get_gemini_key()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"

    parts = []
    if pdf_path and pdf_path.is_file():
        pdf_bytes = pdf_path.read_bytes()
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
        parts.append({
            "inlineData": {
                "mimeType": "application/pdf",
                "data": pdf_base64
            }
        })

    parts.append({"text": prompt_text})

    req_data = {
        "contents": [
            {
                "parts": parts
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(req_data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    max_retries = 10
    backoff = 5.0
    resp_data = None

    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                # 429 Too Many Requests: wait and retry
                print(f"    [Retry] Rate limited (429). Sleeping {backoff}s before retry (attempt {attempt+1}/{max_retries})...")
                time.sleep(backoff)
                backoff *= 2.0
                continue
            raise e
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"    [Retry] Transient error ({e}). Sleeping {backoff}s before retry (attempt {attempt+1}/{max_retries})...")
                time.sleep(backoff)
                backoff *= 2.0
                continue
            raise e

    if not resp_data:
        raise RuntimeError("Failed to get response from Gemini API after retries.")

    try:
        text = resp_data["candidates"][0]["content"]["parts"][0]["text"]
        return text
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected response structure from Gemini API: {resp_data}")


def clean_model_output(text: str) -> str:
    # Remove markdown code blocks if present
    match = re.search(r"```html\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match_any = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if match_any:
        return match_any.group(1).strip()
    return text.strip()


def analyze_visuals_direct(book: BookPaths, page: int) -> bool:
    if agent_visual_plan_ready(book.root, page):
        return True
    prepare_session(book, page, "analyze_visuals")
    prompt_path = book.page_work(page) / "agent" / "prompt.md"
    print(f"  [Vision] Analyzing Page {page} visuals with Gemini...")
    response_text = call_gemini_api(
        prompt_path.read_text(encoding="utf-8"),
        book.source_page_pdf(page),
    )
    try:
        raw_plan = json.loads(clean_model_output(response_text))
        validate_agent_visual_plan(raw_plan, page_num=page)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"Visual analysis for Page {page} returned invalid JSON: {exc}") from exc
    atomic_write_json(diagnosis_path(book.root, page), raw_plan)
    finalize_agent_visual_plan(book.root, page)
    print(f"  ✓ Analyzed Page {page} visuals")
    return True


def render_page_direct(book: BookPaths, page: int) -> bool:
    en_html = book.page_lang_html(page, "en")
    if standalone_page_valid(en_html):
        return True

    analyze_visuals_direct(book, page)

    # The analyze phase uses the same session directory, so always prepare the
    # render prompt after the visual plan has been finalized.
    agent_dir = book.page_work(page) / "agent"
    prompt_path = agent_dir / "prompt.md"
    prepare_session(book, page, "render_page")

    prompt_text = prompt_path.read_text(encoding="utf-8")
    pdf_path = book.source_page_pdf(page)

    print(f"  [Render] Sending Page {page} to Gemini...")
    response_text = call_gemini_api(prompt_text, pdf_path)
    html_content = clean_model_output(response_text)

    # Ensure output directory exists
    en_html.parent.mkdir(parents=True, exist_ok=True)
    en_html.write_text(html_content, encoding="utf-8")
    normalize_per_page_asset_file(en_html)
    html_content = en_html.read_text(encoding="utf-8")
    
    # Validate HTML
    try:
        validate_draft_html(html_content)
        asset_errors = _verify_html_assets(en_html, html_content, ignore_page_figures=True)
        if asset_errors:
            raise ValueError("; ".join(asset_errors))
        plan = json.loads(diagnosis_path(book.root, page).read_text(encoding="utf-8"))
        visual_errors = validate_html_against_visual_plan(
            html_content,
            plan,
            page_num=page,
        )
        if visual_errors:
            raise ValueError("; ".join(visual_errors))
    except Exception as e:
        try:
            en_html.unlink()
        except OSError:
            pass
        raise RuntimeError(f"Rendered Page {page} (EN) failed validation: {e}")

    print(f"  ✓ Rendered Page {page} (EN)")
    return True


def translate_page_direct(book: BookPaths, page: int) -> bool:
    vi_html = book.page_lang_html(page, "vi")
    if standalone_page_valid(vi_html):
        return True

    en_html = book.page_lang_html(page, "en")
    if not en_html.is_file():
        print(f"  ✗ Translation skipped for Page {page}: English HTML missing")
        return False

    # Build translation prompt
    glossary_path = book.root / "translation" / "glossary-vi.md"
    glossary_content = ""
    if glossary_path.is_file():
        glossary_content = glossary_path.read_text(encoding="utf-8")

    normalize_per_page_asset_file(en_html)
    en_content = en_html.read_text(encoding="utf-8")

    prompt_text = f"""# Phase: Translate page (`translate_page`)

You are a **page translator** for a bilingual digital library.

## Context
Book folder: `{book.root.name}`
Original page: `output/en/page_{page:04d}.html`

## Goal
Translate all visible English content in the original page to natural and accurate Vietnamese, preserving layout fidelity and writing the translated result to `output/vi/page_{page:04d}.html`.

## Glossary guidelines (read for terminology consistency):
{glossary_content}

## Input Page content to translate:
```html
{en_content}
```

## Strict Rules
1. **Preserve Layout and CSS**: Do not change HTML structure, classes, IDs, CSS stylesheets links (all per-page assets must remain under `../assets/...`), or javascript/inline styles. Keep the stand-alone A4 sheet wrapper structure:
   `<body class="book-standalone">` -> `<main class="book-page book-page--sheet">` -> `<article class="sheet-flow prose-page...">`
2. **Strict translation bounds**: Translate only user-visible English text blocks (e.g. headings, paragraphs, labels, list items, table text). Do NOT translate class names, ID attributes, file paths, image source tags (`src`), tag attributes (unless they are labels like `alt`, `title`, or `aria-label`), code fragments, syntax/grammar keywords, or links.
3. **No text expansion / overflow**: Keep translations concise. Ensure the entire page still fits on exactly ONE A4 sheet in print preview, exactly mirroring the layout of the English page.
4. **No markdown tags or extra talk**: Output only the complete valid HTML file. Do not reply with extra messages. Output format should be raw HTML.
"""

    print(f"  [Translate] Sending Page {page} to Gemini...")
    response_text = call_gemini_api(prompt_text)
    html_content = clean_model_output(response_text)

    vi_html.parent.mkdir(parents=True, exist_ok=True)
    vi_html.write_text(html_content, encoding="utf-8")
    normalize_per_page_asset_file(vi_html)
    html_content = vi_html.read_text(encoding="utf-8")
    
    # Validate HTML
    try:
        validate_draft_html(html_content)
        asset_errors = _verify_html_assets(vi_html, html_content, ignore_page_figures=True)
        if asset_errors:
            raise ValueError("; ".join(asset_errors))
    except Exception as e:
        try:
            vi_html.unlink()
        except OSError:
            pass
        raise RuntimeError(f"Translated Page {page} (VI) failed validation: {e}")

    print(f"  ✓ Translated Page {page} (VI)")
    return True


def process_page_direct(book: BookPaths, page: int, translate: bool) -> dict:
    try:
        render_page_direct(book, page)
        if translate:
            translate_page_direct(book, page)
        return {"ok": True, "page": page}
    except Exception as e:
        import traceback
        err_tb = f"{e}\n{traceback.format_exc()}"
        return {"ok": False, "page": page, "error": err_tb}


def main() -> int:
    parser = argparse.ArgumentParser(description="Direct book processor using Gemini REST API")
    parser.add_argument("--book", required=True, help="Path to book folder")
    parser.add_argument("--start-page", type=int, default=1, help="Start page")
    parser.add_argument("--end-page", type=int, help="End page")
    parser.add_argument("--threads", type=int, default=10, help="Number of parallel threads")
    parser.add_argument("--translate", action="store_true", help="Also translate pages to VI")
    args = parser.parse_args()

    book_root = Path(args.book).resolve()
    book = BookPaths.open(book_root)
    page_count = args.end_page if args.end_page else book.estimate_page_count()

    print(f"=== Direct Processor: {book_root.name} (pages {args.start_page} to {page_count}) ===")
    
    pages_to_process = []
    for page in range(args.start_page, page_count + 1):
        en_html = book.page_lang_html(page, "en")
        vi_html = book.page_lang_html(page, "vi")
        need_render = not standalone_page_valid(en_html)
        need_translate = args.translate and not standalone_page_valid(vi_html)
        
        if need_render or need_translate:
            pages_to_process.append(page)

    if pages_to_process:
        print(f"Processing {len(pages_to_process)} pages with {args.threads} parallel threads...")
        errors = {}
        with ThreadPoolExecutor(max_workers=args.threads) as executor:
            future_to_page = {
                executor.submit(process_page_direct, book, p, args.translate): p
                for p in pages_to_process
            }
            for future in as_completed(future_to_page):
                p = future_to_page[future]
                try:
                    res = future.result()
                    if not res.get("ok"):
                        print(f"  ✗ Failed Page {p}: {res.get('error')}")
                        errors[p] = res.get("error")
                except Exception as e:
                    print(f"  ✗ Failed Page {p}: {e}")
                    errors[p] = str(e)
        
        if errors:
            print(f"Processing complete with errors in {len(errors)} pages.")
            return 1
    else:
        print("All pages already processed.")

    # Post-render pipeline
    print("Running post-render scripts...")
    py_bin = sys.executable or "python3"
    scripts_dir = _BACKEND / "scripts"

    post_scripts = [
        ("diagnose_page_visuals.py", []),
        ("materialize_vector_figures.py", []),
        ("extract_pdf_figures.py", []),
        ("upgrade_figure_html.py", []),
        ("refresh_figure_images.py", []),
        ("fix_book_layout.py", []),
        ("validate_page_fidelity.py", ["--lang", "all", "--pages-only"]),
    ]

    for script_name, extra_args in post_scripts:
        script_path = scripts_dir / script_name
        if script_path.is_file():
            print(f"Running {script_name}...")
            cmd = [py_bin, str(script_path), str(book_root)] + extra_args
            import subprocess
            result = subprocess.run(cmd, check=False)
            if result.returncode != 0:
                print(f"Post-render failed in {script_name}; assembly was skipped.")
                return 1

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
    import subprocess
    if subprocess.run(cmd_assemble_en, check=False).returncode != 0:
        print("EN assembly failed.")
        return 1

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
        if subprocess.run(cmd_assemble_vi, check=False).returncode != 0:
            print("VI assembly failed.")
            return 1

    # Validate again
    print("Final validation...")
    cmd_val = [py_bin, str(scripts_dir / "validate_page_fidelity.py"), str(book_root), "--lang", "all"]
    if subprocess.run(cmd_val, check=False).returncode != 0:
        print("Final validation failed.")
        return 1

    print("Direct processing complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
