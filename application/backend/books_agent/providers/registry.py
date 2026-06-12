from __future__ import annotations

from books_agent.providers.antigravity import AntigravityProvider
from books_agent.providers.base import Provider
from books_agent.providers.claude import ClaudeProvider
from books_agent.providers.codex import CodexProvider
from books_agent.providers.cursor import CursorProvider

_PROVIDERS: list[Provider] = [
    CursorProvider(),
    CodexProvider(),
    ClaudeProvider(),
    AntigravityProvider(),
]

_BY_ID = {p.id: p for p in _PROVIDERS}


def all_providers() -> list[Provider]:
    return list(_PROVIDERS)


def get_provider(provider_id: str) -> Provider:
    p = _BY_ID.get(provider_id)
    if not p:
        raise KeyError(f"Unknown provider: {provider_id}")
    return p
