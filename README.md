# Bilingual Digital Library & Agent Assistant

Trải nghiệm đọc sách song ngữ (Anh - Việt) cao cấp kết hợp với Trợ lý học tập thông minh. Ứng dụng cung cấp các tùy chọn căn chỉnh bố cục linh hoạt và khả năng tương tác trực quan với tài liệu thông qua mô hình ngôn ngữ lớn (LLM).

## Tính năng nổi bật

- 📖 **Đọc sách song ngữ song song**: Hỗ trợ xem riêng tài liệu gốc tiếng Anh (EN), bản dịch tiếng Việt (VI) hoặc xem song ngữ song song (Split View) tiện lợi.
- 📐 **Bố cục linh hoạt**: Cho phép tùy chỉnh vị trí hiển thị các trang tài liệu (Trái - Phải, Trên - Dưới) trực quan và nhanh chóng qua bảng tùy chọn giao diện.
- ⚡ **Tối ưu hóa hiển thị**: Tự động scale trang sách chuẩn kích thước A4 để vừa vặn với không gian đọc; hỗ trợ cuộn dọc độc lập cho từng ngôn ngữ ở chế độ xếp chồng.
- 🤖 **Agent Assistant thông minh**: Trò chuyện, giải thích thuật ngữ chuyên ngành và tóm tắt nội dung từng trang hoặc toàn bộ cuốn sách theo ngữ cảnh thời gian thực.
- 🎯 **Giao diện không làm sao nhãng**: Các nhãn ngôn ngữ (EN, VI) tự động ẩn đi và chỉ hiện lên mượt mà khi bạn di chuột qua các trang sách.

---

## Giao diện ứng dụng

![Bilingual Digital Library & Agent Assistant](screenshot.png)

---

## Hướng dẫn sử dụng

### Bạn làm

1. Copy PDF vào **`books/inbox/`**
2. Yêu cầu Agent xử lý để ingest và render sách.

### Agent làm

```bash
books-cli ingest --pdf books/inbox/<file>.pdf
books-cli render --book books/<slug> --page N --provider cursor --page-pdf
```

Kết quả render sẽ được xuất ra: `books/<slug>/output/en/page_NNNN.html`

Chi tiết cấu trúc sách: [books/README.md](books/README.md) · Agent skill: [.cursor/skills/books-pdf-render/SKILL.md](.cursor/skills/books-pdf-render/SKILL.md)

---

## Cài đặt & Triển khai (Installation & Deployment)

Ứng dụng hỗ trợ cài đặt, cập nhật và gỡ bỏ nhanh trên **Debian/Ubuntu** và **macOS** thông qua một script cài đặt duy nhất.

### 1. Cài đặt nhanh bằng lệnh `curl`

Chạy lệnh sau trên terminal của bạn để tự động cài đặt phiên bản mới nhất từ GitHub Releases:

```bash
curl -fsSL https://raw.githubusercontent.com/thaonv7995/bilingual-reader/main/install.sh | bash
```

* **Cài đặt cấp độ User thường (Khuyên dùng):** Nếu chạy lệnh không dùng `sudo`, ứng dụng sẽ được cài đặt riêng cho User hiện hành tại `~/.local/share/books-studio` và tạo liên kết dòng lệnh tại `~/.local/bin/books-studio`.
* **Cài đặt cấp hệ thống (System-wide):** Nếu chạy với quyền root (`sudo`), ứng dụng sẽ được cài đặt tại `/opt/books-studio` và liên kết dòng lệnh tại `/usr/local/bin/books-studio`.

### 2. Cập nhật phiên bản mới nhất (Update)

Để cập nhật ứng dụng lên phiên bản mới nhất từ GitHub mà **giữ nguyên toàn bộ dữ liệu sách (`books/`)** đã tải lên của bạn, chạy lệnh:

```bash
books-studio --update
```

### 3. Gỡ bỏ ứng dụng (Uninstall)

Để xóa hoàn toàn ứng dụng, dừng các tiến trình đang chạy và dọn dẹp các thư mục liên quan, chạy lệnh:

```bash
books-studio --uninstall
```

---

## Khởi chạy ứng dụng (Running)

Sau khi cài đặt thành công, khởi chạy Web Studio từ bất kỳ thư mục nào bằng lệnh:

```bash
books-studio
```

* Ứng dụng mặc định chạy trên cổng `8765`. Bạn truy cập qua trình duyệt: `http://localhost:8765`.
* Để đổi cổng chạy, sử dụng tham số `--port`, ví dụ: `books-studio --port 9000`.
* **Yêu cầu:** Đảm bảo máy chủ đã cài đặt `agy` CLI (Antigravity CLI).

---

## Cài đặt thủ công từ Source Code (Local Setup)

Nếu bạn clone repository này về máy và muốn thiết lập nhanh môi trường phát triển cục bộ:

```bash
# Cấp quyền thực thi và chạy script setup
chmod +x setup_debian.sh
./setup_debian.sh

# Khởi chạy Web Studio cục bộ
./run_studio.sh
```
