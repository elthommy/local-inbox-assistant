import json

import httpx
import pytest
import respx

from app.config import settings
from app.llm.ollama import OllamaClient

BASE = settings.ollama_url


def show_response(capabilities):
    return httpx.Response(200, json={"capabilities": capabilities})


def chat_stream_body(chunks):
    lines = [
        json.dumps({"message": {"content": c}, "done": False}) for c in chunks
    ]
    lines.append(json.dumps({"message": {"content": ""}, "done": True}))
    return "\n".join(lines) + "\n"


@respx.mock
async def test_available_true_false():
    route = respx.get(f"{BASE}/api/tags").mock(return_value=httpx.Response(200, json={"models": []}))
    assert await OllamaClient().available() is True
    route.mock(side_effect=httpx.ConnectError("down"))
    assert await OllamaClient().available() is False


@respx.mock
async def test_list_models():
    respx.get(f"{BASE}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "qwen3.6:latest"}, {"name": "nomic-embed-text:latest"}]})
    )
    assert await OllamaClient().list_models() == ["qwen3.6:latest", "nomic-embed-text:latest"]


@respx.mock
async def test_chat_stream_yields_tokens_and_stops_at_done():
    respx.post(f"{BASE}/api/show").mock(return_value=show_response([]))
    respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(200, text=chat_stream_body(["Hel", "lo"]))
    )
    out = [c async for c in OllamaClient().chat_stream([{"role": "user", "content": "hi"}])]
    assert out == ["Hel", "lo"]


@respx.mock
async def test_chat_stream_disables_thinking_for_capable_models():
    respx.post(f"{BASE}/api/show").mock(return_value=show_response(["thinking"]))
    chat_route = respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(200, text=chat_stream_body(["ok"]))
    )
    [c async for c in OllamaClient().chat_stream([{"role": "user", "content": "hi"}])]
    payload = json.loads(chat_route.calls[0].request.content)
    assert payload["think"] is False


@respx.mock
async def test_chat_stream_no_think_field_for_plain_models():
    respx.post(f"{BASE}/api/show").mock(return_value=show_response([]))
    chat_route = respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(200, text=chat_stream_body(["ok"]))
    )
    [c async for c in OllamaClient().chat_stream([{"role": "user", "content": "hi"}])]
    payload = json.loads(chat_route.calls[0].request.content)
    assert "think" not in payload


@respx.mock
async def test_thinking_capability_is_cached():
    show_route = respx.post(f"{BASE}/api/show").mock(return_value=show_response(["thinking"]))
    client = OllamaClient()
    assert await client._supports_thinking() is True
    assert await client._supports_thinking() is True
    assert show_route.call_count == 1


@respx.mock
async def test_chat_stream_surfaces_ollama_error():
    respx.post(f"{BASE}/api/show").mock(return_value=show_response([]))
    respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(200, text=json.dumps({"error": "model not found"}) + "\n")
    )
    with pytest.raises(RuntimeError, match="model not found"):
        [c async for c in OllamaClient().chat_stream([{"role": "user", "content": "hi"}])]


@respx.mock
async def test_chat_json_parses_content_and_sends_schema():
    respx.post(f"{BASE}/api/show").mock(return_value=show_response([]))
    route = respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(
            200, json={"message": {"content": '{"priority": "low"}'}, "done": True}
        )
    )
    schema = {"type": "object"}
    result = await OllamaClient().chat_json([{"role": "user", "content": "x"}], schema=schema)
    assert result == {"priority": "low"}
    payload = json.loads(route.calls[0].request.content)
    assert payload["format"] == schema
    assert payload["options"]["temperature"] == 0
    assert payload["stream"] is False


@respx.mock
async def test_embed_batches_and_errors():
    route = respx.post(f"{BASE}/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})
    )
    out = await OllamaClient().embed(["a", "b"])
    assert out == [[0.1, 0.2], [0.3, 0.4]]
    payload = json.loads(route.calls[0].request.content)
    assert payload["model"] == settings.embed_model
    route.mock(return_value=httpx.Response(200, json={"error": "boom"}))
    with pytest.raises(RuntimeError, match="boom"):
        await OllamaClient().embed(["a"])


def test_model_defaults_to_settings():
    assert OllamaClient().model == settings.chat_model
    assert OllamaClient("other").model == "other"
