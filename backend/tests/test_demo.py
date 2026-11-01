"""Demo tooling: corpus date rendering, Ollama-free seeding, scripted chat and
the offline demo server."""

import asyncio
import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import app.api as api_module
import app.main as main_module
from app.db import get_conn
from app.llm.ollama import OllamaClient
from scripts import demo_chat, demo_server, seed_demo
from scripts.demo_corpus import DEMO_EMAILS, render, rendered_corpus

KEYS = {spec["key"] for spec in DEMO_EMAILS}
_MONTH_WORDS = (
    r"\b(january|february|march|april|june|july|august|september|october|"
    r"november|december|janvier|f[ée]vrier|avril|juin|juillet|ao[uû]t|"
    r"septembre|octobre|novembre|d[ée]cembre)\b"
)


def _all_strings(value):
    """Yield every string nested in a corpus entry."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _all_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _all_strings(v)


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    """Seed the demo corpus without embeddings; fail if Ollama is touched."""

    async def no_ollama(self, *a, **kw):
        raise AssertionError("seeding with --skip-embed must not call Ollama")

    monkeypatch.setattr(OllamaClient, "embed", no_ollama)
    monkeypatch.setattr(OllamaClient, "list_models", no_ollama)
    monkeypatch.setattr(demo_chat, "CHUNK_DELAY_S", 0)
    root = tmp_path / "demo"
    count = asyncio.run(seed_demo.seed(reset=False, skip_embed=True, root=root))
    return root, count


def _answer_text(question: str, **kw) -> str:
    """Collect fake_stream_answer's chunks for one user message."""

    async def collect():
        history = [{"role": "user", "content": question}]
        return "".join(
            [c async for c in demo_chat.fake_stream_answer(history, True, **kw)]
        )

    return asyncio.run(collect())


def test_render_fills_every_token_kind():
    today = date(2026, 11, 1)  # a Sunday
    text = "{fr:+4}|{frd:+4}|{frl:+0}|{frwd:+1}|{en:+2}|{ens:+9}|{wd:+1}|{month:-1}"
    assert render(text, today) == (
        "05/11|05/11/2026|dimanche 1er novembre|lundi|Tuesday 3 November|"
        "10 November|Monday|October"
    )


def test_month_token_wraps_the_year():
    assert render("{month:-1}", date(2027, 1, 10)) == "December"


def test_corpus_has_no_absolute_dates():
    for spec in DEMO_EMAILS:
        for text in _all_strings(spec):
            assert not re.search(r"\b20\d\d\b", text), (spec["key"], text)
            assert not re.search(_MONTH_WORDS, text, re.I), (spec["key"], text)


def test_corpus_keys_unique_and_threads_resolve():
    assert len(KEYS) == len(DEMO_EMAILS)
    for spec in DEMO_EMAILS:
        assert spec.get("reply_to", spec["key"]) in KEYS


def test_rendered_corpus_has_no_leftover_placeholder():
    for spec in rendered_corpus(date.today()):
        for text in _all_strings(spec):
            assert not re.search(r"\{[a-z]+:[+-]?\d+\}", text), text


def test_seed_skip_embed_builds_views_without_ollama(seeded):
    _root, count = seeded
    assert count == len(DEMO_EMAILS)
    with get_conn() as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM emails WHERE embedded = 1").fetchone()[0]
            == 0
        )
        high = conn.execute(
            "SELECT COUNT(*) FROM emails WHERE priority = 'high'"
        ).fetchone()[0]
        tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        threaded = conn.execute(
            "SELECT COUNT(*) FROM emails WHERE in_reply_to != ''"
        ).fetchone()[0]
    assert 5 <= high <= 8
    assert tasks >= 8
    assert threaded == sum(1 for s in DEMO_EMAILS if "reply_to" in s)


def test_seeded_events_all_fall_in_the_next_week(seeded):
    with get_conn() as conn:
        dates = [r["date"] for r in conn.execute("SELECT date FROM events")]
    today = date.today()
    assert len(dates) >= 6
    for raw in dates:
        day = date.fromisoformat(raw)  # normalized at storage time
        assert today < day <= today + timedelta(days=7), raw


def test_reset_refuses_a_directory_it_did_not_create(tmp_path):
    (tmp_path / "precious.txt").write_text("keep me")
    with pytest.raises(SystemExit):
        seed_demo.reset_demo_dir(seed_demo.DemoPaths(tmp_path))
    assert (tmp_path / "precious.txt").exists()


def test_demo_chat_sources_exist_and_answers_are_short():
    for entry in demo_chat.DEMO_CHAT:
        assert entry["sources"] and set(entry["sources"]) <= KEYS
        assert len(entry["answer"].split()) <= 90, entry["question"]
    assert set(demo_chat.DEMO_SUMMARIES) <= KEYS


def test_scripted_question_streams_its_answer(seeded):
    entry = demo_chat.DEMO_CHAT[1]
    text = _answer_text(entry["question"].upper().replace("?", ""))
    assert text == render(entry["answer"], date.today())


def test_unknown_question_gets_the_scripted_list(seeded):
    text = _answer_text("tell me a joke")
    assert demo_chat.DEMO_CHAT[0]["question"] in text


def test_summarize_button_uses_the_pinned_email(seeded):
    with get_conn() as conn:
        email_id = conn.execute(
            "SELECT id FROM emails WHERE maildir_file = 'INBOX/cur/syndic_ag.eml'"
        ).fetchone()["id"]
    text = _answer_text("Summarize this email", email_id=email_id)
    assert "Syndic Duval" in text and "{" not in text


def test_demo_server_serves_status_and_chat_offline(seeded, monkeypatch):
    # record the originals so monkeypatch restores them after the test
    monkeypatch.setattr(api_module, "stream_answer", api_module.stream_answer)
    monkeypatch.setattr(main_module, "run_index", main_module.run_index)
    monkeypatch.setattr(OllamaClient, "available", OllamaClient.available)
    monkeypatch.setattr(OllamaClient, "list_models_info", OllamaClient.list_models_info)
    demo_server.install_demo_patches()

    with TestClient(main_module.app, base_url="http://localhost") as client:
        status = client.get("/api/status").json()
        assert status["ollama"]["up"] and status["ollama"]["missing_models"] == []
        assert len(client.get("/api/emails?filter=priority").json()) >= 5
        question = demo_chat.DEMO_CHAT[0]["question"]
        r = client.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": question}],
                "model": "ollama",
            },
        )
    assert "event: done" in r.text and "INC-3107" in r.text


def test_scripted_question_wins_over_a_pinned_email(seeded):
    with get_conn() as conn:
        email_id = conn.execute("SELECT id FROM emails LIMIT 1").fetchone()["id"]
    entry = demo_chat.DEMO_CHAT[3]
    text = _answer_text(entry["question"], email_id=email_id)
    assert text == render(entry["answer"], date.today())
