import pytest

from app import chat, rag
from app.config import settings
from app.db import get_conn
from app.llm.claude import ClaudeClient
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
        OllamaClient(),
        [{"role": "user", "content": "what is urgent?"}],
        use_context=True,
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


def set_body(email_id, body):
    with get_conn() as conn:
        conn.execute(
            "UPDATE emails SET body = ?, sender_email = 'sarah@x.com' WHERE id = ?",
            (body, email_id),
        )


async def test_email_focus_pinned_with_context(monkeypatch):
    eid = seed_email_with_task_and_event()
    set_body(eid, "FULL-BODY-TEXT")

    async def fake_search(*a, **kw):
        return []

    monkeypatch.setattr(rag, "search_emails", fake_search)
    msgs = await chat.build_messages(
        OllamaClient(),
        [{"role": "user", "content": "summarize"}],
        use_context=True,
        email_id=eid,
    )
    system = msgs[0]["content"]
    assert "## Email in focus" in system
    assert "FULL-BODY-TEXT" in system
    assert "sarah@x.com" in system
    assert "## Retrieved email excerpts" in system  # RAG context still present


async def test_email_focus_overrides_context_off():
    eid = seed_email_with_task_and_event()
    set_body(eid, "FULL-BODY-TEXT")
    # no rag monkeypatch needed: with use_context off no search must happen
    msgs = await chat.build_messages(
        OllamaClient(),
        [{"role": "user", "content": "summarize"}],
        use_context=False,
        email_id=eid,
    )
    system = msgs[0]["content"]
    assert "FULL-BODY-TEXT" in system
    assert "inbox context is off" in system
    assert "DISABLED" not in system


async def test_email_focus_long_body_truncated(monkeypatch):
    eid = seed_email_with_task_and_event()
    set_body(eid, "x" * (chat.FOCUS_BODY_MAX_CHARS + 500))
    msgs = await chat.build_messages(
        OllamaClient(),
        [{"role": "user", "content": "q"}],
        use_context=False,
        email_id=eid,
    )
    system = msgs[0]["content"]
    assert "[… truncated …]" in system
    assert "x" * (chat.FOCUS_BODY_MAX_CHARS + 500) not in system


async def test_email_focus_unknown_id_falls_back_to_no_context():
    msgs = await chat.build_messages(
        OllamaClient(),
        [{"role": "user", "content": "q"}],
        use_context=False,
        email_id=999999,
    )
    assert "DISABLED" in msgs[0]["content"]


async def test_stream_answer_yields_model_chunks(monkeypatch):
    async def fake_stream(self, messages):
        assert messages[0]["role"] == "system"
        yield "Hello "
        yield "world"

    monkeypatch.setattr(OllamaClient, "chat_stream", fake_stream)
    out = [
        c async for c in chat.stream_answer([{"role": "user", "content": "hi"}], False)
    ]
    assert out == ["Hello ", "world"]


async def test_stream_answer_routes_to_claude(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")

    async def fake_claude_stream(self, messages):
        assert messages[0]["role"] == "system"
        yield "from claude"

    monkeypatch.setattr(ClaudeClient, "chat_stream", fake_claude_stream)
    out = [
        c
        async for c in chat.stream_answer(
            [{"role": "user", "content": "hi"}], False, provider="claude"
        )
    ]
    assert out == ["from claude"]


async def test_stream_answer_claude_unconfigured_fails_fast(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    async def no_search(*a, **kw):
        raise AssertionError("retrieval must not run when Claude is unconfigured")

    monkeypatch.setattr(rag, "search_emails", no_search)
    with pytest.raises(RuntimeError, match="not configured"):
        async for _ in chat.stream_answer(
            [{"role": "user", "content": "hi"}], True, provider="claude"
        ):
            pass
