---
name: books-pdf-render
description: User drops PDF in books/inbox/ — agent ingests and converts each page to HTML. No library.json.
---

# Agent: PDF → HTML

## Must read (every book)

| Doc | Purpose |
|-----|---------|
| **`application/agent/FIDELITY-RULES.md`** | Content order, chrome, headings, figures, code, math |
| **`special-layouts.md`** | Which HTML/CSS for each block type |
| **`.cursor/rules/books-page-fidelity.mdc`** | Cursor rule when editing pages |

---

## User làm gì

Copy PDF vào `books/inbox/<tên-sách>.pdf` → *"process book"*.

---

## Pipeline (đúng thứ tự)

### 1. Ingest

```bash
books-cli ingest --pdf books/inbox/<file>.pdf
```

Tạo `books/<slug>/` + `book.json`. Sau ingest, đảm bảo `page_chrome` có trong `book.json` (tự detect từ PDF trang 1 hoặc set tay).

### 2. Page PDF

```bash
books-cli page-pdf --book books/<slug> --pages 1-N
```

### 3. Render từng trang

Đọc **`FIDELITY-RULES.md`** trước khi viết HTML. Mở `source.pdf` **bằng mắt**, không chỉ text extract.

```bash
books-cli render --book books/<slug> --page N --provider cursor
```

### 4. Post-render (bắt buộc — mọi sách, mọi ngôn ngữ)

Xem **`application/agent/FIDELITY-RULES.md` Rule 10**.

```bash
BOOK=books/<slug>
PY=application/.venv/bin/python3

$PY application/backend/scripts/extract_pdf_figures.py "$BOOK"
$PY application/backend/scripts/upgrade_figure_html.py "$BOOK"
$PY application/backend/scripts/refresh_figure_images.py "$BOOK"
$PY application/backend/scripts/fix_book_layout.py "$BOOK"
$PY application/backend/scripts/validate_page_fidelity.py "$BOOK" --lang all
```

### 5. Assemble + validate lại

```bash
books-cli assemble --book "$BOOK" --lang en --output book.html
books-cli assemble --book "$BOOK" --lang vi --output book.vi.html   # sau translate
$PY application/backend/scripts/validate_page_fidelity.py "$BOOK" --lang all
```

**Output:** `output/book.html`, `output/book.vi.html` — cùng format A4 như từng trang; ảnh dùng `assets/` không `../assets/`.

---

## Cấu trúc

```text
books/<slug>/
  book.json              ← page_chrome, page_count
  input/original.pdf
  work/page_NNNN/source.pdf
  output/en/page_NNNN.html
  output/assets/         ← book.css, prose-page.css, code-page.css, figures-page.css, images/
  output/book.html
```

---

## Checklist nhanh (mỗi trang)

- [ ] Block order = PDF visual order
- [ ] Listing đặt đúng chỗ (sau "See Listing N")
- [ ] Run-in `Title.` không phải `<h3>` uppercase
- [ ] Diagram = PNG crop hoặc SVG chất lượng (không ascii-figure)
- [ ] `page_chrome` đúng header/footer
- [ ] `validate_page_fidelity.py` pass
