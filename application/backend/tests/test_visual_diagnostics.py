from __future__ import annotations

import json
from pathlib import Path

import pymupdf as fitz

from books_agent.context import build_context, build_prompt_markdown
from books_core.pipeline import process as pipeline_process
from books_core.paths import BookPaths
from books_core.visual_diagnostics import (
    diagnose_pdf_page,
    diagnosis_path,
    ensure_visual_diagnosis,
    finalize_agent_visual_plan,
    validate_agent_visual_plan,
    validate_html_against_visual_plan,
    validate_html_file_against_visual_plan,
)
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


def _write_raster_figure_pdf(path: Path, *, caption: str | None = "Figure 2.1  Product photograph") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    page = document.new_page(width=600, height=500)
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 160, 100), False)
    pixmap.clear_with(0x55AAEE)
    page.insert_image(fitz.Rect(80, 80, 360, 255), pixmap=pixmap)
    if caption:
        page.insert_text((395, 150), caption, fontsize=10)
    document.save(path)
    document.close()


def _write_full_page_raster_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    page = document.new_page(width=600, height=800)
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 600, 800), False)
    pixmap.clear_with(0x33AAEE)
    page.insert_image(page.rect, pixmap=pixmap)
    document.save(path)
    document.close()


def _page_html(figure_id: str, caption: str) -> str:
    return f"""<!doctype html><html><body><main><article>
<figure class="book-figure">
  <img src="../assets/images/page_0032_fig_{figure_id}.png" alt="Diagram">
  <figcaption>{caption}</figcaption>
</figure>
</article></main></body></html>"""


def _standalone_page_html(figure_id: str, caption: str) -> str:
    return f"""<!doctype html><html><head>
<link rel="stylesheet" href="../assets/book.css">
<link rel="stylesheet" href="../assets/page-tokens.css">
<link rel="stylesheet" href="../assets/prose-page.css">
<link rel="stylesheet" href="../assets/figures-page.css">
</head><body class="book-standalone">
<main class="book-page book-page--sheet"><article class="sheet-flow prose-page">
<figure data-visual-id="{figure_id}">
<img src="../assets/images/page_0010_fig_{figure_id}.png" alt="Photo">
<figcaption>{caption}</figcaption>
</figure></article></main></body></html>"""


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


def test_numbered_photo_caption_is_diagnosed_without_figure_prefix(tmp_path: Path) -> None:
    pdf = tmp_path / "source.pdf"
    _write_raster_figure_pdf(pdf, caption="1. A human handprint made long ago")

    figure = diagnose_pdf_page(pdf, page_num=10)["figures"][0]

    assert figure["id"] == "1"
    assert figure["strategy"] == "extract-raster"
    assert figure["image_count"] == 1
    assert figure["crop_bbox"][2] < figure["caption_bbox"][0]


def test_single_uncaptioned_image_maps_to_single_html_placeholder(tmp_path: Path) -> None:
    pdf = tmp_path / "source.pdf"
    output = tmp_path / "images"
    _write_raster_figure_pdf(pdf, caption=None)

    figures = extract_figures(
        pdf,
        output,
        page_num=10,
        expected_figures=[("page_0010_fig_1.png", "1")],
    )

    assert len(figures) == 1
    assert figures[0]["label"] == "Embedded image fallback"
    assert (output / "page_0010_fig_1.png").is_file()


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
    book = BookPaths(book_root)

    analyze_context = build_context(book, 32, "analyze_visuals")
    analyze_prompt = build_prompt_markdown(book, 32, "analyze_visuals", analyze_context)

    assert analyze_context["output_kind"] == "json"
    assert analyze_context["output_file"] == "work/page_0032/visual-diagnosis.json"
    assert analyze_context["paths"]["source_reference_png"] == "work/page_0032/source.png"
    assert (book_root / "work" / "page_0032" / "source.png").is_file()
    assert '"page": 32' in analyze_prompt
    assert "<page-number>" not in analyze_prompt

    diagnosis_path(book_root, 32).write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "producer": "agent-vision",
                "page": 32,
                "figures": [
                    {
                        "id": "1.1",
                        "type": "diagram",
                        "strategy": "reconstruct-html-svg",
                        "bbox_normalized": [0.14, 0.13, 0.65, 0.62],
                        "caption_bbox_normalized": [0.67, 0.30, 0.95, 0.40],
                        "confidence": 0.98,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    finalized = finalize_agent_visual_plan(book_root, 32)
    assert finalized["producer"] == "agent-vision"
    assert finalized["figures"][0]["snapped_to"] == "pdf-vector"

    context = build_context(book, 32, "render_page")

    assert context["paths"]["visual_diagnosis"] == "work/page_0032/visual-diagnosis.json"
    assert context["visual_diagnosis"]["figures"][0]["strategy"] == "reconstruct-html-svg"
    assert any(
        item["key"] == "visual_diagnosis"
        for item in context["skill_pack"]["inputs"]
    )


def test_full_page_raster_cover_collapses_agent_subregions(tmp_path: Path) -> None:
    book_root = tmp_path / "book"
    pdf = book_root / "work" / "page_0001" / "source.pdf"
    _write_full_page_raster_pdf(pdf)
    diagnosis_path(book_root, 1).write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "producer": "agent-vision",
                "page": 1,
                "figures": [
                    {
                        "id": "1",
                        "type": "illustration",
                        "strategy": "extract-raster",
                        "bbox_normalized": [0.05, 0.60, 0.35, 0.80],
                        "caption_bbox_normalized": None,
                    },
                    {
                        "id": "2",
                        "type": "logo",
                        "strategy": "extract-raster",
                        "bbox_normalized": [0.84, 0.64, 0.96, 0.73],
                        "caption_bbox_normalized": None,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    finalized = finalize_agent_visual_plan(book_root, 1)

    assert len(finalized["figures"]) == 1
    assert finalized["figures"][0]["id"] == "1"
    assert finalized["figures"][0]["type"] == "cover"
    assert finalized["figures"][0]["crop_bbox"] == [0.0, 0.0, 600.0, 800.0]
    assert finalized["figures"][0]["snapped_to"] == "full-page-embedded-image"


def test_scanned_first_page_structured_diagram_is_not_forced_to_cover(tmp_path: Path) -> None:
    book_root = tmp_path / "book"
    pdf = book_root / "work" / "page_0001" / "source.pdf"
    _write_full_page_raster_pdf(pdf)
    diagnosis_path(book_root, 1).write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "producer": "agent-vision",
                "page": 1,
                "figures": [
                    {
                        "id": "1",
                        "type": "family-tree",
                        "strategy": "reconstruct-html-svg",
                        "bbox_normalized": [0.05, 0.08, 0.95, 0.92],
                        "caption_bbox_normalized": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    finalized = finalize_agent_visual_plan(book_root, 1)

    assert finalized["figures"][0]["type"] == "family-tree"
    assert finalized["figures"][0]["strategy"] == "reconstruct-html-svg"
    assert finalized["figures"][0]["snapped_to"] == "agent-region"


def test_extractor_repairs_multi_placeholder_full_page_cover(tmp_path: Path) -> None:
    book = tmp_path / "book"
    pdf = book / "work" / "page_0001" / "source.pdf"
    _write_full_page_raster_pdf(pdf)
    for lang in ("en", "vi"):
        page = book / "output" / lang / "page_0001.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            """<!doctype html><html><body><main><article>
<figure data-visual-id="1"><img src="../assets/images/page_0001_fig_1.png"></figure>
<figure data-visual-id="2"><img src="../assets/images/page_0001_fig_2.png"></figure>
</article></main></body></html>""",
            encoding="utf-8",
        )

    assert extract_main(["extract_pdf_figures.py", str(book), "1"]) == 0
    assert (book / "output" / "assets" / "images" / "page_0001_fig_1.png").is_file()
    assert not (book / "output" / "assets" / "images" / "page_0001_fig_2.png").exists()
    for lang in ("en", "vi"):
        html = (book / "output" / lang / "page_0001.html").read_text(encoding="utf-8")
        assert html.count("page_0001_fig_1.png") == 1
        assert "page_0001_fig_2.png" not in html


def test_extractor_uses_diagnosed_art_crop_and_rewrites_stale_png(tmp_path: Path) -> None:
    book = tmp_path / "book"
    pdf = book / "work" / "page_0032" / "source.pdf"
    _write_raster_figure_pdf(pdf)
    diagnosis = ensure_visual_diagnosis(book, 32, force=True)
    output = book / "output" / "assets" / "images"
    output.mkdir(parents=True)
    stale = output / "page_0032_fig_2_1.png"
    stale.write_bytes(b"stale")

    figures = extract_figures(
        pdf,
        output,
        page_num=32,
        expected_figures=[("page_0032_fig_2_1.png", "2_1")],
    )

    assert len(figures) == 1
    assert figures[0]["clip"] == diagnosis["figures"][0]["crop_bbox"]
    assert figures[0]["clip"][2] < diagnosis["figures"][0]["caption_bbox"][0]
    assert stale.read_bytes().startswith(b"\x89PNG")


def test_extractor_crops_multiple_planned_images_from_one_scanned_page(tmp_path: Path) -> None:
    book = tmp_path / "book"
    pdf = book / "work" / "page_0188" / "source.pdf"
    _write_full_page_raster_pdf(pdf)
    diagnosis_path(book, 188).write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "producer": "agent-vision",
                "status": "finalized",
                "page": 188,
                "figures": [
                    {
                        "id": "1",
                        "type": "photo",
                        "strategy": "extract-raster",
                        "bbox_normalized": [0.08, 0.12, 0.45, 0.42],
                        "crop_bbox": [48.0, 96.0, 270.0, 336.0],
                    },
                    {
                        "id": "2",
                        "type": "photo",
                        "strategy": "extract-raster",
                        "bbox_normalized": [0.55, 0.52, 0.92, 0.82],
                        "crop_bbox": [330.0, 416.0, 552.0, 656.0],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    output = book / "output" / "assets" / "images"

    figures = extract_figures(
        pdf,
        output,
        page_num=188,
        expected_figures=[
            ("page_0188_fig_1.png", "1"),
            ("page_0188_fig_2.png", "2"),
        ],
    )

    assert [figure["figure"] for figure in figures] == ["1", "2"]
    assert (output / "page_0188_fig_1.png").is_file()
    assert (output / "page_0188_fig_2.png").is_file()
    assert figures[1]["clip"] == [330.0, 416.0, 552.0, 656.0]


def test_page_pipeline_runs_agent_vision_before_html_render(tmp_path: Path, monkeypatch) -> None:
    book_root = tmp_path / "book"
    book = BookPaths(book_root)
    _write_raster_figure_pdf(book.source_page_pdf(10))
    calls: list[str] = []

    def fake_agent_step(book_arg, page, phase, provider, **kwargs):
        calls.append(phase)
        if phase == "analyze_visuals":
            diagnosis_path(book_arg.root, page).write_text(
                json.dumps(
                    {
                        "schema_version": "2.0",
                        "producer": "agent-vision",
                        "page": page,
                        "figures": [
                            {
                                "id": "1",
                                "type": "photo",
                                "strategy": "extract-raster",
                                "bbox_normalized": [0.12, 0.14, 0.62, 0.55],
                                "caption_bbox_normalized": [0.65, 0.25, 0.95, 0.35],
                                "confidence": 0.99,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            finalize_agent_visual_plan(book_arg.root, page)
        else:
            output = book_arg.page_lang_html(page, "en")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(_standalone_page_html("1", "Figure 1 Photo"), encoding="utf-8")
        return {"exit_code": 0}

    monkeypatch.setattr(pipeline_process, "_run_agent_step", fake_agent_step)

    result = pipeline_process.process_page(book, 10, "test")

    assert result["ok"] is True
    assert calls == ["analyze_visuals", "render_page"]
    assert result["steps_run"] == ["page-pdf", "analyze_visuals", "render_page"]
    plan = json.loads(diagnosis_path(book_root, 10).read_text(encoding="utf-8"))
    assert plan["producer"] == "agent-vision"
    assert plan["figures"][0]["snapped_to"] == "embedded-image"


def test_html_must_cover_every_agent_planned_visual() -> None:
    plan = {
        "figures": [
            {"id": "1", "strategy": "extract-raster"},
            {"id": "1.1", "strategy": "reconstruct-html-svg"},
        ]
    }
    html = '<img src="../assets/images/page_0010_fig_1.png">'

    assert validate_html_against_visual_plan(html, plan, page_num=10) == [
        "visual plan vector figure 11 has no data-visual-id HTML figure"
    ]

    html += '<figure data-visual-id="1.1"><svg></svg></figure>'
    assert validate_html_against_visual_plan(html, plan, page_num=10) == []


def test_structured_diagram_raster_plan_is_normalized_before_render() -> None:
    for figure_type, label in (
        ("family_tree", "Family Tree"),
        ("diagram", "Relationship exercise"),
        ("relationship-diagram", "Relationship exercise"),
        ("illustration", "Family tree diagram"),
    ):
        plan = {
            "page": 154,
            "figures": [
                {
                    "id": "1",
                    "type": figure_type,
                    "label": label,
                    "strategy": "extract-raster",
                    "bbox_normalized": [0.03, 0.08, 0.97, 0.92],
                }
            ],
        }

        assert validate_agent_visual_plan(plan, page_num=154) is True
        assert plan["figures"][0]["strategy"] == "reconstruct-html-svg"
        assert plan["figures"][0]["strategy_overridden_from"] == "extract-raster"


def test_simple_icon_cannot_create_a_raster_asset_dependency() -> None:
    for figure_type, label in (
        ("icon", "Book"),
        ("book-icon", "Book"),
        ("pictogram", "Book"),
        ("glyph", "Book"),
        ("exercise_marker", "Book"),
        ("illustration", "Book icon"),
    ):
        plan = {
            "page": 23,
            "figures": [
                {
                    "id": "1",
                    "type": figure_type,
                    "label": label,
                    "strategy": "extract-raster",
                    "bbox_normalized": [0.08, 0.05, 0.13, 0.10],
                }
            ],
        }

        assert validate_agent_visual_plan(plan, page_num=23) is True
        assert plan["figures"][0]["strategy"] == "reconstruct-html-svg"

        html = (
            '<span data-visual-id="1">'
            '<img src="../assets/images/page_0023_fig_1.png" alt="Book icon">'
            "</span>"
        )
        assert validate_html_against_visual_plan(html, plan, page_num=23) == [
            "visual plan reconstruct-only figure 1 has a raster image placeholder"
        ]

        html = '<span data-visual-id="1"><svg aria-label="Book icon"></svg></span>'
        assert validate_html_against_visual_plan(html, plan, page_num=23) == []


def test_published_diagram_placeholder_invalidates_cached_page(tmp_path: Path) -> None:
    book = tmp_path / "book"
    plan_path = diagnosis_path(book, 154)
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "producer": "agent-vision",
                "status": "finalized",
                "page": 154,
                "figures": [
                    {
                        "id": "1",
                        "type": "diagram",
                        "strategy": "extract-raster",
                        "bbox_normalized": [0.03, 0.08, 0.97, 0.92],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    html_path = book / "output" / "en" / "page_0154.html"
    html_path.parent.mkdir(parents=True)
    html_path.write_text(
        '<figure data-visual-id="1">'
        '<img src="../assets/images/page_0154_fig_1.png" alt="Family tree">'
        "</figure>",
        encoding="utf-8",
    )

    assert validate_html_file_against_visual_plan(html_path) == [
        "visual plan reconstruct-only figure 1 has a raster image placeholder"
    ]
    persisted = json.loads(plan_path.read_text(encoding="utf-8"))
    assert persisted["figures"][0]["strategy"] == "reconstruct-html-svg"


def test_icon_alt_text_blocks_raster_even_when_plan_type_is_vague() -> None:
    plan = {
        "figures": [
            {
                "id": "1",
                "type": "illustration",
                "label": "Header mark",
                "strategy": "extract-raster",
            }
        ]
    }
    html = (
        '<figure data-visual-id="1">'
        '<img src="../assets/images/page_0154_fig_1.png" alt="Book icon">'
        "</figure>"
    )

    assert validate_html_against_visual_plan(html, plan, page_num=154) == [
        "visual plan reconstruct-only figure 1 has a raster image placeholder"
    ]
