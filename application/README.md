# Books HTML CLI

```bash
cd application/backend && pip install -e .

# User drops PDF in books/inbox/
books-cli ingest --pdf books/inbox/my-book.pdf
books-cli ingest --epub books/inbox/my-vietnamese-book.epub
books-cli render --book books/my-book --page 1 --provider cursor --page-pdf
```

EPUB files are converted to an A4 PDF source for the existing visual pipeline.
The EPUB language metadata/content determines the primary output language; a
Vietnamese source renders to `output/vi/` and translates to `output/en/`.

No `library.json`. See [../books/README.md](../books/README.md).
