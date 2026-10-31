from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from ..config import settings
from .errors import UserFacingError


def model_pulled(model: str, pulled: list[str]) -> bool:
    """Whether a model name (with or without tag) is among the pulled models."""
    return any(m == model or m.startswith(model + ":") for m in pulled)


def not_pulled_message(model: str) -> str:
    """User-facing hint for a model missing from the Ollama server."""
    return f"model {model} is not pulled in Ollama — run `ollama pull {model}`"


class OllamaClient:
    name = "ollama"

    # class-level cache: model name -> supports "thinking"
    _thinking_cache: dict[str, bool] = {}

    def __init__(self, model: str | None = None):
        """Bind to the configured Ollama URL, defaulting to the chat model."""
        self.base_url = settings.ollama_url.rstrip("/")
        self.model = model or settings.chat_model

    async def _supports_thinking(self) -> bool:
        """Thinking-capable models (qwen3 family, deepseek-r1…) emit a
        reasoning preamble by default; we turn it off for latency. The
        `think` field errors on models without the capability, so probe."""
        cached = self._thinking_cache.get(self.model)
        if cached is not None:
            return cached
        supports = False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    f"{self.base_url}/api/show", json={"model": self.model}
                )
                r.raise_for_status()
                supports = "thinking" in r.json().get("capabilities", [])
        except httpx.HTTPError:
            pass
        self._thinking_cache[self.model] = supports
        return supports

    async def available(self) -> bool:
        """Whether the Ollama server answers (short timeout, never raises)."""
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def list_models(self) -> list[str]:
        """Names of the models pulled on the Ollama server."""
        return [m["name"] for m in await self.list_models_info()]

    async def list_models_info(self) -> list[dict]:
        """Name and size in bytes of each model pulled on the Ollama server."""
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{self.base_url}/api/tags")
            r.raise_for_status()
            return [
                {"name": m["name"], "size": m.get("size", 0)}
                for m in r.json().get("models", [])
            ]

    async def pull(self, model: str, on_progress=None) -> None:
        """Download a model via Ollama's streaming /api/pull.

        on_progress(completed_bytes, total_bytes) is called per status line
        that carries sizes (one layer at a time).
        """
        timeout = httpx.Timeout(300, connect=10)  # read timeout = stall guard
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/pull", json={"model": model}
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if err := data.get("error"):
                        raise UserFacingError(f"ollama pull {model}: {err}")
                    if on_progress and data.get("total"):
                        on_progress(data.get("completed", 0), data["total"])

    async def chat_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        """Yield the model's answer as text chunks (thinking disabled)."""
        payload = {"model": self.model, "messages": messages, "stream": True}
        if await self._supports_thinking():
            payload["think"] = False
        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=10)) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as resp:
                if resp.status_code == 404:  # Ollama: model not found
                    raise UserFacingError(not_pulled_message(self.model))
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if err := data.get("error"):
                        raise UserFacingError(f"ollama: {err}")
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break

    async def chat_json(self, messages: list[dict], schema: dict | None = None) -> dict:
        """Non-streaming chat constrained to JSON output (for extraction)."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": schema or "json",
            "options": {"temperature": 0},
        }
        if await self._supports_thinking():
            payload["think"] = False
        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=10)) as client:
            r = await client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
            if err := data.get("error"):
                raise UserFacingError(f"ollama: {err}")
            return json.loads(data["message"]["content"])

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts with the configured embedding model, one vector each."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10)) as client:
            r = await client.post(
                f"{self.base_url}/api/embed",
                json={"model": settings.embed_model, "input": texts},
            )
            r.raise_for_status()
            data = r.json()
            if err := data.get("error"):
                raise UserFacingError(f"ollama: {err}")
            return data["embeddings"]
