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


_INDEX_LAYOUT_FIX = """<style data-layout-fix="index-geometry">
/* Keep reconstructed index pages within one A4 sheet. */
.prose-page.index-page .index-list,
.prose-page.index-page .index-columns {
  gap: 0 !important;
}
.prose-page.index-page .index-item,
.prose-page.index-page .index-entry {
  font-size: 7pt !important;
  line-height: 1.08 !important;
  margin: 0 !important;
}
.prose-page.index-page .index-item.sub-item,
.prose-page.index-page .index-entry.index-sub {
  padding-left: 12mm !important;
}
.prose-page.index-page .index-gap {
  height: 1.5mm !important;
}
</style>"""

_IPA_LAYOUT_FIX = """<style data-layout-fix="ipa-geometry">
/* IPA pages contain nested A4 sheets; constrain the outer flex item and wrap
   interlinear words so the nested sheet itself never creates horizontal loss. */
body.book-standalone .book-page.book-page--sheet,
body.book-standalone .book-page.book-page--sheet > .sheet-flow,
body.book-standalone .book-page.book-page--sheet > .sheet-flow.prose-page.index-page {
  width: 210mm !important;
  max-width: 210mm !important;
  min-width: 0 !important;
  padding: 0 !important;
}
.ipa-sub-sheet {
  flex: 0 0 auto !important;
  width: 210mm !important;
  max-width: 210mm !important;
  min-width: 0 !important;
}
.ipa-sub-sheet .index-item,
.ipa-sub-sheet .index-intro {
  overflow-wrap: anywhere !important;
  word-break: normal !important;
}
</style>"""

_DENSE_PAGE_LAYOUT_FIX = """<style data-layout-fix="dense-page-geometry">
/* Translation can expand prose around fixed source-pixel figures.  Use the
   smallest bounded reduction needed to keep the A4 sheet complete. */
.cover,
.cover-art {
  width: 100% !important;
  height: 100% !important;
  overflow: hidden !important;
}
.cover-art img {
  display: block !important;
  width: 100% !important;
  height: 100% !important;
  object-fit: cover !important;
}
.toc-page .toc-title {
  margin-top: 3mm !important;
  margin-bottom: 9mm !important;
}
.toc-page .toc-frontmatter {
  margin-bottom: 10mm !important;
  gap: 1.4mm !important;
}
.toc-page .toc-section {
  margin-bottom: 9mm !important;
}
.toc-page .toc-chapters {
  gap: 1.8mm !important;
}
.preface-page {
  padding-top: 10mm !important;
  padding-bottom: 12mm !important;
}
.preface-page .preface-title {
  font-size: 18pt !important;
  line-height: 1.08 !important;
  margin-top: 4mm !important;
  margin-bottom: 4mm !important;
}
.preface-page p {
  font-size: 10pt !important;
  line-height: 1.28 !important;
  margin-bottom: 2mm !important;
}
html[lang="vi"] .preface-page p {
  font-size: 9.5pt !important;
  line-height: 1.2 !important;
}
.page-content:has(.bottom-boxes) {
  gap: 2mm !important;
}
.page-content:has(.bottom-boxes) p {
  font-size: 10pt !important;
  line-height: 1.3 !important;
}
.page-15-content .prose-after-collage,
.page-15-content .prose-experience {
  font-size: 10.5pt !important;
  line-height: 1.35 !important;
}
.page-15-content .qualities-list li {
  font-size: 10.5pt !important;
  line-height: 1.3 !important;
  margin-bottom: 1mm !important;
}
.notes-list .note-item {
  font-size: 6pt !important;
  line-height: 1.05 !important;
  margin-bottom: 0.5mm !important;
}
.onetime-table-container {
  margin-top: 2mm !important;
  margin-bottom: 2mm !important;
}
.onetime-table-container .section-title {
  font-size: 9pt !important;
  margin: 1mm 0 !important;
}
.onetime-table-container .onetime-category {
  margin-bottom: 1mm !important;
}
.onetime-table-container .category-header {
  font-size: 8pt !important;
  padding: 0.5mm 2mm !important;
  margin-bottom: 0.5mm !important;
}
.onetime-table-container .onetime-list {
  font-size: 7pt !important;
  line-height: 1.1 !important;
}
.onetime-table-container .onetime-list li {
  margin-bottom: 0.5mm !important;
}
html[lang="vi"] .phase-block {
  margin-top: 3mm !important;
  margin-bottom: 3mm !important;
}
html[lang="vi"] .phase-item {
  line-height: 1.4 !important;
  margin-bottom: 1.2mm !important;
}
html[lang="vi"] .chapter-dots {
  margin-top: 12mm !important;
  margin-bottom: 12mm !important;
}
</style>"""


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


def fix_special_page_layout(html: str) -> str:
    """Apply deterministic geometry fixes to generated index/IPA page shells."""
    additions: list[str] = []
    if "index-page" in html:
        if 'data-layout-fix="index-geometry"' in html:
            html = re.sub(
                r'<style data-layout-fix="index-geometry">.*?</style>',
                _INDEX_LAYOUT_FIX,
                html,
                count=1,
                flags=re.DOTALL,
            )
        else:
            additions.append(_INDEX_LAYOUT_FIX)
    if "ipa-sub-sheet" in html:
        if 'data-layout-fix="ipa-geometry"' in html:
            html = re.sub(
                r'<style data-layout-fix="ipa-geometry">.*?</style>',
                _IPA_LAYOUT_FIX,
                html,
                count=1,
                flags=re.DOTALL,
            )
        else:
            additions.append(_IPA_LAYOUT_FIX)
    if "<article" in html:
        if 'data-layout-fix="dense-page-geometry"' in html:
            html = re.sub(
                r'<style data-layout-fix="dense-page-geometry">.*?</style>',
                _DENSE_PAGE_LAYOUT_FIX,
                html,
                count=1,
                flags=re.DOTALL,
            )
        else:
            additions.append(_DENSE_PAGE_LAYOUT_FIX)
    if not additions:
        return html
    marker = "\n".join(additions)
    if re.search(r"</head>", html, flags=re.I):
        return re.sub(r"</head>", marker + "\n</head>", html, count=1, flags=re.I)
    return marker + html


def process_file(path: Path, chrome: dict[str, str]) -> bool:
    original = path.read_text(encoding="utf-8")
    page = _page_num(path)
    updated = original
    updated = fix_running_head(updated, page, chrome)
    updated = fix_footer(updated, chrome)
    updated = fix_run_in_headings(updated)
    updated = fix_listing_captions(updated)
    updated = fix_unlabeled_code(updated)
    updated = fix_special_page_layout(updated)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: fix_book_layout.py <book-root>", file=sys.stderr)
        return 2
    book_root = Path(argv[1]).resolve()
    output_dir = book_root / "output"
    if not output_dir.is_dir():
        print(f"Missing {output_dir}", file=sys.stderr)
        return 1

    chrome = load_page_chrome(book_root)
    if not chrome.get("head_left"):
        print("WARN: page_chrome.head_left empty — set book.json page_chrome or run page-pdf page 1", file=sys.stderr)

    changed = 0
    page_paths = sorted(
        path
        for lang_dir in output_dir.iterdir()
        if lang_dir.is_dir() and lang_dir.name != "assets"
        for path in lang_dir.glob("page_*.html")
    )
    for path in page_paths:
        if process_file(path, chrome):
            changed += 1
            print(f"fixed {path.parent.name}/{path.name}")
    print(f"Done — {changed} files updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
