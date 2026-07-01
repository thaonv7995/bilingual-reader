from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from books_agent.phase_pack import phase_skill_pack
from books_agent.phases import PROMPT_FILES, AgentPhase
from books_core.paths import BookPaths
from books_core.repo import repo_root, skills_root


def agent_prompts_dir() -> Path:
    return repo_root() / "application" / "agent" / "prompts"


def build_context(book: BookPaths, page: int, phase: AgentPhase) -> dict[str, Any]:
    lang = book.default_lang()
    work = book.page_work(page)
    agent = work / "agent"

    def rel(p: Path) -> str:
        try:
            return str(p.relative_to(book.root))
        except ValueError:
            return str(p)

    source_page_pdf = book.source_page_pdf(page)
    output_file = rel(book.page_lang_html(page, lang))
    paths = {
        "book_root": str(book.root),
        "work_dir": rel(work),
        "agent_dir": rel(agent),
        "source_page_pdf": rel(source_page_pdf) if source_page_pdf.is_file() else None,
        "input_pdf": rel(book.input_dir / "original.pdf")
        if (book.input_dir / "original.pdf").is_file()
        else None,
        "source_pdf": rel(book.source_pdf) if book.source_pdf.is_file() else None,
        # This is the required destination, not a description of an existing file.
        "published_html": output_file,
    }

    skills = {
        "fidelity_rules": rel(repo_root() / "application" / "agent" / "FIDELITY-RULES.md"),
        "books_pdf_render": rel(skills_root() / "books-pdf-render" / "SKILL.md"),
        "special_layouts": rel(skills_root() / "books-pdf-to-html" / "special-layouts.md"),
    }

    prerequisites: list[str] = []
    hints: list[str] = []
    if phase == "render_page":
        if not paths.get("source_page_pdf"):
            prerequisites.append(
                "Run page-pdf first (work/page_NNNN/source.pdf required)."
            )
        hints.append("MUST READ: application/agent/FIDELITY-RULES.md before writing HTML.")
        hints.append(f"Primary input: {rel(source_page_pdf)} — open visually; do not trust text-extract order.")
        hints.append("After render: extract_pdf_figures → upgrade_figure_html → fix_book_layout → validate_page_fidelity.")

    skill_pack = phase_skill_pack(phase, skills, paths)
    skill_pack["output_contract"] = [
        str(rule)
        .replace("output/<lang>/page_NNNN.html", output_file)
        .replace("page_NNNN", f"page_{page:04d}")
        for rule in skill_pack.get("output_contract", [])
    ]

    return {
        "schema_version": "1.0",
        "phase": phase,
        "page": page,
        "lang": lang,
        "output_file": output_file,
        "paths": paths,
        "skills": skills,
        "skill_pack": skill_pack,
        "prerequisites": prerequisites,
        "efficiency_hints": hints,
        "repo_root": str(repo_root()),
    }


def build_prompt_markdown(book: BookPaths, page: int, phase: AgentPhase, ctx: dict[str, Any]) -> str:
    template = agent_prompts_dir() / PROMPT_FILES[phase]
    nn = f"{page:04d}"
    base = template.read_text(encoding="utf-8") if template.is_file() else f"# Phase {phase}\n"
    base = base.replace("page_NNNN", f"page_{nn}").replace("<lang>", str(ctx["lang"]))
    header = f"""---
book: {book.root.name}
page: {page}
phase: {phase}
work: work/page_{nn}/
---

"""
    body = f"""
## Binding skill pack

```json
{json.dumps(ctx.get("skill_pack") or {}, indent=2, ensure_ascii=False)}
```

## Session context

```json
{json.dumps(ctx, indent=2, ensure_ascii=False)}
```

## Book workspace

Open folder: `{book.root}`

Required output (exact path): `{ctx["output_file"]}` relative to `{book.root}`.
Write the final HTML only to that canonical path. Do not write it under `work/` or legacy `pages/`.

"""
    return header + base + body
