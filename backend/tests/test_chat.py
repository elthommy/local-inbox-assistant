from app import chat, rag
from app.db import get_conn
from app.llm.ollama import OllamaClient


def seed_email_with_task_and_event():
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO emails(maildir_file, sender, subject, date_utc) "
            "VALUES('a.eml', 'Sarah Chen', 'Q3', '2026-07-10T00:00:00+00:00')"
        )
        eid = cur.lastrowid
        conn.execute(
            "INSERT INTO tasks(email_id, text, due, done) VALUES(?, 'review report', 'Friday', 0)",
            (eid,),
        )
        conn.execute(
            "INSERT INTO tasks(email_id, text, done) VALUES(?, 'done task', 1)", (eid,)
        )
        conn.execute(
            "INSERT INTO events(email_id, title, date, time) VALUES(?, 'design review', '2026-07-14', '14:00')",
            (eid,),
        )
    return eid


async def test_no_context_uses_no_context_prompt():
    msgs = await chat.build_messages(
        OllamaClient(), [{"role": "user", "content": "hi"}], use_context=False
    )
    assert msgs[0]["role"] == "system"
    assert "DISABLED" in msgs[0]["content"]
    assert msgs[-1] == {"role": "user", "content": "hi"}


async def test_context_includes_excerpts_tasks_events(monkeypatch):
    seed_email_with_task_and_event()

    async def fake_search(ollama, query, top_k=None, chunks_per_email=2):
        assert query == "what is urgent?"
        return [{"email_id": 1, "text": "EXCERPT-ONE", "distance": 0.1}]

    monkeypatch.setattr(rag, "search_emails", fake_search)
    msgs = await chat.build_messages(
        OllamaClient(), [{"role": "user", "content": "what is urgent?"}], use_context=True
    )
    system = msgs[0]["content"]
    assert "EXCERPT-ONE" in system
    assert "review report" in system and "(due Friday)" in system
    assert "done task" not in system  # completed tasks excluded
    assert "design review" in system
    assert "[from Sarah Chen]" in system


async def test_context_with_empty_index(monkeypatch):
    async def fake_search(*a, **kw):
        return []

    monkeypatch.setattr(rag, "search_emails", fake_search)
    msgs = await chat.build_messages(
        OllamaClient(), [{"role": "user", "content": "q"}], use_context=True
    )
    assert "(no relevant emails found)" in msgs[0]["content"]
    assert "(none)" in msgs[0]["content"]  # tasks and events blocks


async def test_history_truncated_to_last_12(monkeypatch):
    async def fake_search(*a, **kw):
        return []

    monkeypatch.setattr(rag, "search_emails", fake_search)
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
        for i in range(30)
    ]
    msgs = await chat.build_messages(OllamaClient(), history, use_context=True)
    assert len(msgs) == 13  # system + last 12
    assert msgs[1]["content"] == "m18"
    assert msgs[-1]["content"] == "m29"


async def test_stream_answer_yields_model_chunks(monkeypatch):
    async def fake_stream(self, messages):
        assert messages[0]["role"] == "system"
        yield "Hello "
        yield "world"

    monkeypatch.setattr(OllamaClient, "chat_stream", fake_stream)
    out = [c async for c in chat.stream_answer([{"role": "user", "content": "hi"}], False)]
    assert out == ["Hello ", "world"]
