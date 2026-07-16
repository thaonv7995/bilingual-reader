from __future__ import annotations

from books_core.repair_report import (
    clear_repair_report,
    parse_validation_failures,
    read_repair_report,
    repair_report_path,
    write_repair_report,
)
from scripts import validate_page_fidelity as fidelity_validator
from scripts.validate_page_fidelity import main as validate_main


VALIDATION_OUTPUT = """
FAIL en/page_0013.html: HTML article has no meaningful visible content (blank page shell)
FAIL en/page_0106.html: Missing image: '../assets/images/page_0106_fig_1.png'
FAIL en/page_0122.html: Missing image: '../assets/images/page_0122_fig_1.png'
FAIL vi/page_0013.html: HTML article has no meaningful visible content (blank page shell)
FAIL vi/page_0106.html: Missing image: '../assets/images/page_0106_fig_1.png'
FAIL vi/page_0122.html: Missing image: '../assets/images/page_0122_fig_1.png'

6 issue(s) — see application/agent/FIDELITY-RULES.md
"""


def test_parse_validation_failures_deduplicates_languages_by_page() -> None:
    report = parse_validation_failures(VALIDATION_OUTPUT)

    assert report["pages"] == [
        {"page": 13, "categories": ["blank_content"]},
        {"page": 106, "categories": ["missing_asset"]},
        {"page": 122, "categories": ["missing_asset"]},
    ]
    assert len(report["issues"]) == 6


def test_repair_report_persists_until_validation_succeeds(tmp_path) -> None:
    written = write_repair_report(tmp_path, VALIDATION_OUTPUT, stage="post-render")

    assert written is not None
    assert repair_report_path(tmp_path).is_file()
    assert read_repair_report(tmp_path)["stage"] == "post-render"

    clear_repair_report(tmp_path)
    assert read_repair_report(tmp_path) is None


def test_non_page_validation_failure_does_not_create_report(tmp_path) -> None:
    assert write_repair_report(tmp_path, "FAIL No pages found or processed.", stage="post-render") is None
    assert not repair_report_path(tmp_path).exists()


def test_extractor_failure_is_recorded_for_targeted_page_repair(tmp_path) -> None:
    output = (
        "FAIL extractor did not create referenced figure: page 0154: "
        "output/assets/images/page_0154_fig_1.png"
    )

    report = write_repair_report(tmp_path, output, stage="post-render:extract_pdf_figures.py")

    assert report is not None
    assert report["pages"] == [{"page": 154, "categories": ["missing_asset"]}]
    assert report["issues"] == [
        {
            "page": 154,
            "lang": "all",
            "category": "missing_asset",
            "message": (
                "Extractor did not create referenced figure: "
                "output/assets/images/page_0154_fig_1.png"
            ),
        }
    ]


def test_validator_writes_and_clears_repair_report(tmp_path) -> None:
    pages = tmp_path / "output" / "en"
    pages.mkdir(parents=True)
    page = pages / "page_0001.html"
    page.write_text(
        '<main class="book-page book-page--sheet"><article>'
        '<img src="../assets/images/page_0001_fig_1.png">'
        '</article></main>',
        encoding="utf-8",
    )

    args = [
        "validate_page_fidelity.py",
        str(tmp_path),
        "--lang",
        "all",
        "--pages-only",
        "--skip-rendered-layout",
    ]
    assert validate_main(args) == 1
    report = read_repair_report(tmp_path)
    assert report["pages"] == [{"page": 1, "categories": ["missing_asset"]}]

    image = tmp_path / "output" / "assets" / "images" / "page_0001_fig_1.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"not-empty")

    assert validate_main(args) == 0
    assert read_repair_report(tmp_path) is None


def test_rendered_overflow_is_classified_for_targeted_repair() -> None:
    output = (
        "FAIL vi/page_0044.html: vertical overflow by 38.0px "
        "near article.sheet-flow.prose-page"
    )

    report = parse_validation_failures(output)

    assert report["pages"] == [{"page": 44, "categories": ["layout_overflow"]}]
    assert report["issues"][0]["category"] == "layout_overflow"


def test_validator_persists_browser_geometry_failure(
    tmp_path,
    monkeypatch,
) -> None:
    pages = tmp_path / "output" / "en"
    pages.mkdir(parents=True)
    page = pages / "page_0007.html"
    page.write_text(
        '<main class="book-page book-page--sheet">'
        '<article class="sheet-flow prose-page"><p>Visible content.</p></article>'
        '</main>',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        fidelity_validator,
        "validate_rendered_pages",
        lambda paths: {page.resolve(): ["vertical overflow by 42.0px near article.sheet-flow"]},
    )

    assert validate_main([
        "validate_page_fidelity.py",
        str(tmp_path),
        "--lang",
        "all",
        "--pages-only",
    ]) == 1
    report = read_repair_report(tmp_path)
    assert report["pages"] == [{"page": 7, "categories": ["layout_overflow"]}]
