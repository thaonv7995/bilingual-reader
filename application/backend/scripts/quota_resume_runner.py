#!/usr/bin/env python3
"""Quota-aware resumable batch runner for Books HTML.

This wrapper processes pages in bounded parallel batches, persists progress to a
state file, and stops cleanly when quota-like errors appear. It can be invoked
manually, by cron, or with --watch polling mode.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Allow imports from backend
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from books_core.paths import BookPaths
from books_core.repo import repo_root
from scripts.batch_processor import get_agy_binary, process_single_page, standalone_page_valid


LOCAL_TZ = datetime.now().astimezone().tzinfo or timezone.utc
DEFAULT_STATE_DIRNAME = "quota_resume"

QUOTA_MARKERS = [
    "resource_exhausted",
    "quota reached",
    "quota exhausted",
    "rate limited",
    "too many requests",
    "429",
    "resets in",
]

AUTH_MARKERS = [
    "not authenticated",
    "not logged in",
    "authentication required",
    "account ineligible",
    "oauth",
]


@dataclass
class RunSummary:
    processed: list[int]
    completed: list[int]
    failed: dict[int, str]
    quota_blocked: bool
    auth_blocked: bool
    blocker_message: str | None


def now_local() -> datetime:
    return datetime.now().astimezone()


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_log(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")


def page_done(book: BookPaths, page: int, translate: bool) -> bool:
    en_html = book.page_lang_html(page, "en")
    if not standalone_page_valid(en_html):
        return False
    if translate:
        vi_html = book.page_lang_html(page, "vi")
        if not standalone_page_valid(vi_html):
            return False
    return True


def detect_marker(text: str, markers: list[str]) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in markers)


def classify_error(text: str) -> str:
    if detect_marker(text, QUOTA_MARKERS):
        return "quota"
    if detect_marker(text, AUTH_MARKERS):
        return "auth"
    return "other"


def contiguous_groups(pages: list[int]) -> list[list[int]]:
    if not pages:
        return []
    groups: list[list[int]] = [[pages[0]]]
    for page in pages[1:]:
        if page == groups[-1][-1] + 1:
            groups[-1].append(page)
        else:
            groups.append([page])
    return groups


def compute_pending_pages(book: BookPaths, start_page: int, end_page: int, translate: bool) -> list[int]:
    pending = []
    for page in range(start_page, end_page + 1):
        if not page_done(book, page, translate):
            pending.append(page)
    return pending


def build_state_dir(book: BookPaths, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    return (book.root / "work" / DEFAULT_STATE_DIRNAME).resolve()


def build_run_command(args: argparse.Namespace) -> list[str]:
    cmd = [
        sys.executable or "python3",
        str(Path(__file__).resolve()),
        "--book", str(Path(args.book).resolve()),
        "--start-page", str(args.start_page),
        "--end-page", str(args.end_page),
        "--threads", str(args.threads),
        "--batch-size", str(args.batch_size),
        "--poll-interval-seconds", str(args.poll_interval_seconds),
        "--provider", args.provider,
    ]
    if args.translate:
        cmd.append("--translate")
    if args.run_post_pipeline:
        cmd.append("--run-post-pipeline")
    if args.watch:
        cmd.append("--watch")
    if args.state_dir:
        cmd.extend(["--state-dir", str(Path(args.state_dir).resolve())])
    return cmd


def write_helper_files(state_dir: Path, command: list[str], args: argparse.Namespace) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)

    run_sh = state_dir / "run.sh"
    run_sh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"cd {shlex.quote(str(repo_root()))}\n"
        f"{' '.join(shlex.quote(part) for part in command)}\n",
        encoding="utf-8",
    )
    run_sh.chmod(0o755)

    cron_txt = state_dir / "install-cron.txt"
    cron_txt.write_text(
        "# Run every 15 minutes. Adjust cadence if quota reset windows are longer.\n"
        f"*/15 * * * * {shlex.quote(str(run_sh))} >> {shlex.quote(str(state_dir / 'cron.log'))} 2>&1\n",
        encoding="utf-8",
    )

    readme = state_dir / "README.md"
    readme.write_text(
        "# Quota Resume\n\n"
        f"- State file: `{state_dir / 'state.json'}`\n"
        f"- Runner log: `{state_dir / 'runner.log'}`\n"
        f"- Manual resume: `{run_sh}`\n"
        f"- Cron template: `{cron_txt}`\n\n"
        "Behavior:\n"
        "- Processes pages in bounded parallel batches.\n"
        "- Persists completed pages and pending pages.\n"
        "- Stops on quota/auth blockers instead of blindly retrying.\n"
        "- Runs post-render pipeline only when all pending pages are complete.\n",
        encoding="utf-8",
    )


def init_state(
    path: Path,
    book: BookPaths,
    args: argparse.Namespace,
    pending_pages: list[int],
) -> dict[str, Any]:
    data = load_json(path)
    failed_pages = data.get("failed_pages", {})
    failed_pages = {k: v for k, v in failed_pages.items() if int(k) in pending_pages}
    data.update({
        "book": str(book.root),
        "start_page": args.start_page,
        "end_page": args.end_page,
        "threads": args.threads,
        "batch_size": args.batch_size,
        "translate": args.translate,
        "provider": args.provider,
        "run_post_pipeline": args.run_post_pipeline,
        "pending_pages": pending_pages,
        "completed_pages": data.get("completed_pages", []),
        "failed_pages": failed_pages,
        "status": data.get("status", "ready"),
        "last_blocker": data.get("last_blocker"),
        "last_error_excerpt": data.get("last_error_excerpt"),
        "next_resume_after": data.get("next_resume_after"),
        "updated_at": iso(now_local()),
    })
    save_json(path, data)
    return data


def refresh_state_pages(path: Path, state: dict[str, Any], pending_pages: list[int], completed_pages: list[int]) -> None:
    state["pending_pages"] = pending_pages
    state["completed_pages"] = completed_pages
    state["updated_at"] = iso(now_local())
    save_json(path, state)


def run_chunk(book: BookPaths, pages: list[int], args: argparse.Namespace, agy_bin: str) -> RunSummary:
    completed: list[int] = []
    failed: dict[int, str] = {}
    processed: list[int] = []
    quota_blocked = False
    auth_blocked = False
    blocker_message: str | None = None

    with ThreadPoolExecutor(max_workers=min(args.threads, len(pages))) as executor:
        future_to_page = {
            executor.submit(process_single_page, book, page, agy_bin, args.translate, args.provider): page
            for page in pages
        }
        for future in as_completed(future_to_page):
            page = future_to_page[future]
            processed.append(page)
            try:
                res = future.result()
            except Exception as exc:
                error_text = str(exc)
                failed[page] = error_text
                category = classify_error(error_text)
                if category == "quota":
                    quota_blocked = True
                    blocker_message = error_text
                elif category == "auth":
                    auth_blocked = True
                    blocker_message = error_text
                continue

            if res.get("ok"):
                completed.append(page)
                continue

            error_text = str(res.get("error") or "Unknown error")
            failed[page] = error_text
            category = classify_error(error_text)
            if category == "quota":
                quota_blocked = True
                blocker_message = error_text
            elif category == "auth":
                auth_blocked = True
                blocker_message = error_text

    return RunSummary(
        processed=sorted(processed),
        completed=sorted(completed),
        failed=failed,
        quota_blocked=quota_blocked,
        auth_blocked=auth_blocked,
        blocker_message=blocker_message,
    )


def run_post_pipeline(book_root: Path, translate: bool) -> bool:
    print("Running post-render and assembly pipeline...")
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
            cmd = [py_bin, str(script_path), str(book_root)] + extra_args
            if subprocess.run(cmd, check=False).returncode != 0:
                print(f"Post-render failed in {script_name}; assembly was skipped.")
                return False

    books_cli_bin = str(Path(_BACKEND).parent / ".venv" / "bin" / "books-cli")
    if subprocess.run(
        [py_bin, books_cli_bin, "assemble", "--book", str(book_root), "--lang", "en", "--output", "book.html"],
        check=False,
    ).returncode != 0:
        return False
    if translate:
        if subprocess.run(
            [py_bin, books_cli_bin, "assemble", "--book", str(book_root), "--lang", "vi", "--output", "book.vi.html"],
            check=False,
        ).returncode != 0:
            return False
    if subprocess.run(
        [py_bin, str(scripts_dir / "validate_page_fidelity.py"), str(book_root), "--lang", "all"],
        check=False,
    ).returncode != 0:
        return False
    return True


def process_once(book: BookPaths, args: argparse.Namespace, state_path: Path, log_path: Path) -> int:
    state = load_json(state_path)
    pending_pages = compute_pending_pages(book, args.start_page, args.end_page, args.translate)
    completed_pages = [page for page in range(args.start_page, args.end_page + 1) if page not in pending_pages]

    init_state(state_path, book, args, pending_pages)
    state = load_json(state_path)

    append_log(log_path, f"[{iso(now_local())}] start status={state.get('status')} pending={len(pending_pages)}")

    if not pending_pages:
        state["status"] = "completed"
        state["last_blocker"] = None
        state["last_error_excerpt"] = None
        state["next_resume_after"] = None
        state["completed_pages"] = completed_pages
        state["pending_pages"] = []
        state["updated_at"] = iso(now_local())
        if args.run_post_pipeline and not state.get("post_pipeline_completed"):
            if not run_post_pipeline(book.root, args.translate):
                state["status"] = "post_pipeline_failed"
                state["last_error_excerpt"] = "Post-render pipeline failed"
                save_json(state_path, state)
                return 1
            state["post_pipeline_completed"] = True
            state["post_pipeline_completed_at"] = iso(now_local())
        save_json(state_path, state)
        print("All target pages are already complete.")
        return 0

    state["status"] = "running"
    state["last_started_at"] = iso(now_local())
    state["post_pipeline_completed"] = state.get("post_pipeline_completed", False)
    save_json(state_path, state)

    try:
        agy_bin = get_agy_binary()
    except Exception as exc:
        state["status"] = "blocked_auth"
        state["last_blocker"] = "agy binary missing"
        state["last_error_excerpt"] = str(exc)
        state["updated_at"] = iso(now_local())
        save_json(state_path, state)
        print(f"Blocked: {exc}")
        return 2

    pending_snapshot = compute_pending_pages(book, args.start_page, args.end_page, args.translate)
    next_pages = pending_snapshot[: args.batch_size]
    groups = contiguous_groups(next_pages)

    any_quota = False
    any_auth = False
    last_error: str | None = None
    failed_pages: dict[str, str] = state.get("failed_pages", {})

    for group in groups:
        print(f"Processing pages {group[0]}-{group[-1]} with {min(args.threads, len(group))} threads...")
        append_log(log_path, f"[{iso(now_local())}] processing group={group[0]}-{group[-1]}")
        summary = run_chunk(book, group, args, agy_bin)

        for page in summary.completed:
            print(f"  ✓ Page {page} complete")
            failed_pages.pop(str(page), None)

        for page, error in sorted(summary.failed.items()):
            print(f"  ✗ Page {page} failed: {error}")
            failed_pages[str(page)] = error
            last_error = error

        pending_snapshot = compute_pending_pages(book, args.start_page, args.end_page, args.translate)
        completed_pages = [page for page in range(args.start_page, args.end_page + 1) if page not in pending_snapshot]
        state = load_json(state_path)
        state["failed_pages"] = failed_pages
        refresh_state_pages(state_path, state, pending_snapshot, completed_pages)

        if summary.quota_blocked:
            any_quota = True
            last_error = summary.blocker_message or last_error
            break
        if summary.auth_blocked:
            any_auth = True
            last_error = summary.blocker_message or last_error
            break

    state = load_json(state_path)
    pending_snapshot = compute_pending_pages(book, args.start_page, args.end_page, args.translate)
    completed_pages = [page for page in range(args.start_page, args.end_page + 1) if page not in pending_snapshot]
    state["failed_pages"] = failed_pages
    state["completed_pages"] = completed_pages
    state["pending_pages"] = pending_snapshot
    state["last_finished_at"] = iso(now_local())
    state["last_error_excerpt"] = last_error

    if any_auth:
        state["status"] = "blocked_auth"
        state["last_blocker"] = "authentication"
        state["next_resume_after"] = None
        save_json(state_path, state)
        append_log(log_path, f"[{iso(now_local())}] blocked_auth pending={len(pending_snapshot)}")
        print("Stopped due to authentication or eligibility blocker.")
        return 2

    if any_quota:
        next_resume = now_local() + timedelta(seconds=args.poll_interval_seconds)
        state["status"] = "pending_quota"
        state["last_blocker"] = "quota"
        state["next_resume_after"] = iso(next_resume)
        save_json(state_path, state)
        append_log(log_path, f"[{iso(now_local())}] pending_quota next_resume_after={iso(next_resume)} pending={len(pending_snapshot)}")
        print(f"Quota-like blocker detected. Pending pages remain: {len(pending_snapshot)}")
        print(f"Suggested resume after: {iso(next_resume)}")
        return 3

    if pending_snapshot:
        state["status"] = "partial"
        state["last_blocker"] = None
        state["next_resume_after"] = iso(now_local())
        save_json(state_path, state)
        append_log(log_path, f"[{iso(now_local())}] partial pending={len(pending_snapshot)}")
        print(f"Batch complete. Pending pages remaining: {len(pending_snapshot)}")
        return 0

    state["status"] = "completed"
    state["last_blocker"] = None
    state["next_resume_after"] = None
    if args.run_post_pipeline and not state.get("post_pipeline_completed"):
        if not run_post_pipeline(book.root, args.translate):
            state["status"] = "post_pipeline_failed"
            state["last_error_excerpt"] = "Post-render pipeline failed"
            save_json(state_path, state)
            return 1
        state["post_pipeline_completed"] = True
        state["post_pipeline_completed_at"] = iso(now_local())
    save_json(state_path, state)
    append_log(log_path, f"[{iso(now_local())}] completed")
    print("All target pages complete.")
    return 0


def should_wait_for_resume(state_path: Path) -> tuple[bool, float]:
    state = load_json(state_path)
    when = state.get("next_resume_after")
    if not when:
        return False, 0.0
    try:
        dt = datetime.fromisoformat(when)
    except Exception:
        return False, 0.0
    remaining = (dt - now_local()).total_seconds()
    return remaining > 0, max(remaining, 0.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quota-aware resumable batch runner")
    parser.add_argument("--book", required=True, help="Path to book folder")
    parser.add_argument("--start-page", type=int, default=1, help="Start page")
    parser.add_argument("--end-page", type=int, help="End page")
    parser.add_argument("--threads", type=int, default=4, help="Parallel worker count inside one chunk")
    parser.add_argument("--batch-size", type=int, default=8, help="Max pages to start per invocation before re-evaluating quota")
    parser.add_argument("--translate", action="store_true", help="Also require VI output")
    parser.add_argument("--provider", default="antigravity", choices=["antigravity", "cursor", "codex", "claude"], help="Render provider")
    parser.add_argument("--poll-interval-seconds", type=int, default=900, help="Backoff before next quota retry")
    parser.add_argument("--state-dir", help="Custom state directory")
    parser.add_argument("--watch", action="store_true", help="Keep polling until completion or auth blocker")
    parser.add_argument("--run-post-pipeline", action="store_true", help="Run post-render pipeline once all pages are complete")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    book_root = Path(args.book).resolve()
    book = BookPaths.open(book_root)
    args.end_page = args.end_page if args.end_page else book.estimate_page_count()

    state_dir = build_state_dir(book, args.state_dir)
    state_path = state_dir / "state.json"
    log_path = state_dir / "runner.log"
    write_helper_files(state_dir, build_run_command(args), args)

    if not args.watch:
        return process_once(book, args, state_path, log_path)

    while True:
        wait, seconds = should_wait_for_resume(state_path)
        if wait:
            print(f"Waiting {int(seconds)}s until next resume window...")
            time.sleep(seconds)

        code = process_once(book, args, state_path, log_path)
        if code == 0:
            state = load_json(state_path)
            if state.get("status") == "completed":
                return 0
            time.sleep(max(args.poll_interval_seconds, 60))
            continue
        if code == 3:
            continue
        return code


if __name__ == "__main__":
    sys.exit(main())
