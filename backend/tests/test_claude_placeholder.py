import pytest

from app.config import settings
from app.llm.claude import NOT_CONFIGURED_MESSAGE, ClaudeClient


async def test_not_available():
    assert await ClaudeClient().available() is False


def test_configured_follows_api_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert ClaudeClient().configured() is False
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    assert ClaudeClient().configured() is True


async def test_chat_stream_raises_not_implemented():
    with pytest.raises(NotImplementedError, match="second step"):
        async for _ in ClaudeClient().chat_stream([{"role": "user", "content": "hi"}]):
            pass


def test_placeholder_message_mentions_ollama():
    assert "Ollama" in NOT_CONFIGURED_MESSAGE
