# Phase: AI Render page (`render_page`)

You are the **page HTML builder** for **one PDF page**.

## Must read first

1. **`application/agent/FIDELITY-RULES.md`** — binding rules for all books
2. **`.cursor/skills/books-pdf-to-html/special-layouts.md`** — code / table / diagram matrix

## Inputs

1. **`work/page_NNNN/source.pdf`** — primary (open visually)
2. **`work/page_NNNN/source.png`** — complete rendered page; open this first, especially for scanned PDFs
3. **`work/page_NNNN/visual-diagnosis.json`** — finalized plan produced by the vision agent
4. **`book.json`** → `page_chrome` — header/footer text for this book
5. **`output/assets/images/`** — raster figure crops

The PDF can be a scanned/image-only page with no extractable text. Empty text extraction never means the page is blank: inspect `source.png` and reproduce every visible content block. Never write an empty `<article>` for a source page that contains visible content. For a genuinely blank source page only, mark the article explicitly with `data-intentionally-blank="true"`.

## Output

**`output/<lang>/page_NNNN.html`**

Stylesheets (relative to page file):
- Always: `../assets/book.css`, `../assets/page-tokens.css`, `../assets/prose-page.css`
- If code/listings: `../assets/code-page.css`
- If figures/math: `../assets/figures-page.css`

## Rules for Linking Stylesheets, Scripts, and Images (CRITICAL)

To prevent resource loading issues (broken CSS, JS, or images), you MUST follow these constraints:
1. **CSS Stylesheets**:
   - Link ONLY standard stylesheets from the `../assets/` directory in the `<head>`: `../assets/book.css`, `../assets/page-tokens.css`, `../assets/prose-page.css`, and optionally `../assets/code-page.css` or `../assets/figures-page.css` based on page elements.
   - Do NOT reference any other styles, remote web links, or ad-hoc custom CSS files.
2. **Javascript (JS) Scripts**:
   - Do NOT include any `<script>` tags, third-party trackers, or custom scripting unless it is a standard template requirement.
3. **Images & Figure Assets**:
   - Every `<img>` tag MUST point to a valid relative path starting with `../assets/images/` (e.g., `src="../assets/images/page_NNNN_fig_X.png"`).
   - Before writing the HTML, check the contents of `output/assets/images/` to see if a cropped image already exists for this page. If you find `page_0016_fig_1.png`, you MUST include the prefix: `src="../assets/images/page_0016_fig_1.png"`.
   - Do NOT append random junk characters or duplicate extensions to the image source (e.g. `../assets/images/page_0016_fig_1.png123` or `../assets/images/page_0016_fig_1.png.png`).
   - If no image has been cropped yet, use the expected standard naming pattern (e.g., `../assets/images/page_NNNN_fig_1.png`) only for a real figure, diagram, or first-page cover visible in `source.pdf`; keep it inside a proper `<figure>` block so the automated extractor can place it later.
   - Never invent an `<img>` placeholder for decorative text, whitespace, or content that has no corresponding visual region in `source.pdf`.

## Figure strategy (CRITICAL)

Read the finalized agent-vision plan at `work/page_NNNN/visual-diagnosis.json` before building figures and follow its id, bbox, caption, and strategy for each figure. Do not independently invent a second visual interpretation:

- **`reconstruct-html-svg`**: redraw the visual using semantic HTML/CSS or inline SVG. Preserve its labels, arrows, grouping, colors, and relationships. Do **not** add an `<img>` placeholder for this figure. Inline SVG is preferred over canvas because page HTML must work without JavaScript.
- **`extract-raster`**: keep the figure in a proper `<figure>` and use the standard `../assets/images/page_NNNN_fig_X.png` placeholder. The post-render extractor will crop only the diagnosed artwork bounds and leave the source caption out when an HTML `<figcaption>` exists.
- Preserve the caption as semantic `<figcaption>` text in both cases. Do not duplicate a caption inside a raster crop.
- Add `data-visual-id="X"` to every planned visual container, using the exact id from the visual plan. Use `<figure>` for a standalone visual; a small icon adjacent to a heading may use an inline `<span>` container.

For a family tree, pedigree, org chart, flowchart, timeline, form, or worksheet diagram, keep every visible label and answer blank as real HTML text/elements and draw only connectors or geometry with inline SVG/CSS. Preserve topology and relative grouping; do not substitute a screenshot just because the source page was scanned.

For a finalized raster technical visual (`technical-drawing`, `engineering-schematic`,
`construction-detail`, `composite-engineering-sheet`, or `dense-technical-diagram`), do not
redesign, simplify, recolor, or redraw it. Preserve the crop's aspect ratio, line work, symbols,
dimensions, and colors. Keep its placement and scale relative to neighboring notes and tables.

Apply the same strict rule to every non-basic drawing, illustration, map, schematic, branded
visual, or detailed chart: use the planned source-pixel image and target at least 99% visual
fidelity. Only a visual explicitly marked `complexity: basic` may be reconstructed. Never replace
a protected crop with a cleaner, generic, translated, recolored, or simplified SVG.

For a simple icon, pictogram, glyph, exercise marker, or standard symbol, render a compact accessible inline SVG, CSS shape, or reliable Unicode character. Match its size and baseline beside the surrounding heading/text. Do not emit an `<img>` placeholder or asset path for it.

If a simple vector figure was not reconstructed by the agent, the post-render pipeline may replace its image placeholder with a clipped inline SVG from the source PDF as a fidelity fallback.

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

DO NOT run any post-render scripts (such as `diagnose_page_visuals.py`, `materialize_vector_figures.py`, `extract_pdf_figures.py`, `upgrade_figure_html.py`, `fix_book_layout.py`, or `validate_page_fidelity.py`) yourself. These scripts are run automatically by the main orchestrator after you finish. Running them yourself as background tasks will cause your process to exit early and fail. Simply write the completed HTML file and finish.

## Self-Verification Steps (CRITICAL)

After writing the HTML file, you MUST perform a self-verification pass using your file tools to ensure all resources load successfully:
1. **Verify CSS Stylesheets**: Find every stylesheet link (e.g. `../assets/book.css`) in your written HTML. Resolve it from `output/<lang>/`; it must point to the corresponding file under `output/assets/`.
2. **Verify Images & Figures**: For every `<img>` tag you wrote, resolve its relative path (e.g. `../assets/images/page_NNNN_fig_X.png`) from `output/<lang>/` and verify that the target image file exists. If the image is not present yet but is required by the page layout, make sure the reference is clean and structured under a proper `<figure>` container so the pipeline can extract it later.
3. **Verify Javascript**: Ensure no unexpected scripts or external links are present.
4. **Immediate Fix**: If any file path is incorrect, broken (404), has unencoded spaces, or is missing, modify your HTML to fix the path before completing your work.

## Done when

Side-by-side with `source.pdf`: correct **order**, **block types**, **chrome**, **listings**, **figures**, **math**; page N only. Must fit onto exactly one A4 page without clipping or overflow.

Also verify that dominant source colors are not replaced by a generic theme and that major
regions remain in the same top/middle/bottom and left/right relationships. A page with correct
text but simplified drawings, changed colors, or reordered regions is not done.
