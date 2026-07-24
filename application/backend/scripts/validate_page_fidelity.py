#!/usr/bin/env python3
"""Lint per-page and assembled book HTML for fidelity mistakes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from books_core.asset_paths import lint_images_in_html  # noqa: E402
from books_core.book_layout import _verify_html_assets  # noqa: E402
from books_core.content_fidelity import (  # noqa: E402
    validate_bilingual_structure,
    validate_source_html_content,
)
from books_core.paths import BookPaths  # noqa: E402
from books_core.validation import ArtifactValidationError, validate_draft_html  # noqa: E402
from books_core.repair_report import clear_repair_report, write_repair_report  # noqa: E402
from books_core.rendered_layout import validate_rendered_pages  # noqa: E402
from books_core.visual_diagnostics import (  # noqa: E402
    diagnosis_path,
    validate_html_file_against_visual_plan,
)


def _lint_per_page(path: Path, *, chrome: dict[str, str] | None, book: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    name = f"{path.parent.name}/{path.name}"

    try:
        validate_draft_html(text)
    except ArtifactValidationError as exc:
        issues.append(f"{name}: {exc}")

    visual_issues = validate_html_file_against_visual_plan(path)
    issues.extend(f"{name}: {issue}" for issue in visual_issues)

    try:
        book_paths = BookPaths.open(book)
        page_match = re.fullmatch(r"page_(\d{4})\.html", path.name, re.I)
        if page_match:
            page = int(page_match.group(1))
            plan = None
            plan_file = diagnosis_path(book_paths.root, page)
            if plan_file.is_file():
                plan = json.loads(plan_file.read_text(encoding="utf-8"))
            if path.parent.name == book_paths.default_lang():
                source_pdf = book_paths.source_page_pdf(page)
                if source_pdf.is_file():
                    issues.extend(
                        f"{name}: {issue}"
                        for issue in validate_source_html_content(
                            source_pdf,
                            path,
                            page_num=page,
                            plan=plan,
                        )
                    )
            else:
                source_html = book_paths.page_lang_html(page, book_paths.default_lang())
                if source_html.is_file():
                    issues.extend(
                        f"{name}: {issue}"
                        for issue in validate_bilingual_structure(source_html, path)
                    )
    except Exception as exc:
        issues.append(f"{name}: content fidelity validation failed: {exc}")

    if "page-copyright" in text:
        issues.append(f"{name}: use .book-footer not .page-copyright")

    if re.search(r'<h3 class="section-title">[^<]+\.</h3>', text):
        issues.append(f"{name}: h3.section-title ending with '.' → use run-in <strong>")

    if "ascii-figure" in text:
        issues.append(f"{name}: ascii-figure — run extract_pdf_figures.py")

    if re.search(
        r'<figure class="listing">.*?<pre class="code-block">[\s\S]*?</pre>\s*<figcaption>',
        text,
        flags=re.DOTALL,
    ):
        issues.append(f"{name}: listing caption must be above code")

    if chrome and chrome.get("foot_left"):
        foot_left = chrome["foot_left"]
        head = re.search(r"<header class=\"running-head\">(.*?)</header>", text, re.DOTALL)
        if head and foot_left in head.group(1):
            issues.append(f"{name}: author in running-head (belongs in footer)")

    if "figure class=\"diagram\"" in text and "figures-page.css" not in text:
        issues.append(f"{name}: link figures-page.css for diagrams")

    if "code-block" in text and "code-page.css" not in text:
        issues.append(f"{name}: link code-page.css for code")

    if "pdf-render" in text:
        issues.append(f"{name}: forbidden pdf-render marker")

    if "<main" in text and "book-page--sheet" not in text:
        issues.append(f"{name}: missing main.book-page.book-page--sheet shell")

    # lint_images_in_html enforces the URL contract; _verify_html_assets owns
    # existence/size checks so one missing file is reported only once.
    issues.extend(lint_images_in_html(text, context=f"per-page {name}"))
    issues.extend(f"{name}: {issue}" for issue in _verify_html_assets(path, text))
    return issues


def _lint_assembled(path: Path, book: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    name = path.name

    if "prose-page.css" not in text:
        issues.append(f"{name}: assembled book must link assets/prose-page.css")

    if "book-page--sheet" not in text:
        issues.append(f"{name}: each sheet needs main.book-page.book-page--sheet")

    if "sheet-flow prose-page" not in text:
        issues.append(f"{name}: each sheet needs article.sheet-flow.prose-page")

    issues.extend(lint_images_in_html(text, context=f"assembled {name}"))
    issues.extend(f"{name}: {issue}" for issue in _verify_html_assets(path, text))
    return issues


def _load_chrome(book: Path) -> dict[str, str] | None:
    book_json = book / "book.json"
    if not book_json.is_file():
        return None
    data = json.loads(book_json.read_text(encoding="utf-8"))
    chrome = data.get("page_chrome")
    return chrome if isinstance(chrome, dict) else None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_root")
    parser.add_argument("--lang", default="all")
    parser.add_argument(
        "--pages-only",
        action="store_true",
        help="Validate standalone pages but ignore stale assembled book files",
    )
    parser.add_argument(
        "--skip-rendered-layout",
        action="store_true",
        help="Skip Chromium geometry checks (debug/testing only)",
    )
    try:
        args = parser.parse_args(argv[1:])
    except SystemExit as exc:
        return int(exc.code)

    book = Path(args.book_root).resolve()
    lang_arg = args.lang

    chrome = _load_chrome(book)
    all_issues: list[str] = []

    if lang_arg == "all":
        langs = sorted({p.parent.name for p in (book / "output").glob("*/page_*.html")})
    else:
        langs = [lang_arg]

    page_count = 0
    page_paths: list[Path] = []
    for lang in langs:
        pages_dir = book / "output" / lang
        if not pages_dir.is_dir():
            continue
        for path in sorted(pages_dir.glob("page_*.html")):
            page_count += 1
            page_paths.append(path.resolve())
            all_issues.extend(_lint_per_page(path, chrome=chrome, book=book))

    if page_paths and not args.skip_rendered_layout:
        try:
            print(
                f"Checking rendered A4 bounds for {len(page_paths)} page(s) with Chromium...",
                flush=True,
            )
            rendered_issues = validate_rendered_pages(page_paths)
            for path in page_paths:
                name = f"{path.parent.name}/{path.name}"
                all_issues.extend(
                    f"{name}: {message}" for message in rendered_issues.get(path, [])
                )
        except (FileNotFoundError, RuntimeError) as exc:
            all_issues.append(f"Rendered layout validation unavailable: {exc}")

    if not args.pages_only:
        for assembled_name in ("book.html", "book.vi.html"):
            assembled = book / "output" / assembled_name
            if assembled.is_file():
                all_issues.extend(_lint_assembled(assembled, book))

    if page_count == 0:
        print("FAIL No pages found or processed.")
        return 1

    if all_issues:
        for msg in all_issues:
            print(f"FAIL {msg}")
        stage = "post-render" if args.pages_only else "final-validation"
        report_output = "\n".join(f"FAIL {message}" for message in all_issues)
        report = write_repair_report(book, report_output, stage=stage)
        if report:
            pages = ",".join(str(item["page"]) for item in report["pages"])
            print(f"\nREPAIR REPORT — {len(report['pages'])} page(s): {pages}")
        print(f"\n{len(all_issues)} issue(s) — see application/agent/FIDELITY-RULES.md")
        return 1

    if lang_arg == "all":
        clear_repair_report(book)
    print(f"OK — {page_count} page(s), assembled book(s) passed fidelity lint")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
