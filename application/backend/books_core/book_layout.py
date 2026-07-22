"""Scaffold and normalize per-book folder layout."""

from __future__ import annotations

import shutil
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from books_core.io import atomic_write_json, atomic_write_text
from books_core.paths import BookPaths, normalize_book_layout
from books_core.repo import skills_root


class _CssContextCollector(HTMLParser):
    """Collect CSS only from style elements and inline style attributes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._style_depth = 0
        self.css_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "style":
            self._style_depth += 1
        for name, value in attrs:
            if name.lower() == "style" and value:
                self.css_chunks.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "style" and self._style_depth:
            self._style_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._style_depth:
            self.css_chunks.append(data)


def _css_contexts(html_content: str) -> list[str]:
    collector = _CssContextCollector()
    collector.feed(html_content)
    collector.close()
    return collector.css_chunks


def _copy_if_exists(src: Path, dest: Path) -> None:
    if src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def sync_standard_assets(book: BookPaths) -> None:
    """Refresh generated CSS assets so existing books receive renderer fixes."""
    templates = Path(__file__).parent / "templates"
    assets = book.output_dir / "assets"
    for name in (
        "book.css",
        "page-tokens.css",
        "prose-page.css",
        "toc-page.css",
        "code-page.css",
        "figures-page.css",
    ):
        _copy_if_exists(templates / name, assets / name)


def scaffold_book(
    book_dir: Path,
    *,
    title: str,
    pdf_source: Path,
    page_count: int,
    slug: str | None = None,
    source_lang: str = "en",
    source_format: str = "pdf",
) -> BookPaths:
    """
    Canonical layout:

        <slug>/
          book.json
          input/original.pdf      ← user input
          work/                   ← generated intermediate
          output/
            assets/               ← CSS + images for HTML
            <lang>/page_NNNN.html ← deliverables
            index.html
    """
    book_dir.mkdir(parents=True, exist_ok=True)
    book = BookPaths.open(book_dir)
    book.ensure_book_dirs()
    book.pages_dir(source_lang).mkdir(parents=True, exist_ok=True)

    shutil.copy2(pdf_source, book.input_dir / "original.pdf")

    sync_standard_assets(book)

    from books_core.page_chrome import detect_page_chrome_from_pdf

    page_chrome = detect_page_chrome_from_pdf(book.input_dir / "original.pdf")

    slug = slug or book_dir.name
    meta: dict = {
        "schema_version": "2.0",
        "slug": slug,
        "title": title,
        "page_count": page_count,
        "source_lang": source_lang,
        "source_format": source_format,
        "languages": [
            {"code": source_lang, "role": "primary"},
            {
                "code": "en" if source_lang == "vi" else "vi",
                "role": "translation",
            },
        ],
        "layout": {
            "input": "input/original.pdf",
            "work": "work",
            "output": "output",
            "output_pages": "output/{lang}/page_{page:04d}.html",
        },
    }
    if page_chrome:
        meta["page_chrome"] = page_chrome
    atomic_write_json(book.book_json, meta)

    rows = "\n".join(
        f'        <tr><td>{n}</td><td>{source_lang}/page_{n:04d}.html</td><td>pending</td></tr>'
        for n in range(1, min(page_count, 30) + 1)
    )
    index = f"""<!doctype html>
<html lang="{source_lang}">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <link rel="stylesheet" href="assets/book.css">
</head>
<body>
  <main class="book-page">
    <h1>{title}</h1>
    <p>{page_count} pages — pipeline: page-pdf → render</p>
    <table>
      <thead><tr><th>Page</th><th>HTML</th><th>Status</th></tr></thead>
      <tbody>
{rows}
      </tbody>
    </table>
  </main>
</body>
</html>
"""
    atomic_write_text(book.index_html, index)
    return book


def _verify_html_assets(
    html_path: Path,
    html_content: str,
    *,
    ignore_page_figures: bool = False,
    asset_base: Path | None = None,
) -> list[str]:
    """
    Verify local CSS/JS/image refs resolve on disk.

    asset_base: directory used to resolve relative URLs. Defaults to html_path.parent.
    Use this when validating work/page_NNNN/final.*.html whose ../assets/ links are
    written for output/<lang>/ (not for the work/ folder).
    """
    import re
    import urllib.parse

    from books_core.asset_paths import resolve_relative_asset

    errors: list[str] = []
    base = Path(asset_base) if asset_base is not None else html_path.parent

    def _local_ref(ref: str) -> str | None:
        if ref.startswith(("http://", "https://", "//", "mailto:", "tel:", "data:", "#")):
            return None
        return ref

    # 1. Stylesheets
    css_refs = re.findall(r'<link\s+[^>]*href=["\']([^"\']+)["\']', html_content, flags=re.I)
    for ref in css_refs:
        if _local_ref(ref) is None:
            continue
        if " " in ref:
            errors.append(f"CSS link contains unencoded spaces: '{ref}'")
        asset_path = resolve_relative_asset(base, ref)
        if not asset_path.is_file():
            errors.append(f"Missing CSS: '{ref}'")
        elif asset_path.stat().st_size == 0:
            errors.append(f"Empty CSS: '{ref}'")

    # 2. Images
    img_refs = re.findall(r'<img\s+[^>]*src=["\']([^"\']+)["\']', html_content, flags=re.I)
    srcset_refs = re.findall(
        r'<(?:source|img)\s+[^>]*srcset=["\']([^"\']+)["\']',
        html_content,
        flags=re.I,
    )
    img_refs.extend(
        re.findall(r'<(?:video|object)\s+[^>]*(?:poster|data)=["\']([^"\']+)["\']', html_content, flags=re.I)
    )
    for css in _css_contexts(html_content):
        img_refs.extend(
            re.findall(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)', css, flags=re.I)
        )
    for ref in srcset_refs:
        img_refs.extend(
            candidate.strip().split()[0]
            for candidate in ref.split(",")
            if candidate.strip()
        )
    img_refs = list(dict.fromkeys(ref.strip() for ref in img_refs))
    for ref in img_refs:
        if _local_ref(ref) is None:
            continue
        if " " in ref:
            errors.append(f"Image link contains unencoded spaces: '{ref}'")
        clean_ref = urllib.parse.unquote(ref.split("?")[0])

        # Skip page-specific dynamic figures (cropped post-render)
        if ignore_page_figures and "_fig_" in clean_ref.lower() and Path(clean_ref).name.startswith("page_"):
            continue

        asset_path = resolve_relative_asset(base, ref)
        if not asset_path.is_file():
            errors.append(f"Missing image: '{ref}'")
        elif asset_path.stat().st_size == 0:
            errors.append(f"Empty image file: '{ref}'")

    # 3. Scripts
    js_refs = re.findall(r'<script\s+[^>]*src=["\']([^"\']+)["\']', html_content, flags=re.I)
    for ref in js_refs:
        if _local_ref(ref) is None:
            continue
        if " " in ref:
            errors.append(f"JS link contains unencoded spaces: '{ref}'")
        asset_path = resolve_relative_asset(base, ref)
        if not asset_path.is_file():
            errors.append(f"Missing JS: '{ref}'")
        elif asset_path.stat().st_size == 0:
            errors.append(f"Empty JS: '{ref}'")

    return errors


def verify_book(
    book_dir: Path | str,
    *,
    force_assets: bool = False,
) -> dict[str, Any]:
    """
    Verify a book's structure, assets, and page validity:
    1. Normalize layout (legacy flat layout to input/work/output).
    2. Repair missing or empty template CSS assets.
    3. Verify that all pages in book.json (or estimated page count) are rendered and valid.
    4. Compile/Assemble the final EN (and VI if present) book HTML files.
    5. Return status, warning list, and whether it's ready to pack.
    """
    book_dir = Path(book_dir).expanduser().resolve()
    # Normalize layout first in case it is in legacy layout
    normalize_result = normalize_book_layout(book_dir)

    book = BookPaths.open(book_dir)
    book.ensure_book_dirs()

    # 2. Repair assets
    tpl_dir = Path(__file__).parent / "templates"
    assets = book.output_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    repaired_assets = []
    css_files = [
        (tpl_dir / "book.css", assets / "book.css"),
        (tpl_dir / "page-tokens.css", assets / "page-tokens.css"),
        (tpl_dir / "prose-page.css", assets / "prose-page.css"),
        (tpl_dir / "toc-page.css", assets / "toc-page.css"),
        (tpl_dir / "code-page.css", assets / "code-page.css"),
        (tpl_dir / "figures-page.css", assets / "figures-page.css"),
    ]

    for src, dest in css_files:
        if not src.is_file():
            continue
        if force_assets or not dest.is_file() or dest.stat().st_size == 0:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            repaired_assets.append(dest.name)

    # 3. Verify pages
    meta = book.load_book_json()
    page_count = meta.get("page_count", 0) or book.estimate_page_count()

    warnings = []
    missing_pages_en = []
    missing_pages_vi = []
    invalid_pages_en = []
    invalid_pages_vi = []

    from books_core.asset_paths import normalize_per_page_asset_file
    from books_core.validation import validate_draft_html
    from concurrent.futures import ThreadPoolExecutor

    default_lang = book.default_lang()
    translation_lang = "en" if default_lang == "vi" else "vi"
    translation_dir = book.pages_dir(translation_lang)
    has_translation = translation_dir.is_dir()

    def check_single_page(page: int) -> dict[str, Any]:
        res_dict = {
            "page": page,
            "missing_en": [],
            "missing_vi": [],
            "invalid_en": [],
            "invalid_vi": [],
            "normalized": [],
            "is_broken": False
        }
        # Check EN
        en_path = book.page_lang_html(page, default_lang)
        if not en_path.is_file():
            res_dict["missing_en"].append(page)
            res_dict["is_broken"] = True
        elif en_path.stat().st_size == 0:
            res_dict["invalid_en"].append(f"Page {page} ({default_lang}) is empty")
            res_dict["is_broken"] = True
        else:
            try:
                if normalize_per_page_asset_file(en_path):
                    res_dict["normalized"].append(str(en_path.relative_to(book.root)))
                content = en_path.read_text(encoding="utf-8")
                validate_draft_html(content)
                asset_errors = _verify_html_assets(en_path, content)
                if asset_errors:
                    res_dict["is_broken"] = True
                    for err in asset_errors:
                        res_dict["invalid_en"].append(f"Page {page} ({default_lang}) - {err}")
            except Exception as e:
                res_dict["is_broken"] = True
                res_dict["invalid_en"].append(f"Page {page} ({default_lang}) invalid: {e}")

        # Check the optional second bilingual output.
        if has_translation:
            vi_path = book.page_lang_html(page, translation_lang)
            if not vi_path.is_file():
                res_dict["missing_vi"].append(page)
                res_dict["is_broken"] = True
            elif vi_path.stat().st_size == 0:
                res_dict["invalid_vi"].append(f"Page {page} ({translation_lang}) is empty")
                res_dict["is_broken"] = True
            else:
                try:
                    if normalize_per_page_asset_file(vi_path):
                        res_dict["normalized"].append(str(vi_path.relative_to(book.root)))
                    content = vi_path.read_text(encoding="utf-8")
                    validate_draft_html(content)
                    asset_errors = _verify_html_assets(vi_path, content)
                    if asset_errors:
                        res_dict["is_broken"] = True
                        for err in asset_errors:
                            res_dict["invalid_vi"].append(f"Page {page} ({translation_lang}) - {err}")
                except Exception as e:
                    res_dict["is_broken"] = True
                    res_dict["invalid_vi"].append(f"Page {page} ({translation_lang}) invalid: {e}")
        return res_dict

    # Run check in parallel using 12 threads
    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(check_single_page, range(1, page_count + 1)))

    broken_pages = []
    normalized_pages = []
    for r in results:
        page = r["page"]
        missing_pages_en.extend(r["missing_en"])
        missing_pages_vi.extend(r["missing_vi"])
        invalid_pages_en.extend(r["invalid_en"])
        invalid_pages_vi.extend(r["invalid_vi"])
        normalized_pages.extend(r["normalized"])
        if r["is_broken"]:
            broken_pages.append(page)

    if missing_pages_en:
        warnings.append(f"Missing {len(missing_pages_en)} primary pages: {missing_pages_en[:10]}")
    if missing_pages_vi and translation_dir.is_dir():
        warnings.append(f"Missing {len(missing_pages_vi)} translated pages: {missing_pages_vi[:10]}")
    warnings.extend(invalid_pages_en)
    warnings.extend(invalid_pages_vi)

    # 4. Assemble the book
    assembled_files = []
    assembly_ok = True
    try:
        from books_core.assemble import assemble_book_html
        languages = [default_lang]
        if has_translation:
            languages.append(translation_lang)
        for lang in languages:
            output_name = "book.html" if lang == "en" else f"book.{lang}.html"
            result = assemble_book_html(book, lang, output_name)
            if result.get("ok"):
                out_file = result.get("output")
                assembled_files.append(out_file)
                out_path = (book.root / str(out_file)).resolve() if out_file else None
                if out_path is not None and out_path.is_file():
                    content = out_path.read_text(encoding="utf-8")
                    asset_errors = _verify_html_assets(out_path, content)
                    if asset_errors:
                        assembly_ok = False
                    for err in asset_errors:
                        warnings.append(f"Assembled ({lang}) - {err}")
            else:
                assembly_ok = False
                warnings.append(f"Assembly ({lang}) failed: {result.get('error')}")
    except Exception as ae:
        assembly_ok = False
        warnings.append(f"Assembly exception: {ae}")

    # Ready to pack requires no missing/invalid pages and successful assembly with no local asset errors in pages
    # Note: we check if there are any warnings/invalid pages.
    has_page_errors = any(
        (
            missing_pages_en,
            missing_pages_vi,
            invalid_pages_en,
            invalid_pages_vi,
        )
    )
    ready_to_pack = (not has_page_errors) and assembly_ok

    return {
        "ok": ready_to_pack,
        "book": str(book.root),
        "page_count": page_count,
        "moved": normalize_result.get("moved", []),
        "repaired_assets": repaired_assets,
        "normalized_pages": sorted(normalized_pages),
        "assembled_files": assembled_files,
        "warnings": warnings,
        "ready_to_pack": ready_to_pack,
        "broken_pages": sorted(broken_pages),
    }
