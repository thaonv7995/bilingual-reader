from __future__ import annotations

from books_agent.detect import DetectResult, detect_binary
from books_agent.providers.base import Provider, RunResult
from books_agent.providers.registry import all_providers, get_provider

__all__ = [
    "DetectResult",
    "detect_binary",
    "Provider",
    "RunResult",
    "all_providers",
    "get_provider",
]
