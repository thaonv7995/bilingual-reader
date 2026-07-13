# Phase: Vision-first page analysis (`analyze_visuals`)

You are the **visual planner** for one complete PDF page. This phase runs before HTML rendering.

## Required visual inspection

1. Open `work/page_NNNN/source.png` and inspect the **entire page visually**.
2. Use `work/page_NNNN/source.pdf` only as supporting evidence.
3. Do not decide from extracted text, caption regexes, or filenames alone.

When the provider supplies `source.pdf` directly as a multimodal attachment, inspect its complete page visually; the attached PDF is equivalent to opening `source.png`.

Identify every meaningful non-text visual:

- photograph or scanned artwork
- illustration
- chart, graph, map, timeline, or table rendered as artwork
- flowchart, UML, architecture diagram, or annotated schematic
- meaningful logo or cover art

Do not classify ordinary prose, headings, captions, rules, backgrounds, or whitespace as figures.

## Strategy decision

- `reconstruct-html-svg`: a simple diagram whose boxes, lines, arrows, labels, and relationships can be faithfully rebuilt using semantic HTML/CSS or inline SVG.
- `extract-raster`: a photograph, painting, scan, textured image, complex illustration, or visual that cannot be safely reconstructed.

## Bounding boxes

Return coordinates normalized to the full page image:

```text
[x0 / page_width, y0 / page_height, x1 / page_width, y1 / page_height]
```

All values must be between `0` and `1`. The visual bbox must contain the complete artwork without clipping. Exclude the caption when it will be represented as semantic HTML. Add `caption_bbox_normalized` separately, or `null` when no caption is visible.

## Required JSON output

Write exactly one JSON object to `work/page_NNNN/visual-diagnosis.json`:

```json
{
  "schema_version": "2.0",
  "producer": "agent-vision",
  "page": <page-number>,
  "figures": [
    {
      "id": "1",
      "type": "photo",
      "strategy": "extract-raster",
      "bbox_normalized": [0.20, 0.25, 0.80, 0.65],
      "caption_bbox_normalized": [0.15, 0.67, 0.85, 0.72],
      "confidence": 0.98,
      "label": "Short visual identifier",
      "reason": "Why this strategy is appropriate"
    }
  ]
}
```

Use figure ids in visual reading order: `1`, `2`, `3`, etc., unless the visible caption clearly supplies an id such as `1.1`. When the page has no meaningful visuals, return an empty `figures` array.

## Strict rules

- Do not write HTML in this phase.
- Do not extract or create image files yourself.
- Do not include Markdown fences or commentary in the JSON file.
- Do not finish until the JSON file exists at the exact required path and is valid JSON.
