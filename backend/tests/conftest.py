"""Shared fixtures: every test runs against a temp maildir, temp SQLite DB and
temp Chroma store — the real mailbox and index are never touched."""

import pytest

from app import rag
from app.config import settings
from app.db import init_db
from app.llm.ollama import OllamaClient


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    maildir = tmp_path / "mail"
    maildir.mkdir()
    monkeypatch.setattr(settings, "maildir", maildir)
    monkeypatch.setattr(settings, "db_path", tmp_path / "inbox.db")
    monkeypatch.setattr(settings, "chroma_path", tmp_path / "chroma")
    rag._client = None
    OllamaClient._thinking_cache.clear()
    init_db()
    yield
    rag._client = None


@pytest.fixture
def fake_embed(monkeypatch):
    """Deterministic, network-free embeddings (8 dims, derived from text)."""

    async def embed(self, texts):
        return [[((hash(t) >> (4 * i)) % 97) / 97.0 for i in range(8)] for t in texts]

    monkeypatch.setattr(OllamaClient, "embed", embed)
    return embed
