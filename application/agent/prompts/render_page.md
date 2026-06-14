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

## Crucial Quality Rule: Fit Exactly One A4 Sheet (No Overflow)

Every page HTML must fit onto exactly one A4 sheet without vertical or horizontal overflow or scrollbars.
If the PDF page is very dense (contains many text paragraphs, list items, dialogue blocks, or exercises), you MUST:
- Reduce the padding of `.prose-page` (e.g., `8mm var(--book-margin-x) 10mm !important` or down to `5mm` if extremely dense).
- Reduce vertical margins between sections/blocks (e.g., `.exercise-block { margin-bottom: 3mm; }`).
- Reduce font-size of list items or body text slightly (e.g., down to `9.5pt` or `9pt` for dense exercises) and tighten line-height (e.g., `1.3` to `1.35`) and item margins (e.g., `1.5mm` down to `0.8mm`).
- Minimize headings size and margins.

## After you write HTML

Agent (or user) runs post-render on the book — see FIDELITY-RULES § Rule 4 & 7:

- `extract_pdf_figures.py` → `upgrade_figure_html.py` → `fix_book_layout.py` → `validate_page_fidelity.py`

## Done when

Side-by-side with `source.pdf`: correct **order**, **block types**, **chrome**, **listings**, **figures**, **math**; page N only. Must fit onto exactly one A4 page without clipping or overflow.

