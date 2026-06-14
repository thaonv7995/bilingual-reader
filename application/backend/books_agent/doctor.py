from __future__ import annotations

from typing import Any

from books_agent.providers.registry import all_providers


def run_doctor() -> dict[str, Any]:
    providers = []
    available = []
    for p in all_providers():
        d = p.detect()
        row = d.to_dict()
        providers.append(row)
        if d.installed and d.runnable:
            available.append(d.id)
    return {
        "ok": len(available) > 0,
        "available_providers": available,
        "providers": providers,
        "note": "No API keys in app — CLIs must be on PATH and authenticated in your shell.",
    }
