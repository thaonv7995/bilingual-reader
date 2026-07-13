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


def _lint_per_page(path: Path, *, chrome: dict[str, str] | None, book: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    issues: list[str] = []
    name = f"{path.parent.name}/{path.name}"

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
    for lang in langs:
        pages_dir = book / "output" / lang
        if not pages_dir.is_dir():
            continue
        for path in sorted(pages_dir.glob("page_*.html")):
            page_count += 1
            all_issues.extend(_lint_per_page(path, chrome=chrome, book=book))

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
        print(f"\n{len(all_issues)} issue(s) — see application/agent/FIDELITY-RULES.md")
        return 1

    print(f"OK — {page_count} page(s), assembled book(s) passed fidelity lint")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
