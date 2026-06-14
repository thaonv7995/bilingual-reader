---
name: books-new-book-setup
description: Optional — prefer books/inbox/ + books-cli ingest. Agent usually does not need this skill.
---

# Setup (optional)

User thường chỉ copy PDF vào **`books/inbox/`** — Agent dùng `books-cli ingest`.

Chỉ dùng skill này nếu cần scaffold tay:

```bash
python3 .cursor/skills/books-new-book-setup/scripts/setup_book.py \
  --pdf books/inbox/my-book.pdf --slug my-book
```

Hoặc:

```bash
books-cli ingest --pdf books/inbox/my-book.pdf
```
