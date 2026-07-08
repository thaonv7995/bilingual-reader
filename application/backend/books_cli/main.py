#!/usr/bin/env python3
"""Books HTML CLI — page-pdf → render → assemble."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from books_agent.doctor import run_doctor
from books_agent.phases import PHASES
from books_agent.session import prepare_session, run_agent
from books_core.extract.service import (
    run_page_pdf,
    run_page_pdf_batch,
    split_pdf_pages,
)
from books_core.assemble import assemble_book_html
from books_core.ingest import find_inbox_pdfs, ingest_pdf
from books_core.meta.reader import book_status_summary
from books_core.paths import BookPaths
from books_core.pipeline.process import process_page
from books_core.package import pack_book, unpack_book
from books_core.book_layout import verify_book


def cmd_status(args: argparse.Namespace) -> int:
    book = BookPaths.open(args.book)
    summary = book_status_summary(book)
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(f"Book: {summary['slug']}")
        print(f"Root: {summary['root']}")
        print(
            f"Pages: {summary['page_count']}  "
            f"page-pdf: {summary['page_pdf_done']}  "
            f"rendered: {summary['published']}"
        )
        for p in summary["pages"][:20]:
            flags = []
            if p.get("page_pdf"):
                flags.append("page-pdf")
            if p.get("published"):
                flags.append("html")
            print(f"  {p['page']:4d}  {' '.join(flags) or 'pending'}")
        if len(summary["pages"]) > 20:
            print(f"  ... and {len(summary['pages']) - 20} more")
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    book = BookPaths.open(args.book)
    print(json.dumps(split_pdf_pages(book), indent=2, ensure_ascii=False))
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    report = run_doctor()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    for p in report["providers"]:
        mark = "✓" if p["installed"] and p["runnable"] else "✗"
        print(f"  {mark} {p['label']}: {p['message']}")
    return 0 if report["ok"] else 1


def cmd_agent_prepare(args: argparse.Namespace) -> int:
    book = BookPaths.open(args.book)
    session = prepare_session(book, args.page, args.phase)
    print(json.dumps(session, indent=2, ensure_ascii=False))
    return 0


def cmd_agent_run(args: argparse.Namespace) -> int:
    book = BookPaths.open(args.book)
    result = run_agent(
        book,
        args.page,
        args.phase,
        args.provider,
        timeout_s=args.timeout,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("exit_code") == 0 else 1


def cmd_ingest(args: argparse.Namespace) -> int:
    """Drop PDF → books/<slug>/input/original.pdf (no library.json)."""
    if args.list_inbox:
        pdfs = find_inbox_pdfs()
        print(json.dumps({"inbox": [str(p) for p in pdfs]}, indent=2, ensure_ascii=False))
        return 0
    if not args.pdf:
        print("Provide --pdf or --list-inbox", file=sys.stderr)
        return 2
    out = ingest_pdf(Path(args.pdf), slug=args.slug, title=args.title)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_page_pdf(args: argparse.Namespace) -> int:
    book = BookPaths.open(args.book)
    if args.page:
        out = run_page_pdf(book, args.page, force=bool(args.force))
        print(json.dumps(out, indent=2, ensure_ascii=False))
    elif args.pending:
        out = run_page_pdf_batch(book, pending_only=True, force=bool(args.force))
        print(json.dumps(out, indent=2, ensure_ascii=False))
    elif args.pages:
        out = run_page_pdf_batch(book, pages_spec=args.pages, force=bool(args.force))
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print("Provide --page N, --pages 1-20, or --pending", file=sys.stderr)
        return 2
    if isinstance(out, dict) and out.get("ok") is False:
        return 1
    elif isinstance(out, list) and any(isinstance(x, dict) and x.get("ok") is False for x in out):
        return 1
    return 0


def cmd_assemble(args: argparse.Namespace) -> int:
    book = BookPaths.open(args.book)
    out = assemble_book_html(
        book,
        lang=args.lang,
        output_name=args.output,
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from books_core.repo import books_dir as get_books_dir

    if not args.book or args.book.lower() == "all":
        library_books_dir = get_books_dir()
        if not library_books_dir.is_dir():
            print(json.dumps({"ok": False, "error": f"Library books directory not found: {library_books_dir}"}))
            return 1

        verified = []
        for child in sorted(library_books_dir.iterdir()):
            if child.is_dir() and not child.name.startswith(".") and child.name not in ("bkbs", "done", "inbox"):
                try:
                    res = verify_book(child, force_assets=bool(args.force_assets))
                    verified.append(res)
                except Exception as e:
                    verified.append({"book": child.name, "ok": False, "error": str(e)})
        print(json.dumps({"ok": True, "verified_books": verified}, indent=2, ensure_ascii=False))
        return 0
    else:
        book = BookPaths.open(args.book)
        out = verify_book(book.root, force_assets=bool(args.force_assets))
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0


def cmd_render(args: argparse.Namespace) -> int:
    book = BookPaths.open(args.book)
    page = int(args.page)
    if args.page_pdf or not book.source_page_pdf(page).is_file():
        run_page_pdf(book, page, force=bool(args.force))
    out = process_page(
        book,
        page,
        args.provider,
        timeout_s=args.timeout,
        force=bool(args.force),
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_pack(args: argparse.Namespace) -> int:
    out = pack_book(args.book, args.output)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_unpack(args: argparse.Namespace) -> int:
    out = unpack_book(args.bkb, args.dest)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn
    from books_cli.server import app
    print(f"Starting Books HTML Web Studio on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="books-cli",
        description="Books HTML — page-pdf → render → assemble",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Book pipeline summary")
    p_status.add_argument("--book", required=True)

    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=cmd_status)

    p_split = sub.add_parser("split", help="Create work/page_NNNN/ folders from PDF")
    p_split.add_argument("--book", required=True)
    p_split.set_defaults(func=cmd_split)

    p_page_pdf = sub.add_parser(
        "page-pdf",
        help="Step 1: extract page N → work/page_NNNN/source.pdf",
    )
    p_page_pdf.add_argument("--book", required=True)
    p_page_pdf.add_argument("--page", type=int)
    p_page_pdf.add_argument("--pages", help="Range e.g. 1-20")
    p_page_pdf.add_argument("--pending", action="store_true")
    p_page_pdf.add_argument("--force", action="store_true")
    p_page_pdf.set_defaults(func=cmd_page_pdf)

    p_ingest = sub.add_parser(
        "ingest",
        help="Drop PDF → books/<slug>/ (from books/inbox/ or any path)",
    )
    p_ingest.add_argument("--pdf", type=Path, help="Path to PDF file")
    p_ingest.add_argument("--slug", help="Book folder name (default: from filename)")
    p_ingest.add_argument("--title")
    p_ingest.add_argument(
        "--list-inbox",
        action="store_true",
        help="List PDFs in books/inbox/",
    )
    p_ingest.set_defaults(func=cmd_ingest)

    p_render = sub.add_parser(
        "render",
        help="Step 2: source.pdf → AI render_page → output/<lang>/page_NNNN.html",
    )
    p_render.add_argument("--book", required=True)
    p_render.add_argument("--page", type=int, required=True)
    p_render.add_argument(
        "--provider",
        required=True,
        choices=["cursor", "codex", "claude", "antigravity"],
    )
    p_render.add_argument("--timeout", type=int, default=3600)
    p_render.add_argument("--page-pdf", action="store_true")
    p_render.add_argument("--force", action="store_true")
    p_render.set_defaults(func=cmd_render)

    p_assemble = sub.add_parser(
        "assemble",
        help="Step 3: output/<lang>/page_*.html → output/book.html",
    )
    p_assemble.add_argument("--book", required=True)
    p_assemble.add_argument("--lang", default="en")
    p_assemble.add_argument("--output", default="book.html")
    p_assemble.set_defaults(func=cmd_assemble)

    p_verify = sub.add_parser(
        "verify",
        help="Verify layout, missing assets, and assemble final book HTMLs before packaging",
    )
    p_verify.add_argument("--book", help="Book directory path or slug (leave empty or use 'all' to verify all books)")
    p_verify.add_argument(
        "--force-assets",
        action="store_true",
        help="Overwrite existing assets with original templates",
    )
    p_verify.set_defaults(func=cmd_verify)

    p_pack = sub.add_parser("pack", help="Pack a book into a .bkb archive")
    p_pack.add_argument("--book", required=True, help="Path to book directory")
    p_pack.add_argument("--output", help="Optional output .bkb path")
    p_pack.set_defaults(func=cmd_pack)

    p_unpack = sub.add_parser("unpack", help="Unpack a .bkb archive")
    p_unpack.add_argument("--bkb", required=True, help="Path to .bkb archive file")
    p_unpack.add_argument("--dest", required=True, help="Destination parent directory (e.g. books/)")
    p_unpack.set_defaults(func=cmd_unpack)

    p_serve = sub.add_parser("serve", help="Start the Web UI & backend server")
    p_serve.add_argument("--host", default="0.0.0.0", help="Binding host")
    p_serve.add_argument("--port", type=int, default=8765, help="Port to run server on")
    p_serve.set_defaults(func=cmd_serve)



    p_doc = sub.add_parser("doctor", help="Detect agent CLIs")
    p_doc.set_defaults(func=cmd_doctor)

    p_ag = sub.add_parser("agent", help="Agent session")
    ag_sub = p_ag.add_subparsers(dest="agent_cmd", required=True)
    p_prep = ag_sub.add_parser("prepare")
    p_prep.add_argument("--book", required=True)
    p_prep.add_argument("--page", type=int, required=True)
    p_prep.add_argument("--phase", required=True, choices=list(PHASES))
    p_prep.set_defaults(func=cmd_agent_prepare)
    p_run = ag_sub.add_parser("run")
    p_run.add_argument("--book", required=True)
    p_run.add_argument("--page", type=int, required=True)
    p_run.add_argument("--phase", required=True, choices=list(PHASES))
    p_run.add_argument("--provider", required=True, choices=["cursor", "codex", "claude", "antigravity"])
    p_run.add_argument("--timeout", type=int, default=3600)
    p_run.set_defaults(func=cmd_agent_run)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
