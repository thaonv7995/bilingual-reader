# Flow (agent)

```text
User: copy PDF → books/inbox/foo.pdf
Agent: ingest → page-pdf → render (per page)
Result: books/<slug>/output/en/page_NNNN.html
```

```bash
books-cli ingest --pdf books/inbox/foo.pdf
books-cli render --book books/<slug> --page 1 --provider cursor --page-pdf
```

Skill: [books-pdf-render/SKILL.md](books-pdf-render/SKILL.md)
