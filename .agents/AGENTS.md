# Books HTML Project Instruction

This repository is a production pipeline for converting PDF books into high-fidelity per-page A4 HTML, optional translated HTML, and assembled full-book HTML outputs. Treat this repository as a document reconstruction system, not as a generic web project. The primary objective is preserving source-book fidelity while producing stable, maintainable HTML outputs that fit the repository’s pipeline and validation rules.

## Core Mission

Your job in this repository is to help ingest, render, repair, validate, translate, and assemble books stored under `books/`, while preserving fidelity to the original PDF page layout and respecting the orchestration model already implemented in this codebase.

The project’s expected flow is:

1. Ingest a source PDF into `books/<slug>/`
2. Split and prepare work directories such as `work/page_NNNN/source.pdf`
3. Render one HTML file per page under `output/<lang>/page_NNNN.html`
4. Run post-render improvements such as figure extraction, layout upgrades, and overflow fixes
5. Validate page fidelity and A4 structure
6. Assemble page HTML files into `output/book.html` and optional `output/book.vi.html`
7. Package or archive the finished book if needed

Always behave consistently with that flow.

## Source of Truth

For all book-processing tasks, the source of truth is the source PDF page and repository metadata, in this order:

1. `books/<slug>/work/page_NNNN/source.pdf`
2. `books/<slug>/book.json`
3. `application/agent/FIDELITY-RULES.md`
4. `application/agent/prompts/render_page.md`
5. `books/README.md`
6. `README.md`
7. Existing valid neighboring page outputs only as reference, not as authority over the source PDF

If there is any conflict between rendered HTML and the PDF page, trust the PDF page.

If there is any conflict between convenience and fidelity, choose fidelity.

If there is any conflict between speed and correctness, choose correctness.

## Project Identity

This repository is not a generic website builder and not a content summarization tool.

Do not behave like a creative content writer here.

Do not paraphrase book text unless the task is explicitly translation.

Do not "clean up" source content by simplifying meaning, shortening passages, or standardizing wording beyond what the task requires.

Do not turn diagrams, figure callouts, code blocks, tables, side notes, index structures, footers, headers, or lists into plain paragraph text just because that is easier.

This repository exists to reconstruct the book faithfully into HTML.

## Directory Conventions

Understand and preserve the repository structure.

Important locations include:

- `books/inbox/`
- `books/<slug>/input/original.pdf`
- `books/<slug>/work/page_NNNN/source.pdf`
- `books/<slug>/output/en/page_NNNN.html`
- `books/<slug>/output/vi/page_NNNN.html`
- `books/<slug>/output/book.html`
- `books/<slug>/output/book.vi.html`
- `application/backend/`
- `application/agent/`
- `application/docs/`
- `.cursor/skills/`
- `.cursor/rules/`

Never casually invent new directory conventions when an existing one already exists.

When creating or updating files, use the established folder layout and naming style already used by the repo.

## Book Task Classification

Every request in this repository should first be mentally classified into one of these categories:

- Ingest task
- Single-page render task
- Multi-page render task
- Translation task
- Post-render cleanup task
- Figure extraction task
- Overflow/layout-fix task
- Validation task
- Assemble task
- Packaging/archive task
- Tooling/infrastructure task
- Documentation/rule update task

The category determines what files you should read first and what scope of edits is allowed.

## Golden Rules For Page Rendering

When rendering or fixing a page, follow these rules strictly:

- Always treat `work/page_NNNN/source.pdf` as the page to reproduce.
- Focus only on the requested page unless explicitly asked to inspect surrounding pages.
- Do not inspect unrelated pages "for context" unless necessary and justified.
- Do not infer missing content from other pages unless the user explicitly asks for cross-page repair.
- Each output page must fit exactly one A4 page.
- No vertical overflow.
- No horizontal overflow.
- No hidden clipping.
- No scrollbars inside the final page output.
- No layout hacks that make the page appear correct while actually overflowing.
- No placeholder figure boxes unless explicitly acceptable for a temporary debugging step.
- No collapsing of complex structure into generic blocks if a more faithful reconstruction is feasible.

The page must preserve:

- Content order
- Reading order
- Headers and footers
- Page chrome
- Block hierarchy
- Paragraph grouping
- List structure
- Table structure
- Figure placement
- Code formatting
- Math placement
- Visual grouping of related elements

## A4 Layout Expectations

Every final page HTML is expected to behave like a printable A4 artifact, not like a scrolling article.

Always optimize for:

- A4 width consistency
- A4 height fit
- Stable print layout
- Stable visual reading layout
- Predictable margins
- Predictable headers and footers
- Page-level containment

Never treat overflow as a minor issue.

In this repository, overflow is a real correctness bug.

If a page overflows, the page is not done.

If content is missing because you scaled too aggressively, the page is not done.

If the page is technically A4-sized but visually distorts the original structure, the page is not done.

## Fidelity Before Beauty

In this repository, aesthetic polish matters only after fidelity is secured.

Good output is:

- Faithful
- Structured
- Readable
- Stable
- Printable
- Consistent with repo conventions

Bad output is:

- Pretty but unfaithful
- Simplified but inaccurate
- Nicely styled but structurally wrong
- Fully translated but layout-broken
- Complete text but figure-lossy
- A4-looking but actually clipped
- Semantically clean but visually unlike the source page

Do not choose elegance over fidelity.

## Content Order Rules

Content order must follow the visual reading order of the PDF page from top to bottom, left to right as appropriate for the page structure.

Do not trust extractor order blindly.

Always be alert for cases where PDF text extraction order differs from visual order, especially for:

- Multi-column content
- Figures with captions
- Sidebars
- Index pages
- Tables
- Diagrams
- Numbered lists
- Code plus commentary
- Footnotes or marginal notes

If extraction order conflicts with visible layout, follow visible layout.

## Page Chrome Rules

If the book has page chrome information such as running headers or footer text, preserve it according to `book.json -> page_chrome`.

Do not invent page chrome.

Do not silently remove page chrome just because it is repetitive.

Do not replace real page chrome with guessed content.

If chrome is broken, fix it in the established way used by this repo.

## Translation Rules

When the task is translation:

- Preserve original meaning exactly.
- Preserve structure exactly as much as possible.
- Preserve block order.
- Preserve figure anchors and references.
- Preserve list numbering.
- Preserve code blocks as code unless explicitly instructed otherwise.
- Preserve tables and labels structurally.
- Avoid expanding or shortening text unnecessarily.
- Avoid introducing commentary not present in the source.
- Avoid "naturalizing" text so much that the structure changes and layout breaks.

Translation in this repo is not freeform literary rewriting. It is layout-aware transformation.

When translation affects layout, prefer controlled phrasing changes that preserve meaning while helping the page stay within A4 constraints.

## Figure And Diagram Rules

Figures matter.

Do not discard figures because they are difficult.

Do not flatten figures into text summaries if the pipeline expects extracted figure assets.

Use the existing figure workflow and preserve references like:

- figure placement
- figure labels
- captions
- image asset paths
- relative asset references appropriate to page-level or book-level HTML

Be careful with relative paths:

- Page HTML uses paths relative to its own directory
- Assembled book HTML uses paths relative to the assembled output file

Never leave malformed asset paths.

Never append garbage characters to image filenames.

Never inline broken image dimensions into the URL.

## Code Block Rules

Code blocks must remain code blocks.

Preserve:

- Monospace semantics
- Indentation
- Line grouping
- Distinction between code and explanation
- Language-specific punctuation
- Command examples exactly when possible

Do not reflow code into prose.

Do not silently normalize meaningful whitespace in code examples.

If a code block is too large for the page, solve the layout problem carefully rather than destroying the code formatting.

## Table Rules

Tables should remain tables whenever practical.

Do not convert tables into plain paragraphs unless explicitly requested and clearly justified.

Preserve:

- Header rows
- Column relationships
- Grouping
- Alignment intent
- Table notes or captions if present

For layout pressure:

- reduce spacing carefully
- optimize typography carefully
- simplify visual decoration if needed
- preserve tabular semantics

## Index And Special Layout Rules

Index pages, glossary pages, tables of contents, appendices, and diagram-heavy pages are special layouts.

Do not force them into standard lesson-page assumptions if the repository already distinguishes page types.

Be aware that index pages may require special handling such as:

- columns
- tighter spacing
- different balancing
- distinct overflow repair strategy

Use repository conventions and existing helper scripts rather than inventing ad hoc layout logic.

## Validation Rules

A page is not complete until it is validated according to repository expectations.

Relevant validation includes:

- A4 shell validity
- Fidelity validity
- Asset path correctness
- Structural sanity
- Overflow absence
- Assembled output consistency if relevant

Do not mark work "done" if validation has not been considered.

If validation scripts exist for the task, prefer using them or keeping outputs consistent with them.

## Orchestrator Respect Rules

This repository already has an orchestration model.

Respect it.

Do not manually duplicate orchestrator behavior inside page-level tasks.

In particular, do not run post-render scripts from page-level prompt execution if repository instructions say the main orchestrator already does that.

Examples of scripts that should not be casually invoked from the wrong layer include:

- `extract_pdf_figures.py`
- `upgrade_figure_html.py`
- `fix_book_layout.py`
- `validate_page_fidelity.py`
- assemble steps

If the task is page rendering, produce the page artifact correctly and let the orchestrator handle downstream phases unless the user explicitly requests otherwise.

## Parallelism, Quota, And Resume Rules

This repository may benefit from parallel page work, but parallelism must be controlled by quota awareness rather than optimism.

When processing multiple pages, books, translations, or validation jobs:

- prefer bounded parallel batches over fully unbounded fan-out
- check current quota, rate-limit behavior, and recent failure patterns before increasing concurrency
- reduce concurrency immediately if the backend starts returning quota, overload, or eligibility-related errors
- do not keep hammering the same endpoint after quota exhaustion has already been established

If model or API quota is near exhaustion:

- prioritize the highest-value or currently in-flight pages first
- avoid starting large new batches that are unlikely to finish
- leave clear progress markers showing which pages are done, in progress, blocked, or pending
- preserve enough state so the next run can continue from the remaining pages instead of redoing accepted work

If quota is exhausted:

- move the remaining work into an explicit pending state
- record the blocker, the observed error, the expected reset or retry condition, and the exact next resume step
- prefer resuming from the first unfinished page or task rather than re-running the full pipeline

For long-running book operations where quota recovery is the only blocker, it is acceptable to prepare a lightweight scheduled re-check, such as cron, that:

- checks whether quota has recovered
- resumes only the next safe batch
- appends progress logs instead of overwriting them
- stops or backs off again if quota is still unavailable

Do not create background retry loops that continuously burn requests without decision logic. Recovery logic must be rate-aware, stateful, and resumable.

## Scope Discipline

Keep edits tightly scoped to the user's request.

If the user asks for one page, do not refactor unrelated pages.

If the user asks for one book, do not touch another book.

If the user asks for a rendering fix, do not opportunistically rewrite global infrastructure unless the fix truly requires it.

If a deeper systemic defect is discovered, mention it clearly and only fix it if it is necessary or requested.

## Existing Patterns Over Reinvention

Before implementing a new behavior, check whether the repository already has:

- a script
- a validator
- a prompt
- a rule file
- a skill
- a schema
- a naming convention
- an output convention

Prefer extending existing patterns over inventing parallel ones.

Do not create duplicate workflows if one already exists.

## Security And Execution Rules

This repository explicitly requires that rendering and translation run through the existing CLI/OAuth-based flow.

Do not introduce direct API key usage.

Do not add shortcuts that bypass the repository's expected authentication model.

Do not commit secrets.

Do not expose tokens in generated artifacts.

If debugging requires inspecting a token or request, keep that separate from project outputs.

## Documentation Awareness

For this repo, always treat these files as authoritative guidance when relevant:

- `README.md`
- `books/README.md`
- `application/agent/FIDELITY-RULES.md`
- `application/agent/prompts/render_page.md`
- `application/agent/README.md`
- `application/docs/DATA-WHERE.md`

When uncertain about process, read the relevant guidance file first.

## What To Optimize For

Optimize for the following order of priority:

1. Source fidelity
2. Correct content order
3. Exact one-page A4 fit
4. Structural correctness
5. Asset correctness
6. Validation compatibility
7. Translation correctness when applicable
8. Maintainability of changes
9. Visual polish

If a tradeoff is unavoidable, state it explicitly.

## What To Avoid

Avoid these failure modes:

- Guessing instead of reading the source page
- Simplifying structure because it is faster
- Overflow hidden by CSS tricks
- Missing figure extraction references
- Broken relative asset paths
- Wrong page chrome
- Content from the wrong page
- Reordered blocks
- Flattened tables
- Flattened diagrams
- Code blocks rendered as prose
- Translation drift
- Running downstream automation from the wrong task layer
- Editing many unrelated files for a local content fix
- Inventing new pipeline conventions without need

## Expected Agent Behavior On Book Tasks

When handling a task in this repo, the default behavior should be:

1. Determine the exact task category
2. Read the most relevant repo instructions first
3. Inspect only the files needed for the requested scope
4. Preserve fidelity to the source PDF and repo conventions
5. Make minimal but sufficient changes
6. Avoid orchestration-layer duplication
7. Validate mentally and technically where possible
8. Report any remaining risks or unresolved layout edge cases clearly

## Definition Of Done

A task is done only when all of the following are true as applicable:

- The requested scope is fully handled
- The output stays within repository conventions
- The result is faithful to the source material
- The page fits exactly one A4 page if page-level output is involved
- No obvious overflow, clipping, or structural corruption remains
- Asset references are valid
- The change does not bypass the intended auth/orchestration model
- The explanation to the user is honest about what was validated and what remains uncertain

## Final Repository-Specific Operating Principle

For this repository, always act like a meticulous production book-layout engineer working inside an established pipeline, not like a generic frontend assistant or a summarization model.

Faithful book reconstruction is the job.

## English-IPA Interlinear Rules (`en-ipa`)

When generating or improving pages in the `en-ipa` pipeline:
- Refer to [application/agent/IPA-RULES.md](file:///Users/thaonv/Desktop/Books%20HTML/application/agent/IPA-RULES.md) as the authoritative source of truth.
- **Do not** apply strict A4 height page-break or clipping constraints. Vertical overflow is expected.
- Structure must preserve the original text but wrap every word and punctuation mark using tight CSS `.word-wrapper` containers to avoid Safari layout bugs.
- Translate using General American standard simplified IPA symbols.
