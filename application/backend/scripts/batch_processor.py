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
from books_core.extract.service import run_page_pdf


def get_agy_binary() -> str:
    # Check common locations or PATH
    for path in ["/Users/thaonv/.local/bin/agy", "agy"]:
        if shutil.which(path):
            return path
    raise FileNotFoundError("Could not find agy binary on PATH or common locations.")


def get_translation_error_details(proc, vi_html, agy_log_path: Path) -> str:
    stderr = (proc.stderr or "").strip()
    stdout = (proc.stdout or "").strip()
    
    log_content = ""
    if agy_log_path.is_file():
        try:
            log_text = agy_log_path.read_text(encoding="utf-8", errors="replace")
            log_lines = log_text.splitlines()
            if log_lines:
                log_content = "\n[agy.log tail]:\n" + "\n".join(log_lines[-25:])
        except Exception:
            pass
            
    validation_err = ""
    if vi_html.is_file():
        try:
            content = vi_html.read_text(encoding="utf-8")
            from books_core.validation import validate_draft_html
            validate_draft_html(content)
        except Exception as e:
            validation_err = f"\n[validation error]: {e}"
            
    parts = []
    if stderr:
        parts.append(f"Stderr: {stderr}")
    if stdout:
        parts.append(f"Stdout: {stdout}")
    if log_content:
        parts.append(log_content)
    if validation_err:
        parts.append(validation_err)
        
    return "\n".join(parts) if parts else "No additional error output found."


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
1. **Preserve Layout and CSS**: Do not change HTML structure, classes, IDs, CSS stylesheets links (e.g. `assets/...`), or javascript/inline styles. Keep the stand-alone A4 sheet wrapper structure:
   `<body class="book-standalone">` -> `<main class="book-page book-page--sheet">` -> `<article class="sheet-flow prose-page...">`
2. **Strict translation bounds**: Translate only user-visible English text blocks (e.g. headings, paragraphs, labels, list items, table text). Do NOT translate class names, ID attributes, file paths, image source tags (`src`), tag attributes (unless they are labels like `alt`, `title`, or `aria-label`), code fragments, syntax/grammar keywords, or links.
3. **No text expansion / overflow**: Keep translations concise. Ensure the entire page still fits on exactly ONE A4 sheet in print preview, exactly mirroring the layout of the English page.
4. **Glossary rules**: Follow the terminology rules in `books/{slug}/translation/glossary-vi.md`.
5. **No markdown tags or extra talk**: Output only the complete valid HTML file, writing it to `output/vi/page_{page_str}.html`. Do not reply with extra messages.

## Efficiency & Speed Directives (CRITICAL)
To avoid timing out, DO NOT perform redundant exploratory tool calls:
- Do NOT read any stylesheets, other pages' HTML, or search other directories.
- Translate the input English HTML and write the translated output HTML to output/vi/page_{page_str}.html immediately in 1-2 steps.
- **CRITICAL**: Always write the output HTML file with `IsArtifact: false` (i.e. do NOT set `IsArtifact: true` as it is forbidden and will fail because the output directory is outside the CLI brain).
"""
    prompt_path.write_text(prompt_content, encoding="utf-8")

    agy_log_path = agent_dir / "agy.log"
    cmd = [
        agy_bin,
        "--print-timeout", "15m",
        "--dangerously-skip-permissions",
        "--log-file", str(agy_log_path),
    ]
    model = os.environ.get("ANTIGRAVITY_MODEL")
    if model:
        cmd.extend(["--model", model])
    cmd.extend([
        "--add-dir", str(book.root),
        "--add-dir", str(repo_root()),
        "--print", f"@{prompt_path}"
    ])

    from books_core.pipeline.status import write_process_status, append_live_log, append_stream_chunk

    write_process_status(
        book,
        page,
        state="running",
        step="translate",
        provider="antigravity",
        message="Translating page EN → VI...",
    )
    append_live_log(book, page, f"$ {' '.join(cmd)}")
    append_live_log(book, page, f"Running translation agent...")

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(book.root)
        )
        
        stdout_chunks = []
        stderr_chunks = []
        import threading
        
        def pump_out(pipe, chunks):
            for line in pipe:
                chunks.append(line)
                append_stream_chunk(book, page, line)
                clean_line = line.rstrip()
                if clean_line and os.environ.get("BOOKS_SILENT_WORKERS") != "1":
                    print(f"[Page {page:02d}] [VI] {clean_line}", flush=True)

        def pump_err(pipe, chunks):
            for line in pipe:
                chunks.append(line)
                append_live_log(book, page, f"[stderr] {line.rstrip()}")
                clean_line = line.rstrip()
                if clean_line and os.environ.get("BOOKS_SILENT_WORKERS") != "1":
                    print(f"[Page {page:02d}] [VI ERR] {clean_line}", flush=True)

        t_out = threading.Thread(target=pump_out, args=(proc.stdout, stdout_chunks), daemon=True)
        t_err = threading.Thread(target=pump_err, args=(proc.stderr, stderr_chunks), daemon=True)
        t_out.start()
        t_err.start()

        import time
        from books_core.validation import validate_draft_html
        start_time = time.time()
        completed_successfully = False
        timeout_s = 900
        while proc.poll() is None:
            if vi_html.is_file() and vi_html.stat().st_mtime >= start_time - 1 and vi_html.stat().st_size > 0:
                try:
                    content = vi_html.read_text(encoding="utf-8")
                    validate_draft_html(content)
                    completed_successfully = True
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    break
                except Exception:
                    pass
            time.sleep(1)
            if time.time() - start_time > timeout_s:
                proc.kill()
                proc.wait()
                raise subprocess.TimeoutExpired(cmd, timeout_s)

        t_out.join(timeout=2)
        t_err.join(timeout=2)
        
        proc.stdout = "".join(stdout_chunks)
        proc.stderr = "".join(stderr_chunks)
        returncode = proc.returncode if proc.returncode is not None else 0
        if completed_successfully:
            returncode = 0

        if returncode != 0 and not vi_html.is_file():
            details = get_translation_error_details(proc, vi_html, agy_log_path)
            err = f"agy failed with code {returncode}.\n{details}"
            write_process_status(
                book,
                page,
                state="failed",
                step="translate",
                provider="antigravity",
                error=err,
            )
            append_live_log(book, page, f"Translation failed: {err}")
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
                details = get_translation_error_details(proc, vi_html, agy_log_path)
                err = f"Translation completed but vi/page.html was not written and stdout did not contain valid HTML.\n{details}"
                write_process_status(
                    book,
                    page,
                    state="failed",
                    step="translate",
                    provider="antigravity",
                    error=err,
                )
                append_live_log(book, page, f"Translation failed: {err}")
                return {"ok": False, "page": page, "error": err}

        # Final validation check
        try:
            content = vi_html.read_text(encoding="utf-8")
            validate_draft_html(content)
        except Exception as e:
            details = get_translation_error_details(proc, vi_html, agy_log_path)
            err = f"Translation completed but output vi/page.html failed validation: {e}\n{details}"
            write_process_status(
                book,
                page,
                state="failed",
                step="translate",
                provider="antigravity",
                error=err,
            )
            append_live_log(book, page, f"Translation failed: {err}")
            return {"ok": False, "page": page, "error": err}

        # Success!
        write_process_status(
            book,
            page,
            state="done",
            step="done",
            provider="antigravity",
            message="Done — translation complete",
        )
        append_live_log(book, page, "Translation complete")
        return {"ok": True, "page": page}
    except Exception as e:
        import traceback
        err_tb = f"{e}\n{traceback.format_exc()}"
        write_process_status(
            book,
            page,
            state="failed",
            step="translate",
            provider="antigravity",
            error=err_tb,
        )
        append_live_log(book, page, f"Translation error: {err_tb}")
        return {"ok": False, "page": page, "error": err_tb}


def parse_pages_spec(spec: str, max_page: int) -> list[int]:
    """Parse pages spec like '1-5', '3', '1,3,5' into a list of integers."""
    # Normalize different dash characters (en-dash, em-dash) to standard hyphen
    spec = spec.replace("–", "-").replace("—", "-")
    pages = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                start, end = map(int, part.split("-"))
                for p in range(start, min(end + 1, max_page + 1)):
                    pages.add(p)
            except ValueError:
                continue
        else:
            try:
                p = int(part)
                if 1 <= p <= max_page:
                    pages.add(p)
            except ValueError:
                continue
    return sorted(list(pages))


def process_single_page(book: BookPaths, page: int, agy_bin: str, translate: bool, provider: str = "antigravity", force: bool = False, custom_prompt: str | None = None) -> dict:
    import time
    
    # 1. Render EN page
    en_html = book.page_lang_html(page, "en")
    render_ok = False
    
    if not force and not custom_prompt and en_html.is_file() and en_html.stat().st_size > 0:
        render_ok = True
    else:
        max_retries = 3
        backoff = 5.0
        last_error = ""
        for attempt in range(max_retries):
            try:
                # Proactively ensure page PDF is extracted
                try:
                    run_page_pdf(book, page, force=force)
                except Exception as pe:
                    print(f"[Page {page:02d}] Warning: failed to extract page PDF: {pe}", flush=True)
                
                res = process_page(book, page, provider=provider, force=force, custom_prompt=custom_prompt)
                if res.get("ok"):
                    render_ok = True
                    break
                else:
                    last_error = "Render returned not OK"
            except Exception as e:
                import traceback
                last_error = f"{e}\n{traceback.format_exc()}"
                
            if attempt < max_retries - 1:
                print(f"[Page {page:02d}] [RETRY] Render failed: {last_error}. Retrying in {backoff}s (attempt {attempt+2}/{max_retries})...", flush=True)
                time.sleep(backoff)
                backoff *= 2.0
                
        if not render_ok:
            return {"ok": False, "page": page, "phase": "render", "error": last_error}

    # 2. Translate to VI page
    if translate:
        vi_html = book.page_lang_html(page, "vi")
        if not force and vi_html.is_file() and vi_html.stat().st_size > 0:
            pass
        else:
            translate_ok = False
            max_retries = 3
            backoff = 5.0
            last_error = ""
            for attempt in range(max_retries):
                try:
                    res = translate_page(book, page, agy_bin)
                    if res.get("ok"):
                        translate_ok = True
                        break
                    else:
                        last_error = res.get("error", "Unknown error")
                except Exception as e:
                    import traceback
                    last_error = f"{e}\n{traceback.format_exc()}"
                
                if attempt < max_retries - 1:
                    print(f"[Page {page:02d}] [RETRY] Translation failed: {last_error}. Retrying in {backoff}s (attempt {attempt+2}/{max_retries})...", flush=True)
                    time.sleep(backoff)
                    backoff *= 2.0
                    
            if not translate_ok:
                return {"ok": False, "page": page, "phase": "translate", "error": last_error}

    return {"ok": True, "page": page}


def main() -> int:
    has_errors = False
    parser = argparse.ArgumentParser(description="Parallel render and translate pages")
    parser.add_argument("--book", required=True, help="Path to book folder")
    parser.add_argument("--start-page", type=int, default=1, help="Start page")
    parser.add_argument("--end-page", type=int, help="End page")
    parser.add_argument("--pages", help="Specific pages/ranges to process, e.g. '1-5', '3', '1,3,5'")
    parser.add_argument("--force", action="store_true", help="Force re-render and re-translate existing pages")
    parser.add_argument("--threads", type=int, default=8, help="Number of parallel threads")
    parser.add_argument("--translate", action="store_true", help="Also translate pages to VI")
    parser.add_argument("--provider", default="antigravity", choices=["antigravity", "cursor", "codex", "claude"], help="Provider for rendering")
    parser.add_argument("--custom-prompt", help="Custom prompt instruction for page rendering")
    args = parser.parse_args()

    book_root = Path(args.book).resolve()
    book = BookPaths.open(book_root)
    page_count = args.end_page if args.end_page else book.estimate_page_count()

    if args.pages:
        print(f"Processing book: {book_root.name} (specific pages: {args.pages})")
    else:
        print(f"Processing book: {book_root.name} (pages {args.start_page} to {page_count})")
    
    agy_bin = get_agy_binary() if args.translate else ""
    
    # Identify pages to process
    if args.pages:
        candidate_pages = parse_pages_spec(args.pages, page_count)
    else:
        candidate_pages = list(range(args.start_page, page_count + 1))
        
    from books_core.validation import validate_draft_html
    pages_to_process = []
    for page in candidate_pages:
        en_html = book.page_lang_html(page, "en")
        vi_html = book.page_lang_html(page, "vi")
        
        en_valid = False
        if en_html.is_file() and en_html.stat().st_size > 0:
            try:
                validate_draft_html(en_html.read_text(encoding="utf-8"))
                en_valid = True
            except Exception:
                pass
                
        vi_valid = False
        if vi_html.is_file() and vi_html.stat().st_size > 0:
            try:
                validate_draft_html(vi_html.read_text(encoding="utf-8"))
                vi_valid = True
            except Exception:
                pass

        need_render = args.force or args.custom_prompt or not en_valid
        need_translate = args.translate and (args.force or args.custom_prompt or not vi_valid)
        
        if need_render or need_translate:
            pages_to_process.append(page)

    if pages_to_process:
        print(f"Starting rendering & translation for {len(pages_to_process)} pages using {args.threads} threads...")
        os.environ["BOOKS_SILENT_WORKERS"] = "1"
        errors = {}
        with ThreadPoolExecutor(max_workers=args.threads) as executor:
            future_to_page = {
                executor.submit(process_single_page, book, p, agy_bin, args.translate, args.provider, args.force, args.custom_prompt): p
                for p in pages_to_process
            }
            for future in as_completed(future_to_page):
                p = future_to_page[future]
                try:
                    res = future.result()
                    if res.get("ok"):
                        print(f"  ✓ Processed Page {p} (EN & VI complete)")
                    else:
                        print(f"\n======================================================================")
                        print(f"✗ ERROR ON PAGE {p} DURING PHASE: {res.get('phase').upper()}")
                        print(f"----------------------------------------------------------------------")
                        print(res.get('error'))
                        print(f"======================================================================\n", flush=True)
                        errors[p] = f"{res.get('phase')}: {res.get('error')}"
                except Exception as e:
                    print(f"\n======================================================================")
                    print(f"✗ ERROR ON PAGE {p}:")
                    print(f"----------------------------------------------------------------------")
                    print(str(e))
                    print(f"======================================================================\n", flush=True)
                    errors[p] = str(e)
        
        if errors:
            print(f"Processing finished with errors in {len(errors)} pages.")
            print("Skipping post-processing and assembly because rendering did not complete.")
            return 1
    else:
        print("All pages already processed and translated.")

    # 3. Post-render and assembly pipeline
    py_bin = sys.executable or "python3"
    scripts_dir = _BACKEND / "scripts"

    # For extract_pdf_figures.py, pass the specific pages we processed to speed it up!
    extract_args = []
    if args.pages:
        extract_args = [str(p) for p in candidate_pages]

    # Runs scripts in sequence
    post_scripts = [
        ("extract_pdf_figures.py", extract_args),
        ("upgrade_figure_html.py", []),
        ("refresh_figure_images.py", []),
        ("fix_book_layout.py", []),
        ("validate_page_fidelity.py", ["--lang", "all"]),
    ]

    for script_name, extra_args in post_scripts:
        script_path = scripts_dir / script_name
        if script_path.is_file():
            cmd = [py_bin, str(script_path), str(book_root)] + extra_args
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
            if res.returncode != 0:
                print(f"\n======================================================================")
                print(f"✗ ERROR RUNNING POST-RENDER SCRIPT: {script_name}")
                print(f"----------------------------------------------------------------------")
                print(res.stdout)
                print(f"======================================================================\n", flush=True)
                has_errors = True

    # Assemble EN
    books_cli_bin = str(Path(_BACKEND).parent / ".venv" / "bin" / "books-cli")
    cmd_assemble_en = [
        py_bin,
        books_cli_bin,
        "assemble",
        "--book", str(book_root),
        "--lang", "en",
        "--output", "book.html"
    ]
    res_en = subprocess.run(cmd_assemble_en, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    if res_en.returncode != 0:
        print(f"\n======================================================================")
        print(f"✗ ERROR ASSEMBLING EN BOOK:")
        print(f"----------------------------------------------------------------------")
        print(res_en.stdout)
        print(f"======================================================================\n", flush=True)
        has_errors = True

    # Assemble VI
    if args.translate:
        cmd_assemble_vi = [
            py_bin,
            books_cli_bin,
            "assemble",
            "--book", str(book_root),
            "--lang", "vi",
            "--output", "book.vi.html"
        ]
        res_vi = subprocess.run(cmd_assemble_vi, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        if res_vi.returncode != 0:
            print(f"\n======================================================================")
            print(f"✗ ERROR ASSEMBLING VI BOOK:")
            print(f"----------------------------------------------------------------------")
            print(res_vi.stdout)
            print(f"======================================================================\n", flush=True)
            has_errors = True


    # Validate again
    cmd_val = [py_bin, str(scripts_dir / "validate_page_fidelity.py"), str(book_root), "--lang", "all"]
    res_val = subprocess.run(cmd_val, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    if res_val.returncode != 0:
        print(f"\n======================================================================")
        print(f"✗ ERROR DURING FINAL VALIDATION:")
        print(f"----------------------------------------------------------------------")
        print(res_val.stdout)
        print(f"======================================================================\n", flush=True)
        has_errors = True

    print("Batch processing complete!")
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
