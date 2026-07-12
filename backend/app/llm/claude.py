"""Claude cloud provider — PLACEHOLDER.

Cloud support is planned as a second step. This stub keeps the provider
interface and API surface in place so wiring it later only touches this file:
add the `anthropic` dependency, read `settings.anthropic_api_key`, and stream
via client.messages.stream(...).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..config import settings

NOT_CONFIGURED_MESSAGE = (
    "Claude (cloud) is not implemented yet — it will be added in a second step. "
    "Use the local Ollama model for now."
)


class ClaudeClient:
    name = "claude"

    def __init__(self, model: str | None = None):
        self.model = model or "claude-sonnet-4-5"

    async def available(self) -> bool:
        # Will become: key present AND a cheap API ping succeeds.
        return False

    def configured(self) -> bool:
        return bool(settings.anthropic_api_key)

    async def chat_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        raise NotImplementedError(NOT_CONFIGURED_MESSAGE)
        yield  # pragma: no cover — makes this an async generator
