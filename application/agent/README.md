# Agent prompts

| Phase | Prompt | Output |
|-------|--------|--------|
| `render_page` | `render_page.md` | `pages/<lang>/page_NNNN.html` |

```bash
books-cli agent prepare --book <path> --page N --phase render_page
books-cli agent run --book <path> --page N --phase render_page --provider cursor
```
