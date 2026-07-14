# Special layouts — code, tables, diagrams, character art

**Read first:** [`application/agent/FIDELITY-RULES.md`](../../../application/agent/FIDELITY-RULES.md) (content order, chrome, anti-patterns — all books).

Read with [page-production.md](page-production.md), [vector-recreation.md](vector-recreation.md), [a4-strict-contract.md](a4-strict-contract.md) §4–§5.

**Rule:** Pick structure by **what the reader sees**, not by how the PDF stored text. Never dump diagram labels or monospace lines into plain `<p>`.

---

## Decision matrix

| PDF content | HTML | CSS / assets | Do not |
|-------------|------|--------------|--------|
| **Body prose** | `<p>` | `prose-page.css` | — |
| **Indented pseudo-code** (algorithm steps, C-like in prose flow) | `<pre class="code-block"><code>` | `code-page.css` | Split into many `<p>` |
| **Shell / syscall listing** (fixed columns, prompts `$`) | `<pre class="code-block"><code>` | monospace, preserve spaces | `<p>` per line |
| **Tables** (aligned columns, borders) | `<table>` + `<thead>`/`<tbody>` if helpful | `code-page.css` `.data-table` | Screenshot of table |
| **TOC dot leaders** | `.toc-row` grid | `toc-page.css` | Typed `.....` in one string |
| **Bullets** | `<ul class="bullets">` | `prose-page.css` | — |
| **Numbered lists** | `<ol class="numbered">` | page-local if needed | — |
| **Footnotes** | `.footnotes` | `prose-page.css` | Body size for notes |
| **Layer / flow diagrams** (boxes, rings, arrows) | Semantic HTML + dedicated **inline SVG** | `figures-page.css` | PNG crop; `<p>` per label; `ascii-figure` |
| **Box + table diagrams** (region tables, stacks, before/after) | Dedicated **SVG** per [figure-box-diagram-quality.md](figure-box-diagram-quality.md) | page bands in `<style>` | Cropped `<img>`; rushed HTML table; `max-height` on figure |
| **Relationship diagrams** (family tree, pedigree, org chart) | HTML labels/fields + inline SVG/CSS connectors | `figures-page.css` | Screenshot/crop of readable text and simple lines |
| **Simple icons / pictograms** (book, pencil, speaker, warning, exercise marker) | Compact inline SVG, CSS geometry, or reliable Unicode | page-local sizing/alignment | PNG crop; broken `<img>` placeholder |
| **ASCII / box drawings** (memory maps, trees in text) | `<pre class="ascii-figure">` **or** redraw SVG | monospace, `white-space: pre`, no wrap | Reflow as prose |
| **Dense charts / photos / scan-only art** | Cropped `<figure><img>` | [image-extraction-strict.md](image-extraction-strict.md) | Only when redraw infeasible |
| **Equations** (simple) | `<i>` / Unicode in `<p>` | — | Guess complex TeX |
| **Equations** (complex) | Crop figure or note `figure: extract` in checklist | extract | Low-quality HTML guess |

---

## Code blocks

**A4 deliverables:** follow **[code-listing-a4.md](code-listing-a4.md)** (binding via [STRICT-QUALITY.md](STRICT-QUALITY.md) R9). Summary:

- `body.book-standalone` + link `code-page.css`
- **No `overflow-x: auto`** — no horizontal scrollbars on screen or print
- `code-page.css` sets `pre-wrap` + `overflow: hidden` under `body.book-standalone`
- Dense figure listings: **9pt** in `<figure class="diagram">`, `max-width: 100%`
- Break long comment lines in source when needed; do not rely on scroll

### When to use `<pre><code>`

- Monospace font in PDF
- Indentation or column alignment must be preserved
- Prompts (`#`, `$`), syscall names, struct definitions, terminal output

### When **not** to use `<pre>`

- Normal paragraphs (even with `int`, `char*` inline) → `<p>` with `<code>` for tokens only
- Diagram labels (“Kernel”, “sh”) → SVG/HTML figure, not `<pre>`

### Markup

```html
<figure class="diagram">
  <pre class="code-block"><code>struct buf {
  int b_flags;
  char *b_addr;
};</code></pre>
  <figcaption>Figure 1.3. Example</figcaption>
</figure>
```

### Typography ([a4-strict-contract.md](a4-strict-contract.md))

- **9–10pt** monospace in figure listings; **9.5–11pt** for inline terminal samples
- Light rule or tint: `border-left` on `.code-block` (from `code-page.css`)

### Fit one A4 sheet

- Use **9pt** + line breaks before splitting to a second HTML page
- Split across two HTML pages only if the book’s PDF did (same break point)
- Never put code in `<p>` to avoid overflow — that breaks alignment
- **Reject** if browser preview shows a horizontal scrollbar on the code panel

---

## Tables

- Rebuild semantic `<table class="data-table">`, do not clip raster.
- Dense data: **10.5pt**, `border-collapse: collapse`, rules matching source.
- Wide tables: smaller type, landscape is **not** default — reflow columns or continue on next page per source.

---

## Diagrams vs “character charts”

| Looks like | Treatment |
|------------|-----------|
| Circles, wedges, labeled layers | **SVG** ([vector-recreation.md](vector-recreation.md)) |
| Tree built from `|`, `-`, `/` characters | `<pre class="ascii-figure">` or SVG if reused |
| Memory layout with addresses in columns | `<pre class="ascii-figure">` + verify spacing in print |
| Mixed figure + caption | `<figure>` + SVG/img + `<figcaption>` |

If a diagram consists mainly of readable text, standard symbols, boxes, rules, arrows, brackets, or connector lines, reconstruct it even when the PDF contains a single scanned image. Treat generic icons and pictograms as geometry, not image assets. PDF storage is not a visual-content classification. Raster cropping is reserved for photos, textured/hand-drawn artwork, genuine brand artwork that cannot be reproduced safely, and genuinely irreducible complex graphics.

**Anti-pattern:** PyMuPDF text order → 30× `<p>` (“Per Process Region Table”, “342K”, …). That is a **figure**, not prose.

---

## Brief checklist (per page)

In `checklist.md` Notes, add one line:

`special: prose | code | table | svg | ascii-pre | figure-crop | mixed`

---

## Shared CSS

Copy at book setup (with prose/toc):

- `assets/code-page.css` — link **only on pages** that need code/tables/ascii

```html
<link rel="stylesheet" href="../assets/code-page.css">
```

Template: [templates/page-code.html](templates/page-code.html)
