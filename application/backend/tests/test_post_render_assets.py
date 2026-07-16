from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pymupdf as fitz

from scripts import batch_processor
from scripts.extract_pdf_figures import main as extract_main
from scripts.extract_pdf_figures import process_book
from scripts.validate_page_fidelity import _lint_per_page
from scripts.validate_page_fidelity import main as validate_main


def _write_source_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page(width=200, height=300)
    page.draw_rect(fitz.Rect(0, 0, 200, 300), color=(0.1, 0.2, 0.5), fill=(0.1, 0.2, 0.5))
    page.insert_text((30, 150), "Cover", fontsize=28, color=(1, 1, 1))
    doc.save(path)
    doc.close()


def _page_html(body: str) -> str:
    return f"""<!doctype html>
<html><head>
  <link rel="stylesheet" href="../assets/book.css">
  <link rel="stylesheet" href="../assets/page-tokens.css">
  <link rel="stylesheet" href="../assets/prose-page.css">
</head><body class="book-standalone">
  <main class="book-page book-page--sheet"><article class="sheet-flow prose-page">
    {body}
  </article></main>
</body></html>"""


def _book(tmp_path: Path, *, page_count: int = 1) -> Path:
    book = tmp_path / "book"
    (book / "output" / "en").mkdir(parents=True)
    (book / "output" / "assets" / "images").mkdir(parents=True)
    (book / "output" / "assets" / "book.css").write_text(
        """@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
.book-page.book-page--sheet { width: 210mm; height: 296mm; overflow: hidden; }
.sheet-flow { width: 100%; height: 100%; overflow: hidden; }
img { max-width: 100%; height: auto; }
""",
        encoding="utf-8",
    )
    for name in ("page-tokens.css", "prose-page.css", "figures-page.css"):
        (book / "output" / "assets" / name).write_text("/* test */", encoding="utf-8")
    (book / "book.json").write_text(
        json.dumps({"title": "Test", "page_count": page_count, "source_lang": "en"}),
        encoding="utf-8",
    )
    return book


def test_first_page_cover_placeholder_is_materialized(tmp_path: Path) -> None:
    book = _book(tmp_path)
    _write_source_pdf(book / "work" / "page_0001" / "source.pdf")
    page = book / "output" / "en" / "page_0001.html"
    page.write_text(
        _page_html('<figure class="cover"><img src="../assets/images/page_0001_fig_1.png"></figure>'),
        encoding="utf-8",
    )

    manifest = process_book(book, [1])

    image = book / "output" / "assets" / "images" / "page_0001_fig_1.png"
    assert image.is_file()
    assert image.stat().st_size > 0
    assert manifest["page_0001"][0]["file"] == "images/page_0001_fig_1.png"
    assert manifest["page_0001"][0]["label"] == "First-page cover fallback"
    assert manifest["page_0001"][0]["raster_width"] > 0
    assert manifest["page_0001"][0]["raster_height"] > 0
    assert manifest["page_0001"][0]["display_width_pt"] == 200
    assert manifest["page_0001"][0]["display_height_pt"] == 300
    assert extract_main(["extract_pdf_figures.py", str(book), "1"]) == 0


def test_extractor_fails_early_for_unmaterialized_non_cover_placeholder(
    tmp_path: Path,
    capsys,
) -> None:
    book = _book(tmp_path, page_count=2)
    _write_source_pdf(book / "work" / "page_0002" / "source.pdf")
    (book / "output" / "en" / "page_0002.html").write_text(
        _page_html('<figure><img src="../assets/images/page_0002_fig_1.png"></figure>'),
        encoding="utf-8",
    )

    assert extract_main(["extract_pdf_figures.py", str(book), "2"]) == 1
    assert "extractor did not create referenced figure" in capsys.readouterr().err


def test_fidelity_reports_one_missing_asset_and_can_ignore_stale_assembly(
    tmp_path: Path,
    capsys,
) -> None:
    book = _book(tmp_path)
    page = book / "output" / "en" / "page_0001.html"
    page.write_text(
        _page_html('<img src="../assets/images/missing.png">'),
        encoding="utf-8",
    )
    issues = _lint_per_page(page, chrome=None, book=book)
    missing = [issue for issue in issues if "missing" in issue.lower()]
    assert missing == ["en/page_0001.html: Missing image: '../assets/images/missing.png'"]

    page.write_text(_page_html("<p>Valid page</p>"), encoding="utf-8")
    (book / "output" / "book.html").write_text(
        '<img src="assets/images/stale-missing.png">',
        encoding="utf-8",
    )
    assert validate_main([
        "validate_page_fidelity.py",
        str(book),
        "--lang",
        "all",
        "--pages-only",
        "--skip-rendered-layout",
    ]) == 0
    assert "OK" in capsys.readouterr().out


def test_batch_stops_before_assembly_when_post_render_fails(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    book = _book(tmp_path)
    _write_source_pdf(book / "work" / "page_0001" / "source.pdf")
    (book / "output" / "en" / "page_0001.html").write_text(
        _page_html('<img src="../assets/images/page_0001_fig_1.png">'),
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def fail_first(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, stdout="extract failed")

    monkeypatch.setattr(batch_processor.subprocess, "run", fail_first)
    monkeypatch.setattr(
        sys,
        "argv",
        ["batch_processor.py", "--book", str(book), "--pages", "1", "--threads", "1"],
    )

    assert batch_processor.main() == 1
    assert len(calls) == 1
    assert calls[0][1].endswith("diagnose_page_visuals.py")
    output = capsys.readouterr().out
    assert "assembly was skipped" in output
    assert "Batch processing complete" not in output


def test_batch_finalizes_valid_page_assets_before_returning_worker_errors(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    book = _book(tmp_path, page_count=2)
    _write_source_pdf(book / "work" / "page_0001" / "source.pdf")
    (book / "output" / "en" / "page_0001.html").write_text(
        _page_html(
            '<figure class="cover"><img src="../assets/images/page_0001_fig_1.png" '
            'alt="Cover"></figure>'
        ),
        encoding="utf-8",
    )

    def fail_page_two(*_args, **_kwargs):
        return {"ok": False, "page": 2, "phase": "render", "error": "quota exhausted"}

    monkeypatch.setattr(batch_processor, "process_single_page", fail_page_two)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "batch_processor.py",
            "--book",
            str(book),
            "--pages",
            "1-2",
            "--threads",
            "12",
        ],
    )

    assert batch_processor.main() == 1
    assert (book / "output" / "assets" / "images" / "page_0001_fig_1.png").is_file()
    assert not (book / "output" / "book.html").exists()
    output = capsys.readouterr().out
    assert "Figure assets were finalized for 1 page" in output
    assert "Skipping layout post-processing and assembly" in output


def test_batch_materializes_cover_then_assembles_successfully(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    book = _book(tmp_path)
    _write_source_pdf(book / "work" / "page_0001" / "source.pdf")
    (book / "output" / "en" / "page_0001.html").write_text(
        _page_html(
            '<figure class="cover"><img src="../assets/images/page_0001_fig_1.png" '
            'alt="Cover"></figure>'
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["batch_processor.py", "--book", str(book), "--pages", "1", "--threads", "1"],
    )

    assert batch_processor.main() == 0
    assert (book / "output" / "assets" / "images" / "page_0001_fig_1.png").is_file()
    assembled = book / "output" / "book.html"
    assert assembled.is_file()
    assert 'src="assets/images/page_0001_fig_1.png"' in assembled.read_text(encoding="utf-8")
    assert "render, assets, assembly, and validation passed" in capsys.readouterr().out
