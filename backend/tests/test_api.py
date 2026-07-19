import pytest
from fastapi.testclient import TestClient

import app.api as api_module
import app.main as main_module
from app.llm.ollama import OllamaClient


@pytest.fixture
def client(monkeypatch):
    async def no_index(*a, **kw):
        return None

    # keep startup from indexing (and from touching Ollama) during API tests
    monkeypatch.setattr(main_module, "run_index", no_index)
    with TestClient(main_module.app) as c:
        yield c


def seed(client):
    """Two emails, one high priority with a task and an event."""
    from app.db import get_conn

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO emails(maildir_file, message_id, sender, sender_email, subject, "
            "date_utc, unread, priority, snippet, body, extracted) VALUES "
            "('a.eml', '<a@x>', 'Sarah', 'sarah@x.com', 'Q3 report', "
            "'2026-07-10T00:00:00+00:00', 1, 'high', 'snip', 'full body', 1)"
        )
        high_id = cur.lastrowid
        conn.execute(
            "INSERT INTO emails(maildir_file, sender, subject, date_utc, priority, extracted) "
            "VALUES('b.eml', 'News', 'digest', '2026-07-09T00:00:00+00:00', 'low', 1)"
        )
        conn.execute(
            "INSERT INTO tasks(email_id, text, due, done) VALUES(?, 'review', 'Fri', 0)",
            (high_id,),
        )
        conn.execute(
            "INSERT INTO events(email_id, title, date, time) VALUES(?, 'review mtg', '2026-07-14', '10:00')",
            (high_id,),
        )
    return high_id


class TestStatus:
    def test_status_shape(self, client, monkeypatch):
        async def up(self):
            return True

        async def models_info(self):
            return [
                {"name": "qwen3:8b", "size": 5_200_000_000},
                {"name": "nomic-embed-text:latest", "size": 274_000_000},
            ]

        monkeypatch.setattr(OllamaClient, "available", up)
        monkeypatch.setattr(OllamaClient, "list_models_info", models_info)
        data = client.get("/api/status").json()
        assert data["ollama"]["up"] is True
        assert data["ollama"]["chat_model_pulled"] is True
        assert data["ollama"]["extraction_model_pulled"] is True
        # embedding models are filtered out of the selectable list
        assert data["ollama"]["models"] == [{"name": "qwen3:8b", "size": 5_200_000_000}]
        assert data["claude"] == {"configured": False, "implemented": False}
        assert data["index"]["emails"] == 0
        assert data["index"]["progress"]["phase"] in ("idle", "error")

    def test_status_ollama_down(self, client, monkeypatch):
        async def down(self):
            return False

        monkeypatch.setattr(OllamaClient, "available", down)
        data = client.get("/api/status").json()
        assert data["ollama"]["up"] is False
        assert data["ollama"]["chat_model_pulled"] is False
        assert data["ollama"]["extraction_model_pulled"] is False
        assert data["ollama"]["models"] == []


class TestStatsAndLists:
    def test_stats(self, client):
        seed(client)
        assert client.get("/api/stats").json() == {
            "unread": 1,
            "high_priority": 1,
        }

    def test_emails_all_sorted_desc(self, client):
        seed(client)
        data = client.get("/api/emails?filter=all").json()
        assert [e["subject"] for e in data] == ["Q3 report", "digest"]
        assert data[0]["unread"] is True
        assert "body" not in data[0]  # list view stays light

    def test_emails_priority_filter(self, client):
        seed(client)
        data = client.get("/api/emails?filter=priority").json()
        assert len(data) == 1
        assert data[0]["priority"] == "high"
        # chips embedded
        assert data[0]["tasks"][0]["text"] == "review"
        assert data[0]["events"][0]["title"] == "review mtg"

    def test_email_detail_includes_body(self, client):
        eid = seed(client)
        data = client.get(f"/api/emails/{eid}").json()
        assert data["body"] == "full body"

    def test_email_detail_404(self, client):
        assert client.get("/api/emails/999").status_code == 404

    def test_email_body_markdown_from_source_eml(self, client):
        eid = seed(client)
        from app.config import settings

        (settings.maildir / "a.eml").write_bytes(
            b"From: sarah@x.com\nSubject: Q3 report\n"
            b"Date: Fri, 10 Jul 2026 00:00:00 +0000\n"
            b"Content-Type: text/html; charset=utf-8\n\n"
            b"<h1>Q3</h1><p>numbers look <b>good</b></p>"
            b'<img src="https://t.example.com/p.gif">'
        )
        data = client.get(f"/api/emails/{eid}/body").json()
        assert data["format"] == "markdown"
        assert data["degraded"] is False
        assert "# Q3" in data["body"]
        assert "**good**" in data["body"]
        assert "t.example.com" not in data["body"]  # images stripped

    def test_email_body_falls_back_to_stored_text(self, client):
        # source .eml missing (or plain text): the stored body is returned
        eid = seed(client)
        data = client.get(f"/api/emails/{eid}/body").json()
        assert data == {
            "id": eid,
            "format": "text",
            "body": "full body",
            "degraded": False,
        }

    def test_email_body_degraded_falls_back_unless_forced(self, client):
        eid = seed(client)
        from app.config import settings

        # wall of tracking links: the degradation heuristic trips
        links = "".join(
            f'<a href="https://t.x.com/c?id={i}&tok=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa">Shop</a> '
            for i in range(10)
        )
        (settings.maildir / "a.eml").write_bytes(
            b"From: sarah@x.com\nSubject: Q3 report\n"
            b"Date: Fri, 10 Jul 2026 00:00:00 +0000\n"
            b"Content-Type: text/html; charset=utf-8\n\n"
            b"<p>" + links.encode() + b"</p>"
        )
        data = client.get(f"/api/emails/{eid}/body").json()
        assert data == {
            "id": eid,
            "format": "text",
            "body": "full body",
            "degraded": True,
        }
        # the "render anyway" override returns the markdown after all
        forced = client.get(f"/api/emails/{eid}/body?force_markdown=true").json()
        assert forced["format"] == "markdown"
        assert forced["degraded"] is True
        assert "[Shop](https://t.x.com" in forced["body"]

    def test_email_body_404(self, client):
        assert client.get("/api/emails/999/body").status_code == 404

    def test_tasks_include_source(self, client):
        eid = seed(client)
        data = client.get("/api/tasks").json()
        assert data[0]["source"] == "Sarah"
        assert data[0]["done"] is False
        assert data[0]["email_id"] == eid  # lets the UI dismiss the source email

    def test_events_include_source(self, client):
        eid = seed(client)
        data = client.get("/api/events").json()
        assert data[0]["source"] == "Sarah"
        assert data[0]["date"] == "2026-07-14"
        assert data[0]["email_id"] == eid


class TestTaskToggle:
    def test_toggle_roundtrip(self, client):
        seed(client)
        task_id = client.get("/api/tasks").json()[0]["id"]
        assert client.post(f"/api/tasks/{task_id}/toggle").json()["done"] is True
        assert client.post(f"/api/tasks/{task_id}/toggle").json()["done"] is False

    def test_toggle_404(self, client):
        assert client.post("/api/tasks/999/toggle").status_code == 404


class TestHandledEmails:
    def test_completing_all_tasks_removes_email_from_priority(self, client):
        seed(client)
        task_id = client.get("/api/tasks").json()[0]["id"]
        client.post(f"/api/tasks/{task_id}/toggle")
        assert client.get("/api/emails?filter=priority").json() == []
        assert client.get("/api/stats").json()["high_priority"] == 0
        # unchecking the task brings it back
        client.post(f"/api/tasks/{task_id}/toggle")
        assert len(client.get("/api/emails?filter=priority").json()) == 1
        assert client.get("/api/stats").json()["high_priority"] == 1

    def test_open_task_remaining_keeps_email_in_priority(self, client):
        eid = seed(client)
        from app.db import get_conn

        with get_conn() as conn:
            conn.execute(
                "INSERT INTO tasks(email_id, text, done) VALUES(?, 'second', 0)", (eid,)
            )
        task_id = client.get("/api/tasks").json()[0]["id"]
        client.post(f"/api/tasks/{task_id}/toggle")
        assert len(client.get("/api/emails?filter=priority").json()) == 1

    def test_email_without_tasks_stays_in_priority(self, client):
        seed(client)
        from app.db import get_conn

        with get_conn() as conn:
            conn.execute(
                "INSERT INTO emails(maildir_file, sender, subject, date_utc, priority, extracted) "
                "VALUES('c.eml', 'Boss', 'reply please', '2026-07-11T00:00:00+00:00', 'high', 1)"
            )
        assert len(client.get("/api/emails?filter=priority").json()) == 2


class TestDismiss:
    def test_dismiss_toggle_roundtrip(self, client):
        eid = seed(client)
        assert client.post(f"/api/emails/{eid}/dismiss").json()["dismissed"] is True
        assert client.post(f"/api/emails/{eid}/dismiss").json()["dismissed"] is False

    def test_dismiss_404(self, client):
        assert client.post("/api/emails/999/dismiss").status_code == 404

    def test_dismissed_hidden_from_triage_but_kept_in_all(self, client):
        eid = seed(client)
        client.post(f"/api/emails/{eid}/dismiss")
        assert client.get("/api/emails?filter=priority").json() == []
        assert client.get("/api/tasks").json() == []
        assert client.get("/api/events").json() == []
        assert client.get("/api/stats").json()["high_priority"] == 0
        all_mail = client.get("/api/emails?filter=all").json()
        flags = {e["subject"]: e["dismissed"] for e in all_mail}
        assert flags == {"Q3 report": True, "digest": False}


class TestMuteSender:
    def test_mute_toggle_roundtrip(self, client):
        seed(client)
        r = client.post(
            "/api/senders/mute", json={"sender_email": "Sarah@X.com"}
        ).json()
        assert r == {"sender_email": "sarah@x.com", "muted": True}
        assert (
            client.get("/api/senders/muted").json()[0]["sender_email"] == "sarah@x.com"
        )
        r = client.post(
            "/api/senders/mute", json={"sender_email": "sarah@x.com"}
        ).json()
        assert r["muted"] is False
        assert client.get("/api/senders/muted").json() == []

    def test_mute_requires_sender(self, client):
        assert (
            client.post("/api/senders/mute", json={"sender_email": "  "}).status_code
            == 400
        )

    def test_muted_hidden_from_triage_but_kept_in_all(self, client):
        seed(client)
        client.post("/api/senders/mute", json={"sender_email": "sarah@x.com"})
        assert client.get("/api/emails?filter=priority").json() == []
        assert client.get("/api/tasks").json() == []
        assert client.get("/api/events").json() == []
        assert client.get("/api/stats").json()["high_priority"] == 0
        all_mail = client.get("/api/emails?filter=all").json()
        flags = {e["subject"]: e["muted"] for e in all_mail}
        assert flags == {"Q3 report": True, "digest": False}

    def test_unmute_restores_triage(self, client):
        seed(client)
        client.post("/api/senders/mute", json={"sender_email": "sarah@x.com"})
        client.post("/api/senders/mute", json={"sender_email": "sarah@x.com"})
        assert len(client.get("/api/emails?filter=priority").json()) == 1
        assert len(client.get("/api/tasks").json()) == 1


class TestSettings:
    DEFAULTS = {
        "window_days": 90,
        "extraction_window_days": 14,
        "extraction_max_emails": 300,
        "chat_model": "qwen3:8b",
        "extraction_model": "qwen3:8b",
    }

    def _restore(self, monkeypatch):
        from app.config import settings

        for key, value in self.DEFAULTS.items():
            monkeypatch.setattr(settings, key, value)
        return settings

    def test_read_defaults(self, client, monkeypatch):
        self._restore(monkeypatch)
        assert client.get("/api/settings").json() == self.DEFAULTS

    def test_update_persists_and_applies(self, client, monkeypatch):
        settings = self._restore(monkeypatch)
        r = client.post("/api/settings", json={"extraction_window_days": 30}).json()
        assert r["extraction_window_days"] == 30
        assert r["window_days"] == 90  # untouched fields keep their value
        assert settings.extraction_window_days == 30  # applied immediately
        assert client.get("/api/settings").json()["extraction_window_days"] == 30

    def test_override_reapplied_on_startup(self, client, monkeypatch):
        from app.db import apply_setting_overrides

        settings = self._restore(monkeypatch)
        client.post("/api/settings", json={"window_days": 120})
        settings.window_days = 90  # simulate a fresh process
        apply_setting_overrides()
        assert settings.window_days == 120

    def test_rejects_invalid_values(self, client, monkeypatch):
        self._restore(monkeypatch)
        assert client.post("/api/settings", json={"window_days": 0}).status_code == 422
        assert (
            client.post("/api/settings", json={"extraction_max_emails": -5}).status_code
            == 422
        )
        assert client.post("/api/settings", json={"chat_model": ""}).status_code == 422

    def test_update_models_persists_and_applies(self, client, monkeypatch):
        from app.db import apply_setting_overrides

        settings = self._restore(monkeypatch)
        r = client.post(
            "/api/settings",
            json={"chat_model": "gemma3:12b-it-qat", "extraction_model": "qwen3:4b"},
        ).json()
        assert r["chat_model"] == "gemma3:12b-it-qat"
        assert r["extraction_model"] == "qwen3:4b"
        assert settings.chat_model == "gemma3:12b-it-qat"  # applied immediately
        settings.chat_model = "qwen3:8b"  # simulate a fresh process
        apply_setting_overrides()
        assert settings.chat_model == "gemma3:12b-it-qat"


class TestReindex:
    def test_reindex_starts(self, client, monkeypatch):
        started = []

        async def fake_run():
            started.append(True)

        monkeypatch.setattr(api_module.indexer, "run_index", fake_run)
        assert client.post("/api/reindex").json()["started"] is True

    def test_reindex_refused_while_running(self, client, monkeypatch):
        monkeypatch.setitem(api_module.indexer.progress, "phase", "embedding")
        data = client.post("/api/reindex").json()
        assert data["started"] is False
        assert data["progress"]["phase"] == "embedding"


class TestReextract:
    def test_reextract_resets_window_and_starts(self, client, monkeypatch):
        from app.db import get_conn

        seed(client)  # both seeded emails are inside the extraction window
        started = []

        async def fake_run():
            started.append(True)

        monkeypatch.setattr(api_module.indexer, "run_index", fake_run)
        data = client.post("/api/reextract").json()
        assert data["started"] is True
        assert data["reset"] == 2
        with get_conn() as conn:
            flags = [
                r["extracted"] for r in conn.execute("SELECT extracted FROM emails")
            ]
        assert flags == [0, 0]

    def test_reextract_refused_while_running(self, client, monkeypatch):
        monkeypatch.setitem(api_module.indexer.progress, "phase", "extracting")
        data = client.post("/api/reextract").json()
        assert data["started"] is False


class TestChat:
    def test_requires_user_last_message(self, client):
        r = client.post("/api/chat", json={"messages": [], "model": "ollama"})
        assert r.status_code == 400
        r = client.post(
            "/api/chat",
            json={
                "messages": [{"role": "assistant", "content": "x"}],
                "model": "ollama",
            },
        )
        assert r.status_code == 400

    def test_claude_returns_error_event(self, client):
        r = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hi"}], "model": "claude"},
        )
        assert r.status_code == 200
        assert "event: error" in r.text
        assert "not implemented yet" in r.text

    def test_streams_tokens_then_done(self, client, monkeypatch):
        async def fake_answer(history, use_context, email_id=None):
            assert use_context is True
            assert email_id is None
            yield "Hello "
            yield "you"

        monkeypatch.setattr(api_module, "stream_answer", fake_answer)
        r = client.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "model": "ollama",
                "use_context": True,
            },
        )
        assert r.headers["content-type"].startswith("text/event-stream")
        assert 'data: {"token": "Hello "}' in r.text
        assert 'data: {"token": "you"}' in r.text
        assert "event: done" in r.text

    def test_email_id_forwarded_to_stream_answer(self, client, monkeypatch):
        seen = {}

        async def fake_answer(history, use_context, email_id=None):
            seen["email_id"] = email_id
            yield "ok"

        monkeypatch.setattr(api_module, "stream_answer", fake_answer)
        r = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hi"}], "email_id": 7},
        )
        assert "event: done" in r.text
        assert seen["email_id"] == 7

    def test_stream_failure_emits_error_event(self, client, monkeypatch):
        async def broken(history, use_context, email_id=None):
            yield "partial"
            raise RuntimeError("ollama died")

        monkeypatch.setattr(api_module, "stream_answer", broken)
        r = client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "hi"}], "model": "ollama"},
        )
        assert 'data: {"token": "partial"}' in r.text
        assert "event: error" in r.text
        assert "ollama died" in r.text
