"""Vision-first pipeline: page-pdf → analyze_visuals → render_page."""

from __future__ import annotations

import json
from typing import Any

from books_agent.session import prepare_session, run_agent
from books_core.compile.gates import PipelineGateError, require_page_pdf
from books_core.paths import BookPaths
from books_core.pipeline.status import (
    append_live_log,
    clear_live_log,
    read_process_status,
    write_process_status,
)
from books_core.validation import validate_draft_html
from books_core.visual_diagnostics import (
    agent_visual_plan_ready,
    diagnosis_path,
    validate_html_against_visual_plan,
)


def _page_ready_at(path, *, asset_base=None) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        from books_core.asset_paths import normalize_per_page_asset_file
        from books_core.book_layout import _verify_html_assets

        normalize_per_page_asset_file(path)
        content = path.read_text(encoding="utf-8")
        validate_draft_html(content)
        return not _verify_html_assets(
            path,
            content,
            ignore_page_figures=True,
            asset_base=asset_base,
        )
    except Exception:
        return False


def _published_ready(book: BookPaths, page: int, lang: str | None = None) -> bool:
    lang = lang or book.default_lang()
    published = book.page_lang_html(page, lang)
    if _page_ready_at(published):
        return True
    final = book.final_html(page, lang)
    return _page_ready_at(final, asset_base=book.pages_dir(lang))


def check_published_errors(book: BookPaths, page: int, lang: str) -> str | None:
    published = book.page_lang_html(page, lang)
    if published.is_file():
        if published.stat().st_size == 0:
            return f"{published.name} is empty (0 bytes)"
        try:
            from books_core.asset_paths import normalize_per_page_asset_file

            normalize_per_page_asset_file(published)
            content = published.read_text(encoding="utf-8")
            validate_draft_html(content)
            
            # Verify CSS, JS, and image assets! Ignore page figures as they are cropped post-render
            from books_core.book_layout import _verify_html_assets
            asset_errors = _verify_html_assets(published, content, ignore_page_figures=True)
            if asset_errors:
                return f"{published.name} has broken assets: " + "; ".join(asset_errors)
                
            return None  # Valid!
        except Exception as e:
            return f"{published.name} failed validation: {e}"

    final = book.final_html(page, lang)
    if final.is_file():
        if final.stat().st_size == 0:
            return f"{final.name} is empty (0 bytes)"
        try:
            from books_core.asset_paths import normalize_per_page_asset_file

            normalize_per_page_asset_file(final)
            content = final.read_text(encoding="utf-8")
            validate_draft_html(content)
            
            # Verify CSS, JS, and image assets! Ignore page figures as they are cropped post-render
            from books_core.book_layout import _verify_html_assets
            asset_errors = _verify_html_assets(
                final,
                content,
                ignore_page_figures=True,
                asset_base=book.pages_dir(lang),
            )
            if asset_errors:
                return f"{final.name} has broken assets: " + "; ".join(asset_errors)
                
            return None  # Valid!
        except Exception as e:
            return f"{final.name} failed validation: {e}"

    return "output HTML file is missing"



def _agent_failure_message(page: int, phase: str, result: dict[str, Any]) -> str:
    stderr = (result.get("stderr") or "").strip()
    stdout = (result.get("stdout") or "").strip()
    log_path = result.get("log_path") or "agent/log.txt"
    combined = f"{stderr}\n{stdout}".lower()
    if "authentication required" in combined and "cursor" in combined:
        return (
            f"Page {page}: Cursor agent chưa đăng nhập. "
            "Chạy: cursor agent login — hoặc thêm CURSOR_API_KEY vào application/.env"
        )
    if "authentication required" in combined or "not logged in" in combined:
        return (
            f"Page {page}: agent {phase} cần đăng nhập CLI ({result.get('provider', '')}). "
            f"Xem log: {log_path}"
        )
    tail = stderr or stdout or "see agent log"
    if len(tail) > 400:
        tail = tail[:400] + "…"
    return f"Page {page}: agent {phase} failed (exit {result.get('exit_code')}). {tail} — log: {log_path}"


def _run_agent_step(
    book: BookPaths,
    page: int,
    phase: str,
    provider: str,
    *,
    timeout_s: int,
    custom_prompt: str | None = None,
) -> dict[str, Any]:
    write_process_status(
        book,
        page,
        state="running",
        step=phase,
        provider=provider,
        message=f"Agent {phase}…",
    )
    prepare_session(book, page, phase, custom_prompt=custom_prompt)
    result = run_agent(book, page, phase, provider, timeout_s=timeout_s, custom_prompt=custom_prompt)
    if result.get("exit_code") != 0:
        err = _agent_failure_message(page, phase, result)
        write_process_status(
            book,
            page,
            state="failed",
            step=phase,
            provider=provider,
            error=err,
        )
        raise RuntimeError(err)
    append_live_log(book, page, f"Completed {phase}")
    return result


def process_page(
    book: BookPaths,
    page: int,
    provider: str,
    *,
    timeout_s: int = 3600,
    force: bool = False,
    custom_prompt: str | None = None,
) -> dict[str, Any]:
    """Run page-pdf → agent vision plan → render_page for one page."""
    book.ensure_book_dirs()
    require_page_pdf(book, page)
    lang = book.default_lang()
    clear_live_log(book, page)
    write_process_status(
        book,
        page,
        state="running",
        step="starting",
        provider=provider,
        message="Pipeline: page PDF → Agent vision → AI render",
    )
    steps_run: list[str] = ["page-pdf"]

    try:
        needs_render = force or not _published_ready(book, page, lang) or custom_prompt
        if needs_render:
            if force or not agent_visual_plan_ready(book.root, page):
                _run_agent_step(
                    book,
                    page,
                    "analyze_visuals",
                    provider,
                    timeout_s=timeout_s,
                )
                if not agent_visual_plan_ready(book.root, page):
                    raise PipelineGateError(
                        f"Page {page}: analyze_visuals completed without a finalized agent vision plan."
                    )
                steps_run.append("analyze_visuals")
                append_live_log(book, page, "Finalized agent vision plan")
            _run_agent_step(
                book,
                page,
                "render_page",
                provider,
                timeout_s=timeout_s,
                custom_prompt=custom_prompt,
            )
            steps_run.append("render_page")
            err_msg = check_published_errors(book, page, lang)
            if err_msg:
                raise PipelineGateError(
                    f"Page {page}: AI render finished but {err_msg}."
                )
            rendered_path = book.page_lang_html(page, lang)
            plan = json.loads(
                diagnosis_path(book.root, page).read_text(encoding="utf-8")
            )
            visual_issues = validate_html_against_visual_plan(
                rendered_path.read_text(encoding="utf-8"),
                plan,
                page_num=page,
            )
            if visual_issues:
                raise PipelineGateError(
                    f"Page {page}: rendered HTML does not match the agent visual plan: "
                    + "; ".join(visual_issues)
                )

        out_path = book.page_lang_html(page, lang)
        if not out_path.is_file():
            out_path = book.final_html(page, lang)

        write_process_status(
            book,
            page,
            state="done",
            step="done",
            provider=provider,
            message=f"Done — {out_path.name}",
        )
        append_live_log(book, page, "Pipeline complete")
        return {
            "ok": True,
            "page": page,
            "steps_run": steps_run,
            "output": str(out_path.relative_to(book.root)),
        }
    except Exception as exc:
        import traceback
        err_tb = f"{exc}\n{traceback.format_exc()}"
        write_process_status(
            book,
            page,
            state="failed",
            step=read_process_status(book, page).get("step", "failed"),
            provider=provider,
            error=err_tb,
        )
        raise


process_page_minimal = process_page


def list_pending_render_pages(book: BookPaths) -> list[int]:
    pending: list[int] = []
    for page in range(1, book.estimate_page_count() + 1):
        if not book.source_page_pdf(page).is_file():
            continue
        if _published_ready(book, page):
            continue
        pending.append(page)
    return pending
