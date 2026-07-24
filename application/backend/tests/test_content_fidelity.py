from __future__ import annotations

import json
from pathlib import Path

import pymupdf as fitz

from books_core.content_fidelity import (
    validate_bilingual_structure,
    validate_source_html_content,
)
from books_core.visual_diagnostics import (
    diagnosis_path,
    finalize_agent_visual_plan,
    validate_html_file_against_visual_plan,
)


def _write_text_pdf(path: Path, text: str = "Alpha Beta 2026") -> None:
    document = fitz.open()
    page = document.new_page(width=600, height=800)
    page.insert_text((72, 100), text, fontsize=18)
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()


def test_source_text_gate_detects_missing_tokens_on_single_page_pdf(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    html = tmp_path / "page_0037.html"
    _write_text_pdf(source_pdf)
    html.write_text("<main><p>Alpha only</p></main>", encoding="utf-8")

    issues = validate_source_html_content(
        source_pdf,
        html,
        page_num=37,
    )

    assert issues
    assert "beta" in issues[0]
    assert "2026" in issues[0]


def test_bilingual_gate_allows_text_translation_but_rejects_layout_changes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "en.html"
    translated = tmp_path / "vi.html"
    source.write_text(
        '<main class="sheet"><img src="../assets/a.png">'
        '<svg viewBox="0 0 10 10"><path fill="#123456" d="M0 0h10v10z"></path></svg>'
        "<p>Hello</p></main>",
        encoding="utf-8",
    )
    translated.write_text(
        '<main class="sheet"><img src="../assets/a.png">'
        '<svg viewBox="0 0 10 10"><path fill="#123456" d="M0 0h10v10z"></path></svg>'
        "<p>Xin chào</p></main>",
        encoding="utf-8",
    )
    assert validate_bilingual_structure(source, translated) == []

    translated.write_text(
        '<main class="sheet"><img src="../assets/a.png">'
        '<svg viewBox="0 0 10 10"><path fill="#abcdef" d="M0 0h10v10z"></path></svg>'
        "<p>Xin chào</p></main>",
        encoding="utf-8",
    )
    assert validate_bilingual_structure(source, translated)


def test_visual_plan_validation_fails_closed_when_source_plan_is_missing(
    tmp_path: Path,
) -> None:
    book = tmp_path / "book"
    source_pdf = book / "work" / "page_0001" / "source.pdf"
    html = book / "output" / "en" / "page_0001.html"
    _write_text_pdf(source_pdf)
    html.parent.mkdir(parents=True, exist_ok=True)
    html.write_text("<main><p>Alpha Beta 2026</p></main>", encoding="utf-8")

    assert validate_html_file_against_visual_plan(html) == [
        f"missing finalized visual plan: {book / 'work' / 'page_0001' / 'visual-diagnosis.json'}"
    ]


def test_finalized_visual_plan_preserves_page_layout_contract(tmp_path: Path) -> None:
    book = tmp_path / "book"
    source_pdf = book / "work" / "page_0002" / "source.pdf"
    _write_text_pdf(source_pdf)
    diagnosis_path(book, 2).write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "producer": "agent-vision",
                "page": 2,
                "page_layout": {"mode": "flow"},
                "figures": [],
            }
        ),
        encoding="utf-8",
    )

    finalized = finalize_agent_visual_plan(book, 2)

    assert finalized["page_layout"] == {"mode": "flow"}
