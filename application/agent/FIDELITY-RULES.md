# Page fidelity rules (all books)

**Goal:** `output/<lang>/page_NNNN.html` matches `work/page_NNNN/source.pdf` side-by-side — same **content order**, **block types**, **positions**, and **typography**.

These rules apply to **every book**. Book-specific header/footer text lives in `book.json` → `page_chrome` (see below).

---

## Rule 0 — Read the PDF visually first

| Do | Don't |
|----|--------|
| Open `source.pdf` and scan layout top→bottom | Trust text-extraction order alone |
| Note where figures sit **above or below** captions | Assume caption always precedes artwork |
| Place blocks in **visual** order | Reorder because raw PDF text lists figures last |

**Common failure:** Listing 2-5 referenced in prose but rendered at page bottom because the text extractor listed it after other paragraphs.

---

## Rule 1 — Page chrome (header / footer)

Read `book.json` → `page_chrome`. If missing, detect from page 1 PDF during ingest or set manually once per book.

| Zone | Typical pattern | HTML |
|------|-----------------|------|
| **Running head** | Site/series left, **page number right** | `.running-head` + `.rh-left` / `.rh-right` |
| **Footer** | Author left, copyright right | `.book-footer` with two `<span>` |

```html
<header class="running-head">
  <span class="rh-left"><!-- page_chrome.head_left --></span>
  <span class="rh-center"></span>
  <span class="rh-right"><!-- page number N --></span>
</header>
<footer class="book-footer">
  <span><!-- page_chrome.foot_left --></span>
  <span><!-- page_chrome.foot_right --></span>
</footer>
```

**Never** put author name in the running head. **Never** drop the footer.

After render, run `fix_book_layout.py` to normalize chrome across pages.

---

## Rule 2 — Headings (run-in vs block)

| PDF pattern | HTML | Wrong |
|-------------|------|-------|
| `Title.` + body **same line** | `<p class="no-indent"><strong class="run-in">Title.</strong> body…</p>` | `<h3 class="section-title">TITLE.</h3>` |
| `Title` on **own line**, no period | `<h3 class="section-title">Title</h3>` | Uppercase block for run-in phrases |

- Run-in: sentence case, **not** `text-transform: uppercase`
- Block section titles: title case, no forced caps

---

## Rule 3 — Special blocks (decision matrix)

See `.cursor/skills/books-pdf-to-html/special-layouts.md`. Summary:

| PDF content | HTML | CSS |
|-------------|------|-----|
| Body prose | `<p>` | `prose-page.css` |
| **Listing** (caption + code) | `<figure class="listing">` caption **above** `<pre class="code-block">` | `code-page.css` |
| Code snippet (no listing #) | `<figure class="code-snippet"><pre class="code-block">` | `code-page.css` |
| **Structured diagrams** (UML, flow, family tree, org chart, timeline) | `<figure class="diagram">` with semantic HTML + inline SVG | `figures-page.css` |
| **Simple icons / pictograms** | Inline `<span data-visual-id>` with SVG/CSS/Unicode | Match surrounding text size/baseline |
| **Pixel-dependent visuals** (photos, textured art, complex maps) | `<figure class="diagram"><img src="../assets/images/…">` | `figures-page.css` |
| **Dense technical drawings** (engineering/architectural sheets, dimensioned construction details) | Cropped source visual in `<figure class="diagram">`; keep surrounding tables/text semantic | `figures-page.css` |
| Simple math / metrics | `.math`, `.frac`, `.metric-block`, `.formula-display` | `figures-page.css` |
| Tables | `<table class="data-table">` | `code-page.css` |
| Footnotes | `.footnotes` at bottom (before footer) | `prose-page.css` |

**Forbidden:**
- Diagram labels as a stack of `<p>` tags
- `<pre class="ascii-figure">` for UML/box diagrams (use semantic HTML/inline SVG)
- Gray code background unless source PDF has it
- `overflow-x: auto` on code (wrap instead; see `code-page.css`)

---

## Rule 4 — Figures & images

**Strict 99% visual rule:** classify by visible content, never by the PDF container. Every drawing, illustration, map, schematic, branded artwork, detailed chart, and non-basic diagram MUST preserve source pixels with `extract-raster`; the target is at least 99% visual similarity for the visual region. Do not redraw, simplify, recolor, restyle, reinterpret, or substitute these visuals. Only a genuinely basic diagram made from a small number of boxes, lines, arrows, and labels may use semantic HTML/inline SVG, and its visual plan must explicitly set `complexity: basic`. Semantic prose and tables outside protected visual crops remain HTML.

**Composite sheet layout rule:** pages containing multiple technical sections must set `page_layout.mode: source-anchored` with normalized bboxes for every major region. Render these pages on a coordinate-preserving A4 canvas. Use controlled absolute positioning inside the canvas; ordinary flex/grid flow must not reorder or push sections away from their source regions. Every anchored section must carry `data-source-region`, and the page shell must carry `data-layout-mode="source-anchored"`.

**Color fidelity rule:** source colors are immutable. Preserve exact header/section fills, page-number badge colors, table fills, border/stroke colors, text colors, logos, rules, and running chrome. Sample colors from the source reference and record them as `fill_color`, `stroke_color`, or `text_color` anchors in `page_layout.regions`. Never apply a generic theme or change colors because the target language differs.

For every protected source-pixel visual, the plan must contain `fidelity_target: 0.99` and `preservation_mode: source-pixels`. A generic `diagram` or `*-diagram` without explicit `complexity: basic` is treated as non-basic and must be raster-preserved.

**Raster pipeline (only for visuals classified `extract-raster`):**

```bash
# 1. Crop figures from single-page PDFs
application/.venv/bin/python3 application/backend/scripts/extract_pdf_figures.py books/<slug>

# 2. Replace ascii diagrams + refresh img paths
application/.venv/bin/python3 application/backend/scripts/upgrade_figure_html.py books/<slug>
application/.venv/bin/python3 application/backend/scripts/refresh_figure_images.py books/<slug>

# 3. Normalize chrome + run-in headings
application/.venv/bin/python3 application/backend/scripts/fix_book_layout.py books/<slug>
```

Markup:

```html
<figure class="diagram">
  <img src="../assets/images/page_NNNN_fig_X_Y.png" width="…" height="…" alt="Figure X-Y">
  <figcaption><strong>Figure X-Y</strong><br>Title from PDF</figcaption>
</figure>
```

Use raster extraction only for a finalized `extract-raster` visual. For `reconstruct-html-svg`, preserve readable labels as HTML (or accessible SVG text) and reproduce the source geometry with inline SVG/CSS.

---

## Rule 5 — Content order checklist

Before accepting a page, verify:

1. [ ] First line matches PDF (continuation hyphenation from previous page if any)
2. [ ] Each **Listing N** sits where PDF shows it (often right after "See Listing N")
3. [ ] Figures between the paragraphs that reference them
4. [ ] Footnotes after body, **before** `.book-footer`
5. [ ] No content from page N+1 / missing content from page N
6. [ ] Dominant colors match the source; no generic theme color replaces source branding
7. [ ] Major regions retain their source relationships (left/right and top/middle/bottom)
8. [ ] Technical drawings retain exact line work and are not simplified substitutes

---

## Rule 6 — Required shell & stylesheets

Every page:

```html
<body class="book-standalone">
  <main class="book-page book-page--sheet">
    <article class="sheet-flow prose-page">
```

Always link: `book.css`, `page-tokens.css`, `prose-page.css`

The `<article>` must contain meaningful visible text or artwork. A shell containing only page chrome is invalid. Image-only/scanned PDFs must be read from `work/page_NNNN/source.png`; lack of extractable PDF text is not evidence of a blank page. Only a genuinely blank source page may use `<article ... data-intentionally-blank="true">`.

Also link when needed:
- `code-page.css` — listings, tables, monospace blocks
- `figures-page.css` — diagrams, math, metrics

Inline `<style>` only for `@media print { .book-page { height: 296mm; } }` — not per-page layout clones.

---

## Rule 7 — Validation before assemble

```bash
# Structural A4 shell
python3 .cursor/skills/books-pdf-to-html/scripts/validate_a4_page.py books/<slug>/output/en/page_*.html

# Fidelity lint — all langs + assembled books
application/.venv/bin/python3 application/backend/scripts/validate_page_fidelity.py books/<slug> --lang all
```

The fidelity validator renders every standalone page with Chromium print CSS and fails when:

- the page shell is not 210mm × 296–297mm;
- visible text, images, or positioned content crosses any page edge;
- text/content is hidden by an inner `overflow: hidden/clip/auto` box;
- `overflow: hidden` on the A4 shell merely conceals content outside the page.

Failures are written to `work/repair-report.json` as `layout_overflow` so each affected page can be repaired from Studio. The `en-ipa` pipeline keeps its documented vertical-overflow exception, but horizontal bounds are still enforced.

Fix all errors before `books-cli assemble`.

---

## Rule 8 — Assembled book (`book.html` / `book.vi.html`)

`books-cli assemble` must produce the **same A4 shell** as per-page files:

```html
<section class="book-sheet" id="page-NNNN">
  <main class="book-page book-page--sheet">
    <article class="sheet-flow prose-page">…</article>
  </main>
</section>
```

Per-page head must link: `../assets/book.css`, `../assets/page-tokens.css`, `../assets/prose-page.css`, and `../assets/code-page.css` / `../assets/figures-page.css` when used.

**Never** dump raw `<article>` content without `main` + `prose-page` wrapper.

After translate, assemble each language:

```bash
books-cli assemble --book books/<slug> --lang en --output book.html
books-cli assemble --book books/<slug> --lang vi --output book.vi.html
```

Re-run `validate_page_fidelity.py` after assemble (it checks assembled files too).

---

## Rule 9 — Asset paths (images & CSS)

| File location | Correct asset prefix | Example |
|---------------|---------------------|---------|
| `output/<lang>/page_NNNN.html` | `../assets/` | `src="../assets/images/page_0006_fig_2_13.png"` |
| `output/book.html` | `assets/` (no `..`) | `src="assets/images/page_0006_fig_2_13.png"` |

**Image src rules:**
- Must end with a real extension: `.png`, `.jpg`, `.svg`, …
- **Forbidden:** junk after extension (`page_0006.png1546è9`) — always use separate `width` / `height` attributes
- File must exist under `output/assets/images/`
- Use `figures.manifest.json` + `refresh_figure_images.py` — never hand-edit src with dimensions glued on

`assemble` rewrites `../assets/` → `assets/` automatically. Do not manually edit assembled files.

---

## Rule 10 — Full post-render pipeline (copy for every book)

```bash
BOOK=books/<slug>
PY=application/.venv/bin/python3

# Figures
$PY application/backend/scripts/extract_pdf_figures.py "$BOOK"
$PY application/backend/scripts/upgrade_figure_html.py "$BOOK"
$PY application/backend/scripts/refresh_figure_images.py "$BOOK"

# Layout
$PY application/backend/scripts/fix_book_layout.py "$BOOK"

# Validate per-page (all langs)
$PY application/backend/scripts/validate_page_fidelity.py "$BOOK" --lang all
python3 .cursor/skills/books-pdf-to-html/scripts/validate_a4_page.py "$BOOK"/output/en/page_*.html

# Assemble + validate again
books-cli assemble --book "$BOOK" --lang en --output book.html
books-cli assemble --book "$BOOK" --lang vi --output book.vi.html   # if translated
$PY application/backend/scripts/validate_page_fidelity.py "$BOOK" --lang all
```

---

## Anti-patterns (learned from production)

| Symptom | Root cause | Fix |
|---------|------------|-----|
| Listing at wrong position | Text-extract order | Re-read PDF visually; move `<figure class="listing">` |
| CLIENTS RUIN EVERYTHING block heading | Run-in treated as h3 + uppercase CSS | `run-in` paragraph + remove `text-transform: uppercase` |
| Author in header | Guessed template | `page_chrome` + `fix_book_layout.py` |
| Ellipse/Circle as two lines of ASCII | Lazy diagram | Rebuild with inline SVG |
| Code in gray box | Default IDE styling | `code-page.css` transparent background |
| Figure missing | Never extracted | Run figure pipeline after render |
| Broken `<img>` used for a simple icon | Icon incorrectly classified as raster | Replace with inline SVG/CSS/Unicode and rerender the page |
| Broken raster figure | Corrupt `src` or wrong `../` prefix in assembled book | `refresh_figure_images.py` + Rule 9; re-assemble |
| `book.vi.html` plain text blob | Assemble without A4 shell/CSS | Rule 8; use current `assemble.py` |
| Duplicate Figure label | `alt` + empty `figcaption` | One caption in `<figcaption>`; alt can mirror |
