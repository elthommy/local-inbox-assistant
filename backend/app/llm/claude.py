"""Claude cloud chat provider (opt-in).

The only cloud call in the app: chat answers, when the user picks Claude in
the chat-model dropdown. Retrieval (embeddings) and email extraction always
stay on local Ollama, so email bodies only leave the machine as the excerpts
embedded in the chat prompt of a conversation the user chose to run on Claude.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import anthropic

from ..config import settings

NOT_CONFIGURED_MESSAGE = (
    "Claude (cloud) is not configured — set INBOX_ANTHROPIC_API_KEY in "
    "backend/.env or the environment and restart, or use the local Ollama "
    "model."
)

# hard cap on one answer; chat replies are short, this is generous headroom
MAX_TOKENS = 16000


def split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """Split OpenAI-style messages into (system prompt, user/assistant turns).

    The Anthropic API takes the system prompt as a separate parameter and
    rejects "system" roles inside `messages`.
    """
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    turns = [m for m in messages if m["role"] != "system"]
    return system, turns


class ClaudeClient:
    name = "claude"

    def __init__(self, model: str | None = None):
        """Bind to the configured Claude model; the SDK client is created per call."""
        self.model = model or settings.claude_model

    def configured(self) -> bool:
        """Whether an Anthropic API key is set."""
        return bool(settings.anthropic_api_key)

    async def available(self) -> bool:
        """Key present; an invalid key surfaces as a chat-time error instead."""
        return self.configured()

    def _client(self) -> anthropic.AsyncAnthropic:
        """New async SDK client bound to the configured key."""
        return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def chat_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        """Yield the answer as text chunks (adaptive thinking, not streamed)."""
        if not self.configured():
            raise RuntimeError(NOT_CONFIGURED_MESSAGE)
        system, turns = split_system(messages)
        try:
            async with self._client() as client:
                async with client.messages.stream(
                    model=self.model,
                    max_tokens=MAX_TOKENS,
                    system=system or anthropic.NOT_GIVEN,
                    thinking={"type": "adaptive"},
                    messages=turns,
                ) as stream:
                    async for text in stream.text_stream:
                        yield text
        except anthropic.AuthenticationError as exc:
            raise RuntimeError(
                "Anthropic rejected the API key — check INBOX_ANTHROPIC_API_KEY."
            ) from exc
