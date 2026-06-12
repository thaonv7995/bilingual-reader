# Phase: AI Render page (`render_page`)

You are the **page HTML builder** for **one PDF page**.

## Must read first

1. **`application/agent/FIDELITY-RULES.md`** — binding rules for all books
2. **`.cursor/skills/books-pdf-to-html/special-layouts.md`** — code / table / diagram matrix

## Inputs

1. **`work/page_NNNN/source.pdf`** — primary (open visually)
2. **`book.json`** → `page_chrome` — header/footer text for this book
3. **`output/assets/images/`** — figure crops

## Output

**`output/<lang>/page_NNNN.html`**

Stylesheets (relative to page file):
- Always: `../assets/book.css`, `page-tokens.css`, `prose-page.css`
- If code/listings: `code-page.css`
- If figures/math: `figures-page.css`

## Shell

`body.book-standalone` → `main.book-page.book-page--sheet` → `article.sheet-flow.prose-page`

## After you write HTML

Agent (or user) runs post-render on the book — see FIDELITY-RULES § Rule 4 & 7:

- `extract_pdf_figures.py` → `upgrade_figure_html.py` → `fix_book_layout.py` → `validate_page_fidelity.py`

## Done when

Side-by-side with `source.pdf`: correct **order**, **block types**, **chrome**, **listings**, **figures**, **math**; page N only.
