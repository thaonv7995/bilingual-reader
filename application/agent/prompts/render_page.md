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
- Always: `assets/book.css`, `assets/page-tokens.css`, `assets/prose-page.css`
- If code/listings: `assets/code-page.css`
- If figures/math: `assets/figures-page.css`

## Rules for Linking Stylesheets, Scripts, and Images (CRITICAL)

To prevent resource loading issues (broken CSS, JS, or images), you MUST follow these constraints:
1. **CSS Stylesheets**:
   - Link ONLY standard stylesheets from the `assets/` directory in the `<head>`: `assets/book.css`, `assets/page-tokens.css`, `assets/prose-page.css`, and optionally `assets/code-page.css` or `assets/figures-page.css` based on page elements.
   - Do NOT reference any other styles, remote web links, or ad-hoc custom CSS files.
2. **Javascript (JS) Scripts**:
   - Do NOT include any `<script>` tags, third-party trackers, or custom scripting unless it is a standard template requirement.
3. **Images & Figure Assets**:
   - Every `<img>` tag MUST point to a valid relative path starting with `assets/images/` (e.g., `src="assets/images/page_NNNN_fig_X.png"`).
   - Before writing the HTML, check the contents of `output/assets/images/` to see if a cropped image already exists for this page (e.g., `page_0016_fig_1.png` for page 16). Use its exact filename in the `src` attribute.
   - Do NOT append random junk characters or duplicate extensions to the image source (e.g. `page_0016_fig_1.png123` or `page_0016_fig_1.png.png`).
   - If no image has been cropped yet, use the expected standard naming pattern (e.g., `assets/images/page_NNNN_fig_1.png`) inside a proper `<figure>` block, so the automated figure extraction script can place it later.

## Shell

`body.book-standalone` → `main.book-page.book-page--sheet` → `article.sheet-flow.prose-page`

## Crucial Quality Rule: Fit Exactly One A4 Sheet (No Overflow)

Every page HTML must fit onto exactly one A4 sheet without vertical or horizontal overflow or scrollbars.
If the PDF page is very dense (contains many text paragraphs, list items, dialogue blocks, or exercises), you MUST:
- Reduce the padding of `.prose-page` (e.g., `8mm var(--book-margin-x) 10mm !important` or down to `5mm` if extremely dense).
- Reduce vertical margins between sections/blocks (e.g., `.exercise-block { margin-bottom: 3mm; }`).
- Reduce font-size of list items or body text slightly (e.g., down to `9.5pt` or `9pt` for dense exercises) and tighten line-height (e.g., `1.3` to `1.35`) and item margins (e.g., `1.5mm` down to `0.8mm`).
- Minimize headings size and margins.

## Efficiency & Speed Directives (CRITICAL)

To avoid timing out, DO NOT perform redundant exploratory tool calls:
- Do NOT read the stylesheets (`book.css`, `prose-page.css`, etc.) repeatedly. They are already standard.
- Do NOT read other pages' HTML files for boilerplate.
- Do NOT perform manual figures/images searches if no figures are present in the PDF text.
- Render the `source.pdf` to image, extract text, and write the output HTML immediately in 3-5 steps.
- **CRITICAL**: Do NOT render, extract, or view other PDF pages (like checking TOC page numbers on page 10, 15, etc.). You must focus ONLY on page N.
- **CRITICAL**: Do NOT write custom Python scripts or run pixel-level crop analysis for logos/images unless explicitly instructed. If there are no images in the PDF text, just write standard text HTML.
- **CRITICAL**: Do NOT run broad grep searches on completed books or check other directories.
- **CRITICAL**: Always write the output HTML file with `IsArtifact: false` (i.e. do NOT set `IsArtifact: true` as it is forbidden and will fail because the output directory is outside the CLI brain).

## After you write HTML

DO NOT run any post-render scripts (such as `extract_pdf_figures.py`, `upgrade_figure_html.py`, `fix_book_layout.py`, or `validate_page_fidelity.py`) yourself. These scripts are run automatically by the main orchestrator after you finish. Running them yourself as background tasks will cause your process to exit early and fail. Simply write the completed HTML file and finish.

## Self-Verification Steps (CRITICAL)

After writing the HTML file, you MUST perform a self-verification pass using your file tools to ensure all resources load successfully:
1. **Verify CSS Stylesheets**: Find every stylesheet link (e.g. `assets/book.css`) in your written HTML. Verify that these files actually exist on disk in the corresponding `output/assets/` directory.
2. **Verify Images & Figures**: For every `<img>` tag you wrote, resolve its relative path (e.g. `assets/images/page_NNNN_fig_X.png`) and verify that the target image file exists on disk. If the image is not present yet but is required by the page layout, make sure the reference is clean and structured under a proper `<figure>` container so the pipeline can extract it later.
3. **Verify Javascript**: Ensure no unexpected scripts or external links are present.
4. **Immediate Fix**: If any file path is incorrect, broken (404), has unencoded spaces, or is missing, modify your HTML to fix the path before completing your work.

## Done when

Side-by-side with `source.pdf`: correct **order**, **block types**, **chrome**, **listings**, **figures**, **math**; page N only. Must fit onto exactly one A4 page without clipping or overflow.


