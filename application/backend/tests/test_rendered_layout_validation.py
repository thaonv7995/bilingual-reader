from __future__ import annotations

import pytest

from books_core.rendered_layout import (
    A4_HEIGHT_296_PX,
    A4_WIDTH_PX,
    issues_from_layout_metrics,
)


def _metrics(**overrides):
    metrics = {
        "sheetCount": 1,
        "shell": {"width": A4_WIDTH_PX, "height": A4_HEIGHT_296_PX},
        "bounds": {"left": 0, "right": 0, "top": 0, "bottom": 0},
        "offenders": {"left": "", "right": "", "top": "", "bottom": ""},
        "clipped": [],
    }
    metrics.update(overrides)
    return metrics


def test_a4_page_without_overflow_passes() -> None:
    assert issues_from_layout_metrics(_metrics()) == []


def test_wrong_shell_and_visible_overflow_are_reported() -> None:
    issues = issues_from_layout_metrics(
        _metrics(
            shell={"width": 820, "height": 900},
            bounds={"left": 0, "right": 24, "top": 0, "bottom": 37},
            offenders={"left": "", "right": "pre.code-block", "top": "", "bottom": "footer"},
        )
    )

    assert any("rendered page width" in issue for issue in issues)
    assert any("rendered page height" in issue for issue in issues)
    assert "horizontal overflow by 24.0px near pre.code-block" in issues
    assert "vertical overflow by 37.0px near footer" in issues


def test_clipped_text_is_reported_but_small_rounding_is_tolerated() -> None:
    issues = issues_from_layout_metrics(
        _metrics(
            bounds={"left": 0, "right": 4, "top": 0, "bottom": 4},
            clipped=[
                {"selector": "article.sheet-flow", "x": 3, "y": 26},
                {"selector": "pre.code-block", "x": 18, "y": 0},
            ],
        )
    )

    assert "clipped text/content overflow in article.sheet-flow: 26.0px vertically" in issues
    assert "clipped text/content overflow in pre.code-block: 18.0px horizontally" in issues
    assert not any(issue.startswith("horizontal overflow") for issue in issues)


def test_en_ipa_exception_skips_only_vertical_constraints() -> None:
    issues = issues_from_layout_metrics(
        _metrics(
            shell={"width": A4_WIDTH_PX, "height": 1600},
            bounds={"left": 0, "right": 12, "top": 0, "bottom": 400},
            offenders={"left": "", "right": "p", "top": "", "bottom": "article"},
            clipped=[{"selector": "article", "x": 0, "y": 100}],
        ),
        allow_vertical_overflow=True,
    )

    assert issues == ["horizontal overflow by 12.0px near p"]


@pytest.mark.parametrize("sheet_count", [0, 2])
def test_exactly_one_a4_sheet_is_required(sheet_count: int) -> None:
    assert issues_from_layout_metrics({"sheetCount": sheet_count}) == [
        f"rendered page must contain exactly one A4 sheet (found {sheet_count})"
    ]
