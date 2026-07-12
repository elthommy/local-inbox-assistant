from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class ChatProvider(Protocol):
    """A chat backend. `messages` follows the OpenAI-style
    [{"role": "system"|"user"|"assistant", "content": str}] shape."""

    name: str

    async def chat_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        """Yield response text chunks."""
        ...

    async def available(self) -> bool:
        ...
