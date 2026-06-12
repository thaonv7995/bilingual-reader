# Books HTML CLI

```bash
cd application/backend && pip install -e .

# User drops PDF in books/inbox/
books-cli ingest --pdf books/inbox/my-book.pdf
books-cli render --book books/my-book --page 1 --provider cursor --page-pdf
```

No `library.json`. See [../books/README.md](../books/README.md).
