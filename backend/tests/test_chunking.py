from app.config import settings
from app.rag import chunk_text, email_to_chunks


class TestChunkText:
    def test_empty(self):
        assert chunk_text("") == []
        assert chunk_text("   \n ") == []

    def test_short_text_single_chunk(self):
        assert chunk_text("hello world") == ["hello world"]

    def test_exact_size_single_chunk(self):
        text = "x" * settings.chunk_size
        assert chunk_text(text) == [text]

    def test_long_text_splits_with_overlap(self):
        text = ("word " * 300).strip()  # ~1500 chars
        chunks = chunk_text(text)
        assert len(chunks) >= 2
        # consecutive chunks overlap
        assert chunks[1].split()[0] in chunks[0]

    def test_reconstruction_covers_whole_text(self):
        text = "".join(f"paragraph {i}.\n\n" for i in range(200))
        chunks = chunk_text(text)
        # last chunk must reach the end of the text
        assert text.rstrip().endswith(chunks[-1].rstrip()[-50:])

    def test_prefers_paragraph_boundary(self):
        para = "a" * 800 + "\n\n" + "b" * 800
        chunks = chunk_text(para)
        assert chunks[0].endswith("\n\n")

    def test_no_tiny_tail_spin(self):
        """Regression: tails shorter than the overlap used to produce ~150
        shrinking micro-chunks per email (advance clamped to 1)."""
        # length chosen so the remainder after the first chunk is < overlap
        text = "y" * (settings.chunk_size + settings.chunk_overlap // 2)
        chunks = chunk_text(text)
        assert len(chunks) <= 2

    def test_bounded_chunk_count(self):
        # 20k chars can never legitimately produce more than ~40 chunks
        text = "line of text here\n" * 1200  # ~21k chars
        assert len(chunk_text(text)) < 40

    def test_whitespace_only_chunks_dropped(self):
        text = "a" * 1100 + "\n\n" + " " * 400
        for c in chunk_text(text):
            assert c.strip()


class TestEmailToChunks:
    EMAIL = {
        "id": 42,
        "sender": "Sarah Chen",
        "sender_email": "sarah@example.com",
        "subject": "Q3 report",
        "date_utc": "2026-07-10T07:14:00+00:00",
        "body": "please review the numbers",
    }

    def test_header_prepended(self):
        ids, docs, metas = email_to_chunks(self.EMAIL)
        assert ids == ["42:0"]
        assert docs[0].startswith("From: Sarah Chen <sarah@example.com>\n")
        assert "Subject: Q3 report" in docs[0]
        assert "Date: 2026-07-10" in docs[0]
        assert docs[0].endswith("please review the numbers")
        assert metas[0] == {"email_id": 42, "chunk": 0}

    def test_empty_body_still_produces_header_chunk(self):
        ids, docs, _ = email_to_chunks({**self.EMAIL, "body": ""})
        assert len(ids) == 1
        assert "Subject: Q3 report" in docs[0]

    def test_long_body_multiple_ids(self):
        long = {**self.EMAIL, "body": "text " * 1000}
        ids, docs, metas = email_to_chunks(long)
        assert len(ids) == len(docs) == len(metas) >= 2
        assert ids[1] == "42:1"
        # every chunk carries the header for retrieval context
        assert all(d.startswith("From: ") for d in docs)
