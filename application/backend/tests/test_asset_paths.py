from __future__ import annotations

import json
from pathlib import Path

from books_core.assemble import assemble_book_html
from books_core.asset_paths import (
    lint_images_in_html,
    normalize_per_page_asset_file,
    normalize_per_page_asset_paths,
)
from books_core.book_layout import _verify_html_assets, verify_book
from books_core.paths import BookPaths
from scripts.refresh_figure_images import refresh_page
from scripts.upgrade_figure_html import upgrade_page


def _page_html(body: str, *, assets: str = "assets/") -> str:
    return f"""<!doctype html>
<html><head>
  <link rel="stylesheet" href="{assets}book.css">
  <link rel="stylesheet" href="{assets}page-tokens.css">
  <link rel="stylesheet" href="{assets}prose-page.css">
</head><body class="book-standalone">
  <main class="book-page book-page--sheet"><article class="sheet-flow prose-page">
    {body}
  </article></main>
</body></html>"""


def _book(tmp_path: Path, *, with_vi: bool = False) -> BookPaths:
    root = tmp_path / "book"
    (root / "input").mkdir(parents=True)
    (root / "input" / "original.pdf").write_bytes(b"%PDF")
    (root / "output" / "assets" / "images").mkdir(parents=True)
    for name in ("book.css", "page-tokens.css", "prose-page.css", "figures-page.css"):
        (root / "output" / "assets" / name).write_text("/* test */", encoding="utf-8")
    (root / "output" / "en").mkdir()
    if with_vi:
        (root / "output" / "vi").mkdir()
    (root / "book.json").write_text(
        json.dumps({"title": "Test", "page_count": 1, "source_lang": "en"}),
        encoding="utf-8",
    )
    return BookPaths.open(root)


def test_normalize_per_page_asset_paths_covers_html_url_forms() -> None:
    html = """
    <link href='assets/book.css'>
    <img src="assets/images/a.png" srcset="assets/images/a.png 1x, assets/images/a@2x.png 2x">
    <div style="background-image: url('assets/images/bg.png')"></div>
    <a href="https://example.com/assets/help">Help</a>
    """

    normalized = normalize_per_page_asset_paths(html)

    assert "href='../assets/book.css'" in normalized
    assert 'src="../assets/images/a.png"' in normalized
    assert 'srcset="../assets/images/a.png 1x, ../assets/images/a@2x.png 2x"' in normalized
    assert "url('../assets/images/bg.png')" in normalized
    assert 'href="https://example.com/assets/help"' in normalized


def test_per_page_assets_resolve_and_assemble_to_root_assets(tmp_path: Path) -> None:
    book = _book(tmp_path)
    image = book.output_dir / "assets" / "images" / "page_0001_fig_1.png"
    image.write_bytes(b"png")
    page = book.page_lang_html(1, "en")
    page.write_text(
        _page_html('<img src="assets/images/page_0001_fig_1.png" alt="Figure 1">'),
        encoding="utf-8",
    )

    assert normalize_per_page_asset_file(page) is True
    content = page.read_text(encoding="utf-8")
    assert _verify_html_assets(page, content) == []
    assert lint_images_in_html(
        content,
        context="per-page en/page_0001.html",
        book_root=book.root,
    ) == []

    result = assemble_book_html(book, "en")
    assert result["ok"] is True
    assembled = (book.output_dir / "book.html").read_text(encoding="utf-8")
    assert 'src="assets/images/page_0001_fig_1.png"' in assembled
    assert 'src="../assets/' not in assembled


def test_asset_verifier_ignores_java_methods_ending_in_url(tmp_path: Path) -> None:
    book = _book(tmp_path)
    page = book.page_lang_html(1, "en")
    page.write_text(
        _page_html(
            """
            <pre class="code-block"><code>.formLogin()
              .loginProcessingUrl("/authenticate")
              .defaultSuccessUrl("/design")</code></pre>
            """,
            assets="../assets/",
        ),
        encoding="utf-8",
    )

    content = page.read_text(encoding="utf-8")
    assert _verify_html_assets(page, content) == []


def test_asset_verifier_still_checks_css_url_references(tmp_path: Path) -> None:
    book = _book(tmp_path)
    page = book.page_lang_html(1, "en")
    page.write_text(
        _page_html(
            """
            <style>.hero { background-image: url('../assets/images/missing-style.png'); }</style>
            <div style="background-image: url('../assets/images/missing-inline.png')"></div>
            """,
            assets="../assets/",
        ),
        encoding="utf-8",
    )

    content = page.read_text(encoding="utf-8")
    assert _verify_html_assets(page, content) == [
        "Missing image: '../assets/images/missing-style.png'",
        "Missing image: '../assets/images/missing-inline.png'",
    ]


def test_refresh_preserves_figures_and_normalizes_legacy_paths(tmp_path: Path) -> None:
    book = _book(tmp_path)
    existing = book.output_dir / "assets" / "images" / "page_0001_fig_1.png"
    existing.write_bytes(b"png")
    page = book.page_lang_html(1, "en")
    page.write_text(
        _page_html(
            """
            <figure class="diagram"><img class="diagram-img" loading="lazy"
              src="assets/images/page_0001_fig_1.png" width="1" height="1" alt="Figure 1">
              <figcaption>Figure 1: Existing</figcaption></figure>
            <figure class="diagram"><img src="assets/images/page_0001_fig_2.png" alt="Figure 2">
              <figcaption>Figure 2: Missing crop</figcaption></figure>
            """
        ),
        encoding="utf-8",
    )
    manifest = {
        "page_0001": [
            {
                "figure": "1",
                "file": "images/page_0001_fig_1.png",
                "width": 640,
                "height": 480,
            }
        ]
    }

    assert refresh_page(page, manifest) is True
    content = page.read_text(encoding="utf-8")
    assert content.count("<figure") == 2
    assert 'src="../assets/images/page_0001_fig_1.png"' in content
    assert 'src="../assets/images/page_0001_fig_2.png"' in content
    assert 'class="diagram-img"' in content
    assert 'loading="lazy"' in content
    assert 'width="640"' in content
    assert 'height="480"' in content
    assert 'href="../assets/figures-page.css"' in content


def test_upgrade_plain_figure_id_for_en_and_vi(tmp_path: Path) -> None:
    book = _book(tmp_path, with_vi=True)
    manifest = {
        "page_0001": [
            {
                "figure": "1",
                "file": "images/page_0001_fig_1.png",
                "width": 320,
                "height": 200,
            }
        ]
    }
    for lang, label in (("en", "Figure 1"), ("vi", "Hình 1")):
        page = book.page_lang_html(1, lang)
        page.write_text(
            _page_html(
                f'<figure class="diagram"><figcaption>{label}</figcaption>'
                '<pre class="ascii-figure">box</pre></figure>'
            ),
            encoding="utf-8",
        )
        assert upgrade_page(page, manifest) is True
        content = page.read_text(encoding="utf-8")
        assert 'src="../assets/images/page_0001_fig_1.png"' in content
        assert "ascii-figure" not in content


def test_verify_normalizes_both_languages_and_counts_vi_asset_errors(tmp_path: Path) -> None:
    book = _book(tmp_path, with_vi=True)
    book.page_lang_html(1, "en").write_text(_page_html("<p>EN</p>"), encoding="utf-8")
    book.page_lang_html(1, "vi").write_text(
        _page_html('<img src="assets/images/missing.png" alt="missing">'),
        encoding="utf-8",
    )

    result = verify_book(book.root)

    assert result["ready_to_pack"] is False
    assert "output/en/page_0001.html" in result["normalized_pages"]
    assert "output/vi/page_0001.html" in result["normalized_pages"]
    assert any("Page 1 (vi) - Missing image" in warning for warning in result["warnings"])
