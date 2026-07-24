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
from books_core.asset_paths import normalize_per_page_asset_file
from books_core.book_layout import _verify_html_assets, sync_standard_assets
from books_core.content_fidelity import (
    validate_bilingual_structure,
    validate_source_html_content,
)
from books_core.validation import validate_draft_html
from books_core.visual_diagnostics import diagnosis_path, validate_html_file_against_visual_plan
from books_core.repair_report import write_repair_report


def standalone_page_valid(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        normalize_per_page_asset_file(path)
        content = path.read_text(encoding="utf-8")
        validate_draft_html(content)
        if validate_html_file_against_visual_plan(path):
            return False
        match = re.fullmatch(r"page_(\d{4})\.html", path.name, re.I)
        if match and len(path.parents) >= 3:
            book = BookPaths.open(path.parents[2])
            page = int(match.group(1))
            plan = None
            plan_path = diagnosis_path(book.root, page)
            if plan_path.is_file():
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
            if path.parent.name == book.default_lang():
                source_pdf = book.source_page_pdf(page)
                if source_pdf.is_file() and validate_source_html_content(
                    source_pdf,
                    path,
                    page_num=page,
                    plan=plan,
                ):
                    return False
            else:
                primary = book.page_lang_html(page, book.default_lang())
                if primary.is_file() and validate_bilingual_structure(primary, path):
                    return False
        return not _verify_html_assets(path, content, ignore_page_figures=True)
    except Exception:
        return False


def get_agy_binary() -> str:
    # Check common locations or PATH
    for path in ["/Users/thaonv/.local/bin/agy", "agy"]:
        if shutil.which(path):
            return path
    raise FileNotFoundError("Could not find agy binary on PATH or common locations.")


def get_translation_error_details(proc, target_html, agy_log_path: Path) -> str:
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
    if target_html.is_file():
        try:
            normalize_per_page_asset_file(target_html)
            content = target_html.read_text(encoding="utf-8")
            validate_draft_html(content)
            asset_errors = _verify_html_assets(target_html, content, ignore_page_figures=True)
            if asset_errors:
                raise ValueError("; ".join(asset_errors))
            structure_errors = validate_bilingual_structure(source_html, target_html)
            if structure_errors:
                raise ValueError("; ".join(structure_errors))
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
    source_lang = book.default_lang()
    target_lang = "en" if source_lang == "vi" else "vi"
    source_name = "Vietnamese" if source_lang == "vi" else "English"
    target_name = "English" if target_lang == "en" else "Vietnamese"
    source_html = book.page_lang_html(page, source_lang)
    target_html = book.page_lang_html(page, target_lang)

    if not source_html.is_file():
        return {"ok": False, "page": page, "error": f"{source_name} HTML page missing."}

    target_html.parent.mkdir(parents=True, exist_ok=True)

    # Prepare translate prompt
    agent_dir = book.page_work(page) / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = agent_dir / "prompt_translate.md"

    slug = book.root.name
    prompt_content = f"""# Phase: Translate page (`translate_page`)

You are a **page translator** for a bilingual digital library.

## Context
Book folder: `{book.root}`
Original page: `output/{source_lang}/page_{page_str}.html`

## Goal
Translate all visible {source_name} content in the original page to natural and accurate {target_name}, preserving layout fidelity and writing the translated result to `output/{target_lang}/page_{page_str}.html`.

## Inputs
1. Original page HTML: `output/{source_lang}/page_{page_str}.html` (contains layout and text)
2. Optional glossary: `books/{slug}/translation/glossary-{target_lang}.md`

## Output
Write the translated HTML to: `output/{target_lang}/page_{page_str}.html`

## Strict Rules
1. **Preserve Layout and CSS**: Do not change HTML structure, classes, IDs, CSS stylesheets links (all per-page assets must remain under `../assets/...`), or javascript/inline styles. Keep the stand-alone A4 sheet wrapper structure:
   `<body class="book-standalone">` -> `<main class="book-page book-page--sheet">` -> `<article class="sheet-flow prose-page...">`
   Preserve every `<img>`, `<svg>`, table, figure, element order, source color, dimension, and positioning rule exactly. Translation must edit text nodes only; it must never redesign, recolor, or simplify the page. If the source uses `data-layout-mode="source-anchored"`, preserve that marker and every `data-source-region` marker and do not change any geometry, colors, or CSS positioning. Header fills, page-number colors, table fills, borders, logos, and running chrome are immutable.
2. **Strict translation bounds**: Translate only user-visible {source_name} text blocks (e.g. headings, paragraphs, labels, list items, table text). Do NOT translate class names, ID attributes, file paths, image source tags (`src`), tag attributes (unless they are labels like `alt`, `title`, or `aria-label`), code fragments, syntax/grammar keywords, or links.
   If the page is a full-page facsimile, keep it unchanged; do not replace the source image with an AI-reconstructed translated page.
3. **No text expansion / overflow**: Keep translations concise. Ensure the entire page still fits on exactly ONE A4 sheet in print preview, exactly mirroring the source page.
4. **Glossary rules**: If present, follow `books/{slug}/translation/glossary-{target_lang}.md`.
5. **No markdown tags or extra talk**: Output only the complete valid HTML file, writing it to `output/{target_lang}/page_{page_str}.html`. Do not reply with extra messages.

## Efficiency & Speed Directives (CRITICAL)
To avoid timing out, DO NOT perform redundant exploratory tool calls:
- Do NOT read any stylesheets, other pages' HTML, or search other directories.
- Translate the input HTML and write the translated output HTML to output/{target_lang}/page_{page_str}.html immediately in 1-2 steps.
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
        message=f"Translating page {source_lang.upper()} → {target_lang.upper()}...",
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
                    print(f"[Page {page:02d}] [{target_lang.upper()}] {clean_line}", flush=True)

        def pump_err(pipe, chunks):
            for line in pipe:
                chunks.append(line)
                append_live_log(book, page, f"[stderr] {line.rstrip()}")
                clean_line = line.rstrip()
                if clean_line and os.environ.get("BOOKS_SILENT_WORKERS") != "1":
                    print(f"[Page {page:02d}] [{target_lang.upper()} ERR] {clean_line}", flush=True)

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
            if target_html.is_file() and target_html.stat().st_mtime >= start_time - 1 and target_html.stat().st_size > 0:
                try:
                    content = target_html.read_text(encoding="utf-8")
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

        if returncode != 0 and not target_html.is_file():
            details = get_translation_error_details(proc, target_html, agy_log_path)
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

        if not target_html.is_file() or target_html.stat().st_size == 0:
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
                target_html.write_text(html_content, encoding="utf-8")
            else:
                details = get_translation_error_details(proc, target_html, agy_log_path)
                err = f"Translation completed but {target_lang}/page.html was not written and stdout did not contain valid HTML.\n{details}"
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
            normalize_per_page_asset_file(target_html)
            content = target_html.read_text(encoding="utf-8")
            validate_draft_html(content)
            asset_errors = _verify_html_assets(target_html, content, ignore_page_figures=True)
            if asset_errors:
                raise ValueError("; ".join(asset_errors))
        except Exception as e:
            details = get_translation_error_details(proc, target_html, agy_log_path)
            err = f"Translation completed but output {target_lang}/page.html failed validation: {e}\n{details}"
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
    
    # 1. Render the source language page.
    source_lang = book.default_lang()
    target_lang = "en" if source_lang == "vi" else "vi"
    source_html = book.page_lang_html(page, source_lang)
    render_ok = False
    
    if not force and not custom_prompt and standalone_page_valid(source_html):
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

    # 2. Translate to the other bilingual output.
    if translate:
        target_html = book.page_lang_html(page, target_lang)
        if not force and standalone_page_valid(target_html):
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
    parser = argparse.ArgumentParser(description="Parallel render and translate pages")
    parser.add_argument("--book", required=True, help="Path to book folder")
    parser.add_argument("--start-page", type=int, default=1, help="Start page")
    parser.add_argument("--end-page", type=int, help="End page")
    parser.add_argument("--pages", help="Specific pages/ranges to process, e.g. '1-5', '3', '1,3,5'")
    parser.add_argument("--force", action="store_true", help="Force re-render and re-translate existing pages")
    parser.add_argument("--threads", type=int, default=8, help="Number of parallel threads")
    parser.add_argument("--translate", action="store_true", help="Also create the other EN/VI language")
    parser.add_argument("--provider", default="antigravity", choices=["antigravity", "cursor", "codex", "claude"], help="Provider for rendering")
    parser.add_argument("--custom-prompt", help="Custom prompt instruction for page rendering")
    args = parser.parse_args()

    book_root = Path(args.book).resolve()
    book = BookPaths.open(book_root)
    sync_standard_assets(book)
    source_lang = book.default_lang()
    target_lang = "en" if source_lang == "vi" else "vi"
    if source_lang == "vi":
        args.translate = True
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
        
    pages_to_process = []
    for page in candidate_pages:
        source_html = book.page_lang_html(page, source_lang)
        target_html = book.page_lang_html(page, target_lang)
        
        source_valid = standalone_page_valid(source_html)
        target_valid = standalone_page_valid(target_html)

        need_render = args.force or args.custom_prompt or not source_valid
        need_translate = args.translate and (args.force or args.custom_prompt or not target_valid)
        
        if need_render or need_translate:
            pages_to_process.append(page)

    errors: dict[int, str] = {}
    if pages_to_process:
        print(f"Starting rendering & translation for {len(pages_to_process)} pages using {args.threads} threads...")
        os.environ["BOOKS_SILENT_WORKERS"] = "1"
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
                        draft_status = "EN & VI drafts ready" if args.translate else f"{source_lang.upper()} draft ready"
                        print(f"  ✓ Rendered Page {p} ({draft_status}; post-render pending)")
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
        
    else:
        print("All pages already processed and translated.")

    # 3. Post-render and assembly pipeline
    py_bin = sys.executable or "python3"
    scripts_dir = _BACKEND / "scripts"

    # Asset materialization is intentionally serialized after the worker pool.
    # When some workers fail (for example due to provider quota exhaustion), still
    # finalize every candidate with a valid source draft. Otherwise one late failure
    # leaves successful/skipped pages pointing at figure files that were never
    # created.  Do not move these scripts into the workers: they share the figure
    # manifest and concurrent read/modify/write cycles can lose entries.
    if errors:
        asset_pages = [
            page
            for page in candidate_pages
            if standalone_page_valid(book.page_lang_html(page, source_lang))
        ]
        extract_args = [str(page) for page in asset_pages]
        if asset_pages:
            page_label = "page" if len(asset_pages) == 1 else "pages"
            print(
                f"Finalizing figure assets for {len(asset_pages)} {page_label} with valid {source_lang.upper()} drafts "
                "before reporting worker errors..."
            )
    else:
        # For a targeted run, pass only its requested pages.  An empty list keeps
        # the historical full-book behavior for a non-targeted successful run.
        extract_args = [str(page) for page in candidate_pages] if args.pages else []

    asset_scripts = [
        ("diagnose_page_visuals.py", extract_args),
        ("materialize_vector_figures.py", extract_args),
        ("extract_pdf_figures.py", extract_args),
    ]
    layout_scripts = [
        ("upgrade_figure_html.py", []),
        ("refresh_figure_images.py", []),
        ("fix_book_layout.py", []),
        ("validate_page_fidelity.py", ["--lang", "all", "--pages-only"]),
    ]

    # With worker errors and no valid source drafts, an empty page argument would mean
    # "all pages" to the asset scripts, so skip them instead.
    post_scripts = [] if errors and not extract_args else asset_scripts
    for script_name, extra_args in post_scripts:
        script_path = scripts_dir / script_name
        if script_path.is_file():
            cmd = [py_bin, str(script_path), str(book_root)] + extra_args
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
            if res.returncode != 0:
                write_repair_report(
                    book_root,
                    res.stdout,
                    stage=f"post-render:{script_name}",
                )
                print(f"\n======================================================================")
                print(f"✗ ERROR RUNNING POST-RENDER SCRIPT: {script_name}")
                print(f"----------------------------------------------------------------------")
                print(res.stdout)
                print(f"======================================================================\n", flush=True)
                print("Batch processing failed during post-render; assembly was skipped.")
                return 1

    if errors:
        print(f"Processing finished with errors in {len(errors)} pages.")
        if extract_args:
            page_label = "page" if len(extract_args) == 1 else "pages"
            print(
                f"Figure assets were finalized for {len(extract_args)} {page_label} "
                f"with valid {source_lang.upper()} drafts."
            )
        print("Skipping layout post-processing and assembly because rendering did not complete.")
        return 1

    for script_name, extra_args in layout_scripts:
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
                print("Batch processing failed during post-render; assembly was skipped.")
                return 1

    # Use stable assembled filenames: book.html = EN, book.vi.html = VI.
    books_cli_bin = str(Path(_BACKEND).parent / ".venv" / "bin" / "books-cli")
    assembled_languages = [source_lang]
    if args.translate:
        assembled_languages.append(target_lang)
    for language in assembled_languages:
        output_name = "book.html" if language == "en" else f"book.{language}.html"
        cmd_assemble = [
            py_bin,
            books_cli_bin,
            "assemble",
            "--book", str(book_root),
            "--lang", language,
            "--output", output_name,
        ]
        result = subprocess.run(cmd_assemble, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        if result.returncode != 0:
            print(f"\n======================================================================")
            print(f"✗ ERROR ASSEMBLING {language.upper()} BOOK:")
            print(f"----------------------------------------------------------------------")
            print(result.stdout)
            print(f"======================================================================\n", flush=True)
            print(f"Batch processing failed while assembling the {language.upper()} book.")
            return 1


    # Validate again
    cmd_val = [py_bin, str(scripts_dir / "validate_page_fidelity.py"), str(book_root), "--lang", "all"]
    res_val = subprocess.run(cmd_val, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    if res_val.returncode != 0:
        print(f"\n======================================================================")
        print(f"✗ ERROR DURING FINAL VALIDATION:")
        print(f"----------------------------------------------------------------------")
        print(res_val.stdout)
        print(f"======================================================================\n", flush=True)
        print("Batch processing failed during final validation.")
        return 1

    print("Batch processing complete — render, assets, assembly, and validation passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
