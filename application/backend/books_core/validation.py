"""HTML and process status validation."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


class ArtifactValidationError(ValueError):
    """Raised when a pipeline artifact is structurally invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ArtifactValidationError(message)


def validate_process_status(data: dict[str, Any], *, page: int | None = None) -> None:
    _require(isinstance(data, dict), "process.status must be a JSON object")
    if page is not None:
        _require(int(data.get("page", page)) == page, "process.status page mismatch")
    _require(
        data.get("state") in {"idle", "queued", "running", "done", "failed", "cancelled"},
        "invalid process state",
    )
    _require(bool(data.get("step")), "process.status missing step")


_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
_NON_CONTENT_TAGS = {"script", "style", "template", "noscript"}
_PAGE_CHROME_CLASSES = {"running-head", "book-footer", "page-nav"}


def _inline_style_is_hidden(style: str) -> bool:
    compact = re.sub(r"\s+", "", style).lower()
    return (
        "display:none" in compact
        or "visibility:hidden" in compact
        or bool(re.search(r"(?:^|;)opacity:0(?:\.0+)?(?:;|$)", compact))
    )


class _ArticleContentProbe(HTMLParser):
    """Find actual page content while excluding head metadata and page chrome."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool, bool]] = []
        self.article_found = False
        self.intentional_blank = False
        self.meaningful_text = False
        self.meaningful_visual = False

    @property
    def has_meaningful_content(self) -> bool:
        return self.meaningful_text or self.meaningful_visual or self.intentional_blank

    def _start(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> bool:
        tag = tag.lower()
        attrs = {str(key).lower(): value or "" for key, value in attrs_list}
        parent_in_article = self.stack[-1][1] if self.stack else False
        parent_hidden = self.stack[-1][2] if self.stack else False
        in_article = parent_in_article or tag == "article"

        classes = set(attrs.get("class", "").lower().split())
        hidden = (
            parent_hidden
            or tag in _NON_CONTENT_TAGS
            or "hidden" in attrs
            or attrs.get("aria-hidden", "").lower() == "true"
            or bool(classes & _PAGE_CHROME_CLASSES)
            or _inline_style_is_hidden(attrs.get("style", ""))
        )

        if tag == "article":
            self.article_found = True
            blank_marker = (
                attrs.get("data-intentionally-blank", "")
                or attrs.get("data-blank-page", "")
            ).lower()
            if blank_marker in {"1", "true", "yes"}:
                self.intentional_blank = True

        if in_article and not hidden and tag != "article":
            if attrs.get("data-visual-id"):
                self.meaningful_visual = True
            elif tag == "img" and (attrs.get("src") or attrs.get("srcset")):
                self.meaningful_visual = True
            elif tag in {"svg", "canvas", "math"}:
                self.meaningful_visual = True
            elif tag in {"video", "audio"} and (
                attrs.get("src") or attrs.get("poster")
            ):
                self.meaningful_visual = True
            elif tag in {"object", "embed", "iframe"} and (
                attrs.get("data") or attrs.get("src")
            ):
                self.meaningful_visual = True
            elif tag == "hr":
                self.meaningful_visual = True
            elif tag == "input" and attrs.get("type", "text").lower() != "hidden":
                self.meaningful_visual = True
            elif "url(" in attrs.get("style", "").lower():
                self.meaningful_visual = True

        if tag not in _VOID_TAGS:
            self.stack.append((tag, in_article, hidden))
            return True
        return False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        pushed = self._start(tag, attrs)
        if pushed:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if not self.stack:
            return
        _tag, in_article, hidden = self.stack[-1]
        if in_article and not hidden and any(character.isalnum() for character in data):
            self.meaningful_text = True


def validate_draft_html(text: str) -> None:
    lowered = text.lower()
    _require("<main" in lowered and "book-page" in lowered, "HTML missing A4 book-page shell")
    _require("<article" in lowered, "HTML missing semantic article")
    _require("pdf-render" not in lowered, "HTML includes forbidden pdf-render marker")

    probe = _ArticleContentProbe()
    probe.feed(text)
    _require(probe.article_found, "HTML missing semantic article")
    _require(
        probe.has_meaningful_content,
        "HTML article has no meaningful visible content (blank page shell)",
    )


def draft_html_file_valid(path: Path) -> bool:
    """Return whether a page HTML file is non-empty and passes the content contract."""
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        validate_draft_html(path.read_text(encoding="utf-8"))
        return True
    except (OSError, UnicodeError, ArtifactValidationError):
        return False
