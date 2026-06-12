# Books

## Bạn chỉ cần

**Copy PDF vào `books/inbox/`** — ví dụ `books/inbox/my-book.pdf`

Sau đó bảo Agent: *"process book"* hoặc *"convert trang 1-5"*.

Agent tự (theo **`application/agent/FIDELITY-RULES.md`**):
1. `books-cli ingest` → tạo `books/my-book/` + `page_chrome` trong `book.json`
2. `page-pdf` + `render` từng trang → **1 HTML / trang**
3. **Post-render** (bắt buộc): extract figures → fix layout → validate fidelity
4. `assemble` → gộp thành **1 file sách** `output/book.html`

**Output từng trang:** `books/my-book/output/en/page_0001.html`, `page_0002.html`, …

**Output cả sách:** `books/my-book/output/book.html`

Không cần file JSON. Không cần cấu hình.

---

## Cấu trúc (agent tạo tự động)

```text
books/
  inbox/              ← BẠN COPY PDF VÀO ĐÂY
    my-book.pdf
  my-book/            ← agent tạo sau ingest
    input/original.pdf
    work/             ← trung gian (xóa được)
    output/
      en/page_*.html  ← 1 HTML mỗi trang (kết quả render)
      book.html       ← gộp tất cả trang (sau assemble)
```

## Lệnh assemble

```bash
application/.venv/bin/books-cli assemble --book books/my-book
```

Chỉ chạy sau khi đã có `output/en/page_*.html` và `validate_page_fidelity.py` pass.

## Post-render (mọi sách)

```bash
BOOK=books/my-book
PY=application/.venv/bin/python3

$PY application/backend/scripts/extract_pdf_figures.py "$BOOK"
$PY application/backend/scripts/upgrade_figure_html.py "$BOOK"
$PY application/backend/scripts/refresh_figure_images.py "$BOOK"
$PY application/backend/scripts/fix_book_layout.py "$BOOK"
$PY application/backend/scripts/validate_page_fidelity.py "$BOOK" --lang all
books-cli assemble --book "$BOOK" --lang en --output book.html
$PY application/backend/scripts/validate_page_fidelity.py "$BOOK" --lang all
```

Chi tiết: **`application/agent/FIDELITY-RULES.md`** (Rule 8–10: assemble, asset paths, images).
