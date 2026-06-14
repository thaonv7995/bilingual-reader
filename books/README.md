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
---

## Quy trình chuẩn: Batch Process sử dụng Hệ thống Authen (Không dùng API Key)

Để đảm bảo tuân thủ bảo mật và sử dụng đúng hạ tầng, **không được sử dụng API Key trực tiếp dưới bất kỳ hình thức nào**. Mọi tiến trình render và dịch thuật phải chạy thông qua CLI `agy` của hệ thống (sử dụng cơ chế OAuth/Authentication có sẵn).

Để xử lý sách một cách tối ưu và song song (EN + VI):

```bash
# Thiết lập model sử dụng (khuyên dùng gemini-3.5-flash)
export ANTIGRAVITY_MODEL="gemini-3.5-flash"

# Chạy batch processor (sử dụng agy CLI với authen hệ thống)
application/.venv/bin/python application/backend/scripts/batch_processor.py --book books/my-book --translate --threads 4
```

Lệnh trên tự động:
1. Gọi CLI `agy` song song bằng nhiều luồng (threads) để render các trang tiếng Anh.
2. Dịch các trang sang tiếng Việt thông qua CLI `agy` (với model cấu hình qua `ANTIGRAVITY_MODEL`).
3. Tự động chạy toàn bộ pipeline post-render (extract figures, upgrade layout, fix margins, v.v.).
4. Tự động assemble thành `book.html` và `book.vi.html`.
---

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

---

## Hướng dẫn nén và tải lên máy chủ (BKB Packaging & Upload)

Khi Agent đã hoàn thành quá trình xử lý sách (ingest, render, post-render, assemble), bạn cần nén sách thành định dạng lưu trữ `.bkb` (ZIP nén) để có thể tải lên hệ thống qua Admin Portal hoặc API.

### Bước 1: Nén thư mục sách thành tệp `.bkb`
Sử dụng công cụ dòng lệnh `books-cli pack` có sẵn trong môi trường ảo của dự án:

```bash
application/.venv/bin/books-cli pack --book books/tên-thư-mục-sách --output books/tên-sách.bkb
```

*Ví dụ:*
```bash
application/.venv/bin/books-cli pack --book books/animal-farm-by-george-orwell --output books/animal-farm.bkb
```

### Bước 2: Tải lên máy chủ qua Web Admin Portal
1. Truy cập trang quản trị của hệ thống tại địa chỉ: `http://localhost:27099/admin` (hoặc nhấn nút **Admin Site** từ thanh công cụ khi đăng nhập tài khoản admin).
2. Chọn tab **Sách** (Books).
3. Sử dụng khung kéo thả tệp hoặc nhấn nút duyệt để chọn tệp `tên-sách.bkb` đã tạo ở bước 1.
4. Quá trình tải lên và giải nén (unpack) sẽ diễn ra hoàn toàn tự động trên máy chủ, đi kèm với thanh tiến trình tải lên trực quan. Sau khi tải lên thành công, sách sẽ hiển thị trong tủ sách của thư viện.

