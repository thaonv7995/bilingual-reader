# Data layout

All books: **`books/<slug>/`** at repo root.

```text
books/
  library.json
  <slug>/
    input/original.pdf
    work/page_NNNN/source.pdf
    output/en/page_NNNN.html
    output/assets/
```

Migrate legacy folders:

```bash
books-cli library migrate
```
