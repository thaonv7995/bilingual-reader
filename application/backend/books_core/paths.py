"""Book workspace path helpers — input / work / output layout."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BookPaths:
    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root).expanduser().resolve())

    @classmethod
    def open(cls, book_dir: str | Path) -> BookPaths:
        root = Path(book_dir).expanduser().resolve()
        if not root.is_dir():
            from books_core.repo import books_dir as get_books_dir
            try:
                slug_dir = get_books_dir() / str(book_dir)
                if slug_dir.is_dir():
                    root = slug_dir
                else:
                    raise NotADirectoryError(root)
            except Exception:
                raise NotADirectoryError(root)
        return cls(root)

    # --- Top-level zones ---

    @property
    def input_dir(self) -> Path:
        return self.root / "input"

    @property
    def work(self) -> Path:
        return self.root / "work"

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    @property
    def book_json(self) -> Path:
        return self.root / "book.json"

    @property
    def index_html(self) -> Path:
        return self.output_dir / "index.html"

    # --- Input (user-provided, immutable) ---

    @property
    def source_pdf(self) -> Path:
        """Canonical: input/original.pdf. Falls back to legacy source/original.pdf."""
        preferred = self.input_dir / "original.pdf"
        if preferred.is_file():
            return preferred
        legacy = self.root / "source" / "original.pdf"
        if legacy.is_file():
            return legacy
        return preferred

    # --- Output (deliverables) ---

    @property
    def assets(self) -> Path:
        preferred = self.output_dir / "assets"
        if preferred.is_dir() or not (self.root / "assets").is_dir():
            return preferred
        return self.root / "assets"

    def pages_dir(self, lang: str | None = None) -> Path:
        lang = lang or "en"
        preferred = self.output_dir / lang
        legacy = self.root / "pages" / lang
        if legacy.is_dir() and not preferred.is_dir():
            return legacy
        return preferred

    def page_lang_html(self, page: int, lang: str = "en") -> Path:
        return self.pages_dir(lang) / f"page_{page:04d}.html"

    # --- Work (generated intermediate, safe to delete) ---

    def page_work(self, page: int) -> Path:
        return self.work / f"page_{page:04d}"

    def source_page_pdf(self, page: int) -> Path:
        return self.page_work(page) / "source.pdf"

    def agent_dir(self, page: int) -> Path:
        return self.page_work(page) / "agent"

    def final_html(self, page: int, lang: str = "en") -> Path:
        return self.page_work(page) / f"final.{lang}.html"

    # --- Book metadata ---

    def load_book_json(self) -> dict[str, Any]:
        if not self.book_json.is_file():
            return {
                "slug": self.root.name,
                "source_lang": "en",
                "languages": [{"code": "en", "role": "primary"}],
                "page_count": 0,
                "layout": {
                    "input": "input/original.pdf",
                    "work": "work",
                    "output": "output",
                },
            }
        return json.loads(self.book_json.read_text(encoding="utf-8"))

    def _infer_page_count(self) -> int:
        if self.source_pdf.is_file():
            try:
                import fitz

                with fitz.open(self.source_pdf) as doc:
                    return doc.page_count
            except Exception:
                pass
        html_pages = list(self.pages_dir().glob("page_*.html"))
        if html_pages:
            return max(int(p.stem.split("_")[1]) for p in html_pages)
        work_dirs = list(self.work.glob("page_*"))
        if work_dirs:
            return max(int(p.name.split("_")[1]) for p in work_dirs)
        return 0

    def estimate_page_count(self) -> int:
        if self.book_json.is_file():
            data = json.loads(self.book_json.read_text(encoding="utf-8"))
            if n := data.get("page_count"):
                return int(n)
        return self._infer_page_count()

    def default_lang(self) -> str:
        book = self.load_book_json()
        return str(book.get("source_lang") or "en")

    def ensure_book_dirs(self) -> None:
        """Create input / work / output zones (no page folders)."""
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.work.mkdir(parents=True, exist_ok=True)
        assets = self.output_dir / "assets"
        (assets / "images").mkdir(parents=True, exist_ok=True)
        self.pages_dir().mkdir(parents=True, exist_ok=True)

        # Automatically populate standard CSS templates if missing or empty
        try:
            tpl_dir = Path(__file__).parent / "templates"
            
            css_files = [
                (tpl_dir / "book.css", assets / "book.css"),
                (tpl_dir / "page-tokens.css", assets / "page-tokens.css"),
                (tpl_dir / "prose-page.css", assets / "prose-page.css"),
                (tpl_dir / "toc-page.css", assets / "toc-page.css"),
                (tpl_dir / "code-page.css", assets / "code-page.css"),
                (tpl_dir / "figures-page.css", assets / "figures-page.css"),
            ]
            for src, dest in css_files:
                if src.is_file():
                    if not dest.is_file() or dest.stat().st_size == 0:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dest)
        except Exception:
            pass

    def ensure_work_page(self, page: int) -> Path:
        d = self.page_work(page)
        d.mkdir(parents=True, exist_ok=True)
        return d


def normalize_book_layout(book_dir: Path) -> dict[str, Any]:
    """
    Move legacy flat layout into input/work/output.
    Safe to run multiple times.
    """
    book_dir = book_dir.resolve()
    book = BookPaths.open(book_dir)
    moved: list[str] = []

    legacy_pdf = book_dir / "source" / "original.pdf"
    target_pdf = book.input_dir / "original.pdf"
    if legacy_pdf.is_file() and not target_pdf.is_file():
        book.input_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_pdf), str(target_pdf))
        moved.append("source/original.pdf → input/original.pdf")

    legacy_assets = book_dir / "assets"
    target_assets = book.output_dir / "assets"
    if legacy_assets.is_dir() and legacy_assets != target_assets:
        target_assets.parent.mkdir(parents=True, exist_ok=True)
        if not target_assets.exists():
            shutil.move(str(legacy_assets), str(target_assets))
            moved.append("assets/ → output/assets/")
        else:
            for item in legacy_assets.iterdir():
                dest = target_assets / item.name
                if not dest.exists():
                    shutil.move(str(item), str(dest))
            if not any(legacy_assets.iterdir()):
                legacy_assets.rmdir()
                moved.append("assets/* → output/assets/")

    legacy_pages = book_dir / "pages"
    if legacy_pages.is_dir():
        for lang_dir in legacy_pages.iterdir():
            if not lang_dir.is_dir():
                continue
            dest_lang = book.output_dir / lang_dir.name
            dest_lang.mkdir(parents=True, exist_ok=True)
            for html in lang_dir.glob("*.html"):
                dest = dest_lang / html.name
                if not dest.is_file():
                    shutil.move(str(html), str(dest))
                    moved.append(f"{html.relative_to(book_dir)} → output/{lang_dir.name}/")
        if not any(legacy_pages.rglob("*")):
            shutil.rmtree(legacy_pages, ignore_errors=True)

    legacy_index = book_dir / "index.html"
    if legacy_index.is_file() and not book.index_html.is_file():
        book.output_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_index), str(book.index_html))
        moved.append("index.html → output/index.html")

    for junk in ("meta", "analysis", "qa", "translation", "templates"):
        junk_dir = book_dir / junk
        if junk_dir.is_dir() and not any(junk_dir.rglob("*")):
            shutil.rmtree(junk_dir, ignore_errors=True)

    empty_source = book_dir / "source"
    if empty_source.is_dir() and not any(empty_source.iterdir()):
        empty_source.rmdir()

    return {"ok": True, "book": str(book_dir), "moved": moved}
