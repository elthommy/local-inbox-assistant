import httpx
import pytest
from anthropic import NOT_GIVEN, AuthenticationError

from app.config import settings
from app.llm.claude import ClaudeClient, split_system


def test_configured_follows_api_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert ClaudeClient().configured() is False
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    assert ClaudeClient().configured() is True


async def test_available_follows_api_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert await ClaudeClient().available() is False
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    assert await ClaudeClient().available() is True


def test_default_model_from_settings():
    assert ClaudeClient().model == settings.claude_model
    assert ClaudeClient(model="claude-sonnet-5").model == "claude-sonnet-5"


def test_split_system_extracts_system_prompt():
    system, turns = split_system(
        [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
    )
    assert system == "SYS"
    assert turns == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_split_system_without_system_message():
    system, turns = split_system([{"role": "user", "content": "hi"}])
    assert system == ""
    assert turns == [{"role": "user", "content": "hi"}]


async def test_chat_stream_without_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with pytest.raises(RuntimeError, match="not configured"):
        async for _ in ClaudeClient().chat_stream([{"role": "user", "content": "hi"}]):
            pass


class FakeStream:
    """Stands in for the SDK's AsyncMessageStream (text_stream attribute)."""

    def __init__(self, chunks):
        self.text_stream = self._gen(chunks)

    async def _gen(self, chunks):
        for c in chunks:
            yield c

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeClient:
    """Stands in for AsyncAnthropic: records the stream() kwargs."""

    def __init__(self, chunks, captured):
        self.chunks, self.captured = chunks, captured
        self.messages = self

    def stream(self, **kwargs):
        self.captured.update(kwargs)
        return FakeStream(self.chunks)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


async def test_chat_stream_yields_chunks_and_splits_system(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    captured = {}
    monkeypatch.setattr(
        ClaudeClient, "_client", lambda self: FakeClient(["Hello ", "you"], captured)
    )
    out = [
        c
        async for c in ClaudeClient().chat_stream(
            [
                {"role": "system", "content": "SYS"},
                {"role": "user", "content": "hi"},
            ]
        )
    ]
    assert out == ["Hello ", "you"]
    assert captured["model"] == settings.claude_model
    assert captured["system"] == "SYS"
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["thinking"] == {"type": "adaptive"}


async def test_chat_stream_omits_system_when_absent(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    captured = {}
    monkeypatch.setattr(
        ClaudeClient, "_client", lambda self: FakeClient(["ok"], captured)
    )
    _ = [
        c async for c in ClaudeClient().chat_stream([{"role": "user", "content": "hi"}])
    ]
    assert captured["system"] is NOT_GIVEN


async def test_chat_stream_maps_auth_error(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-bad")

    class RejectingClient(FakeClient):
        """Raises the SDK auth error on stream()."""

        def stream(self, **kwargs):
            response = httpx.Response(
                401, request=httpx.Request("POST", "https://api.anthropic.com")
            )
            raise AuthenticationError("invalid x-api-key", response=response, body=None)

    monkeypatch.setattr(ClaudeClient, "_client", lambda self: RejectingClient([], {}))
    with pytest.raises(RuntimeError, match="INBOX_ANTHROPIC_API_KEY"):
        async for _ in ClaudeClient().chat_stream([{"role": "user", "content": "hi"}]):
            pass
