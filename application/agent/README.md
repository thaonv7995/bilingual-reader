# Agent prompts

| Phase | Prompt | Output |
|-------|--------|--------|
| `analyze_visuals` | `analyze_visuals.md` | `work/page_NNNN/visual-diagnosis.json` |
| `render_page` | `render_page.md` | `output/<lang>/page_NNNN.html` |

```bash
books-cli agent prepare --book <path> --page N --phase analyze_visuals
books-cli agent run --book <path> --page N --phase analyze_visuals --provider cursor
books-cli agent prepare --book <path> --page N --phase render_page
books-cli agent run --book <path> --page N --phase render_page --provider cursor
```
