#!/usr/bin/env python3
"""Normalize rendered page HTML to match PDF layout conventions."""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Allow import from backend when run as script
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from books_core.page_chrome import load_page_chrome  # noqa: E402


def _page_num(path: Path) -> int:
    return int(path.stem.split("_")[1])


_FRONT_MATTER_RE = re.compile(
    r'class="[^"]*\b(?:title-page|cover|flap|toc|copy|ded|preface-page|chapter-page|chapter-body-page|manning-chapter-opener)\b',
    re.I,
)

# Chapter pages carry section/chapter titles + printed folio in the running head.
_CHAPTER_BODY_RE = re.compile(r'\bchapter-(?:body-)?page\b', re.I)

# Index continuation pages use INDEX + printed folio in the running head.
_INDEX_PAGE_RE = re.compile(r'\bindex-page\b', re.I)


def fix_running_head(html: str, page: int, chrome: dict[str, str]) -> str:
    if _FRONT_MATTER_RE.search(html) or _CHAPTER_BODY_RE.search(html) or _INDEX_PAGE_RE.search(html):
        return html

    head_left = chrome.get("head_left") or ""
    return re.sub(
        r'<header class="running-head">.*?</header>',
        (
            '<header class="running-head">\n'
            f'        <span class="rh-left">{head_left}</span>\n'
            '        <span class="rh-center"></span>\n'
            f'        <span class="rh-right">{page}</span>\n'
            "      </header>"
        ),
        html,
        count=1,
        flags=re.DOTALL,
    )


def fix_footer(html: str, chrome: dict[str, str]) -> str:
    if _FRONT_MATTER_RE.search(html) or _CHAPTER_BODY_RE.search(html) or _INDEX_PAGE_RE.search(html):
        return html

    foot_left = chrome.get("foot_left") or ""
    foot_right = chrome.get("foot_right") or ""

    if not foot_left and not foot_right:
        return html

    footer_html = (
        '<footer class="book-footer">\n'
        f"        <span>{foot_left}</span>\n"
        f"        <span>{foot_right}</span>\n"
        "      </footer>"
    )

    html = re.sub(
        r'<footer class="page-copyright">.*?</footer>',
        footer_html,
        html,
        flags=re.DOTALL,
    )

    if "book-footer" not in html and foot_left:
        html = re.sub(
            r"(</article>)",
            f"      {footer_html}\n    \\1",
            html,
            count=1,
        )
    return html


def fix_run_in_headings(html: str) -> str:
    def repl(match: re.Match[str]) -> str:
        title = match.group(1).strip()
        body = match.group(2).strip()
        return (
            f'<p class="no-indent"><strong class="run-in">{title}</strong> {body}</p>'
        )

    prev = None
    while prev != html:
        prev = html
        html = re.sub(
            r'<h3 class="section-title">([^<]+\.)</h3>\s*<p(?:\s[^>]*)?>(.*?)</p>',
            repl,
            html,
            count=1,
            flags=re.DOTALL,
        )
    return html


def fix_listing_captions(html: str) -> str:
    return re.sub(
        r'<figure class="diagram">\s*<figcaption>(Listing \d+-\d+)<br>([^<]+)</figcaption>\s*<pre class="code-block">',
        r'<figure class="listing"><figcaption><strong>\1</strong><br>\2</figcaption><pre class="code-block">',
        html,
    )


def fix_unlabeled_code(html: str) -> str:
    return re.sub(
        r'<figure class="diagram">\s*<pre class="code-block">',
        r'<figure class="code-snippet"><pre class="code-block">',
        html,
        count=0,
    )


def process_file(path: Path, chrome: dict[str, str]) -> bool:
    original = path.read_text(encoding="utf-8")
    page = _page_num(path)
    updated = original
    updated = fix_running_head(updated, page, chrome)
    updated = fix_footer(updated, chrome)
    updated = fix_run_in_headings(updated)
    updated = fix_listing_captions(updated)
    updated = fix_unlabeled_code(updated)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: fix_book_layout.py <book-root>", file=sys.stderr)
        return 2
    book_root = Path(argv[1]).resolve()
    pages_dir = book_root / "output" / "en"
    if not pages_dir.is_dir():
        print(f"Missing {pages_dir}", file=sys.stderr)
        return 1

    chrome = load_page_chrome(book_root)
    if not chrome.get("head_left"):
        print("WARN: page_chrome.head_left empty — set book.json page_chrome or run page-pdf page 1", file=sys.stderr)

    changed = 0
    for path in sorted(pages_dir.glob("page_*.html")):
        if process_file(path, chrome):
            changed += 1
            print(f"fixed {path.name}")
    print(f"Done — {changed} files updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
