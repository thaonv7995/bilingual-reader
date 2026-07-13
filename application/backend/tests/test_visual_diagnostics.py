from __future__ import annotations

from pathlib import Path

import pymupdf as fitz

from books_agent.context import build_context
from books_core.paths import BookPaths
from books_core.visual_diagnostics import diagnose_pdf_page, ensure_visual_diagnosis
from scripts.extract_pdf_figures import extract_figures, main as extract_main
from scripts.materialize_vector_figures import materialize_page


def _write_vector_figure_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    page = document.new_page(width=600, height=500)
    page.draw_rect(fitz.Rect(90, 70, 380, 300), color=(0.2, 0.2, 0.2), fill=(0.9, 0.96, 0.9))
    page.draw_rect(fitz.Rect(120, 110, 220, 180), color=(0.2, 0.2, 0.2), fill=(0.7, 0.85, 0.95))
    page.draw_rect(fitz.Rect(270, 110, 350, 180), color=(0.2, 0.2, 0.2), fill=(0.8, 0.72, 0.86))
    page.draw_line((220, 145), (270, 145), color=(0.1, 0.1, 0.1), width=1.5)
    page.insert_text((127, 148), "Inventory", fontsize=11)
    page.insert_text((280, 148), "Product", fontsize=11)
    page.insert_text((405, 170), "Figure 1.1  Components are managed", fontsize=10)
    page.insert_text((405, 184), "and injected into one another.", fontsize=10)
    document.save(path)
    document.close()


def _write_raster_figure_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    page = document.new_page(width=600, height=500)
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 160, 100), False)
    pixmap.clear_with(0x55AAEE)
    page.insert_image(fitz.Rect(80, 80, 360, 255), pixmap=pixmap)
    page.insert_text((395, 150), "Figure 2.1  Product photograph", fontsize=10)
    document.save(path)
    document.close()


def _page_html(figure_id: str, caption: str) -> str:
    return f"""<!doctype html><html><body><main><article>
<figure class="book-figure">
  <img src="../assets/images/page_0032_fig_{figure_id}.png" alt="Diagram">
  <figcaption>{caption}</figcaption>
</figure>
</article></main></body></html>"""


def test_side_caption_diagnosis_keeps_complete_art_bounds(tmp_path: Path) -> None:
    pdf = tmp_path / "source.pdf"
    _write_vector_figure_pdf(pdf)

    diagnosis = diagnose_pdf_page(pdf, page_num=32)
    figure = diagnosis["figures"][0]

    assert figure["id"] == "1.1"
    assert figure["strategy"] == "reconstruct-html-svg"
    assert figure["caption_position"] == "right"
    assert figure["image_count"] == 0
    assert figure["crop_bbox"][2] < figure["caption_bbox"][0]
    assert figure["crop_bbox"][3] >= figure["art_bbox"][3]


def test_embedded_image_is_kept_as_raster(tmp_path: Path) -> None:
    pdf = tmp_path / "source.pdf"
    _write_raster_figure_pdf(pdf)

    figure = diagnose_pdf_page(pdf, page_num=32)["figures"][0]

    assert figure["strategy"] == "extract-raster"
    assert figure["image_count"] == 1
    assert figure["caption_position"] == "right"


def test_vector_placeholder_becomes_inline_svg_in_all_languages(tmp_path: Path) -> None:
    book = tmp_path / "book"
    pdf = book / "work" / "page_0032" / "source.pdf"
    _write_vector_figure_pdf(pdf)
    for lang, caption in (("en", "Figure 1.1 Components"), ("vi", "Hình 1.1 Các thành phần")):
        page = book / "output" / lang / "page_0032.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(_page_html("1_1", caption), encoding="utf-8")
    ensure_visual_diagnosis(book, 32, force=True)

    changed = materialize_page(book, 32)

    assert len(changed) == 2
    for lang in ("en", "vi"):
        html = (book / "output" / lang / "page_0032.html").read_text(encoding="utf-8")
        assert '<svg xmlns="http://www.w3.org/2000/svg"' in html
        assert 'data-visual-strategy="reconstruct-html-svg"' in html
        assert "<img" not in html
        assert "<figcaption>" in html
    assert extract_main(["extract_pdf_figures.py", str(book), "32"]) == 0
    assert not (book / "output" / "assets" / "images" / "page_0032_fig_1_1.png").exists()


def test_render_context_includes_visual_strategy_before_agent_runs(tmp_path: Path) -> None:
    book_root = tmp_path / "book"
    _write_vector_figure_pdf(book_root / "work" / "page_0032" / "source.pdf")

    context = build_context(BookPaths(book_root), 32, "render_page")

    assert context["paths"]["visual_diagnosis"] == "work/page_0032/visual-diagnosis.json"
    assert context["visual_diagnosis"]["figures"][0]["strategy"] == "reconstruct-html-svg"
    assert any(
        item["key"] == "visual_diagnosis"
        for item in context["skill_pack"]["inputs"]
    )


def test_extractor_uses_diagnosed_art_crop_and_rewrites_stale_png(tmp_path: Path) -> None:
    book = tmp_path / "book"
    pdf = book / "work" / "page_0032" / "source.pdf"
    _write_vector_figure_pdf(pdf)
    diagnosis = ensure_visual_diagnosis(book, 32, force=True)
    output = book / "output" / "assets" / "images"
    output.mkdir(parents=True)
    stale = output / "page_0032_fig_1_1.png"
    stale.write_bytes(b"stale")

    figures = extract_figures(
        pdf,
        output,
        page_num=32,
        expected_figures=[("page_0032_fig_1_1.png", "1_1")],
    )

    assert len(figures) == 1
    assert figures[0]["clip"] == diagnosis["figures"][0]["crop_bbox"]
    assert figures[0]["clip"][2] < diagnosis["figures"][0]["caption_bbox"][0]
    assert stale.read_bytes().startswith(b"\x89PNG")
