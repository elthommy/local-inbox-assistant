import pytest

from app import rag
from app.llm.ollama import OllamaClient


def email(i, body):
    return {
        "id": i,
        "sender": f"Sender {i}",
        "sender_email": f"s{i}@example.com",
        "subject": f"Subject {i}",
        "date_utc": "2026-07-10T00:00:00+00:00",
        "body": body,
    }


async def test_index_and_search_roundtrip(fake_embed):
    o = OllamaClient()
    n = await rag.index_emails(o, [email(1, "hello"), email(2, "goodbye")])
    assert n == 2
    assert rag.chunk_count() == 2
    hits = await rag.search(o, "hello", top_k=2)
    assert len(hits) == 2
    assert {h["email_id"] for h in hits} == {1, 2}
    assert all("distance" in h and "text" in h for h in hits)


async def test_search_empty_index(fake_embed):
    assert await rag.search(OllamaClient(), "anything") == []


async def test_upsert_is_idempotent(fake_embed):
    o = OllamaClient()
    await rag.index_emails(o, [email(1, "hello")])
    await rag.index_emails(o, [email(1, "hello")])
    assert rag.chunk_count() == 1


async def test_index_no_emails(fake_embed):
    assert await rag.index_emails(OllamaClient(), []) == 0


async def test_delete_emails(fake_embed):
    o = OllamaClient()
    await rag.index_emails(o, [email(1, "one"), email(2, "two")])
    rag.delete_emails([1])
    assert rag.chunk_count() == 1
    hits = await rag.search(o, "one", top_k=2)
    assert {h["email_id"] for h in hits} == {2}


class TestSearchEmailsDedup:
    """search_emails must group chunk hits into distinct emails."""

    @pytest.fixture
    def patched_search(self, monkeypatch):
        hits = [
            {"email_id": 1, "text": "chunk 1a", "distance": 0.1},
            {"email_id": 1, "text": "chunk 1b", "distance": 0.2},
            {"email_id": 1, "text": "chunk 1c", "distance": 0.25},
            {"email_id": 2, "text": "chunk 2a", "distance": 0.3},
            {"email_id": 3, "text": "chunk 3a", "distance": 0.4},
        ]

        async def fake_search(ollama, query, top_k=None):
            return hits

        monkeypatch.setattr(rag, "search", fake_search)

    async def test_groups_by_email(self, patched_search):
        out = await rag.search_emails(OllamaClient(), "q", top_k=2)
        assert [o["email_id"] for o in out] == [1, 2]

    async def test_caps_chunks_per_email(self, patched_search):
        out = await rag.search_emails(OllamaClient(), "q", top_k=3, chunks_per_email=2)
        best = out[0]
        assert "chunk 1a" in best["text"] and "chunk 1b" in best["text"]
        assert "chunk 1c" not in best["text"]

    async def test_keeps_best_distance(self, patched_search):
        out = await rag.search_emails(OllamaClient(), "q", top_k=3)
        assert out[0]["distance"] == 0.1
