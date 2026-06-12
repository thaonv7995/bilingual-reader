# Manual Control Rules

**Standard flow:** `.cursor/skills/FLOW.md`

- Do not spawn sub-agents for this book.
- Main agent owns QA, redesign, checklist, and translation gates.
- Default batch: 10 pages; update status per page.

## Per-page (step 1)

1. Architecture brief ([html-architecture.md](../../books-pdf-to-html/html-architecture.md))
2. HTML per [page-shell.md](../../books-pdf-to-html/templates/page-shell.md)
3. `validate_a4_page.py` exit 0
4. Print preview + screenshot QA → `accepted`

## Figures

- Diagrams / simple geometry → inline SVG ([vector-recreation.md](../../books-pdf-to-html/vector-recreation.md), [figure-svg-quality.md](../../books-pdf-to-html/figure-svg-quality.md))
- Photos / logos only → extract ([image-extraction-strict.md](../../books-pdf-to-html/image-extraction-strict.md))
- No full-page screenshots in `pages/page_####.html`
- `analysis/screenshots/` = QA only

## Page states

`pending` → `qa-in-progress` → `qa-failed` / `fixing` → `qa-passed` → `accepted`

## Fidelity vs redesign

- **Clean PDF page** → match source layout ([fidelity-rules](../../books-pdf-to-html/fidelity-rules.md)).
- **Ugly / unsuitable PDF page** → redesign for readable A4 HTML ([redesign-rules](../../books-pdf-to-html/redesign-rules.md)); record `redesign needed = yes`, strategy `redesign-a4`.

## Accept only when

- Editorial layout matches source ([html-architecture.md](../../books-pdf-to-html/html-architecture.md)).
- Content faithful to source (fidelity or redesign).
- **A4 strict** pass ([a4-strict-contract.md](../../books-pdf-to-html/a4-strict-contract.md)); validator exit 0.
- **Print preview: exactly 1 A4 sheet**, 100% scale, no clipped text.
- Side-by-side screenshot check done.
- `checklist.md` and `qa/manual-progress.md` updated (`architecture: …` in notes).

## Translation gate

Do not translate until source page is `accepted`.
