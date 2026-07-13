#!/usr/bin/env python3
"""Create per-page visual strategy metadata before HTML rendering."""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from books_core.visual_diagnostics import ensure_visual_diagnosis  # noqa: E402


def _target_pages(book_root: Path, args: list[str]) -> list[int]:
    if args:
        return sorted({int(value) for value in args})
    return [
        int(path.parent.name.split("_")[1])
        for path in sorted((book_root / "work").glob("page_*/source.pdf"))
    ]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: diagnose_page_visuals.py <book-root> [page ...]", file=sys.stderr)
        return 2
    book_root = Path(argv[1]).expanduser().resolve()
    try:
        pages = _target_pages(book_root, argv[2:])
        for page_num in pages:
            # A finalized agent-vision plan is authoritative. This script only
            # supplies deterministic recovery metadata for legacy pages that
            # do not have one; it must never overwrite the agent's plan.
            diagnosis = ensure_visual_diagnosis(book_root, page_num, force=False)
            counts: dict[str, int] = {}
            for figure in diagnosis.get("figures", []):
                strategy = str(figure.get("strategy") or "unknown")
                counts[strategy] = counts.get(strategy, 0) + 1
            summary = ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
            producer = diagnosis.get("producer") or "deterministic-fallback"
            print(f"page {page_num:04d}: {producer}; {summary or 'no figures detected'}")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"FAIL visual diagnosis: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
