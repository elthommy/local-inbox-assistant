"""ChromaDB vector store over email body chunks, embedded via Ollama."""

from __future__ import annotations

import chromadb

from .config import settings
from .llm.ollama import OllamaClient

_client: chromadb.ClientAPI | None = None


def get_collection() -> chromadb.Collection:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(settings.chroma_path))
    return _client.get_or_create_collection(
        "emails", metadata={"hnsw:space": "cosine"}
    )


def chunk_text(text: str) -> list[str]:
    size, overlap = settings.chunk_size, settings.chunk_overlap
    if len(text) <= size:
        return [text] if text.strip() else []
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        if end >= len(text):
            # last piece: emit the remainder and stop (never re-slice a tail
            # shorter than the overlap, which would loop with tiny advances)
            tail = text[start:]
            if tail.strip():
                chunks.append(tail)
            break
        chunk = text[start:end]
        # prefer to break on a paragraph/sentence boundary in the tail
        for sep in ("\n\n", "\n", ". "):
            cut = chunk.rfind(sep, size // 2)
            if cut != -1:
                chunk = chunk[: cut + len(sep)]
                break
        if chunk.strip():
            chunks.append(chunk)
        start += max(len(chunk) - overlap, 1)
    return chunks


def email_to_chunks(email_row: dict) -> tuple[list[str], list[str], list[dict]]:
    """Build (ids, documents, metadatas) for one email. The header line is
    prepended to each chunk so retrieval hits carry sender/date context."""
    header = (
        f"From: {email_row['sender']} <{email_row['sender_email']}>\n"
        f"Subject: {email_row['subject']}\n"
        f"Date: {email_row['date_utc'][:10]}\n\n"
    )
    body_chunks = chunk_text(email_row["body"]) or [""]
    ids, docs, metas = [], [], []
    for i, chunk in enumerate(body_chunks):
        ids.append(f"{email_row['id']}:{i}")
        docs.append(header + chunk)
        metas.append({"email_id": email_row["id"], "chunk": i})
    return ids, docs, metas


async def index_emails(ollama: OllamaClient, email_rows: list[dict]) -> int:
    """Embed and upsert chunks for the given emails. Returns chunk count."""
    coll = get_collection()
    all_ids, all_docs, all_metas = [], [], []
    for row in email_rows:
        ids, docs, metas = email_to_chunks(row)
        all_ids += ids
        all_docs += docs
        all_metas += metas
    if not all_docs:
        return 0
    embeddings = []
    batch = 32
    for i in range(0, len(all_docs), batch):
        embeddings += await ollama.embed(all_docs[i : i + batch])
    coll.upsert(ids=all_ids, documents=all_docs, embeddings=embeddings, metadatas=all_metas)
    return len(all_docs)


async def search(ollama: OllamaClient, query: str, top_k: int | None = None) -> list[dict]:
    """Return the best-matching chunks: [{email_id, text, distance}]."""
    coll = get_collection()
    if coll.count() == 0:
        return []
    [embedding] = await ollama.embed([query])
    res = coll.query(
        query_embeddings=[embedding],
        n_results=min(top_k or settings.rag_top_k, coll.count()),
    )
    out = []
    for doc, meta, dist in zip(
        res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        out.append({"email_id": meta["email_id"], "text": doc, "distance": dist})
    return out


async def search_emails(
    ollama: OllamaClient,
    query: str,
    top_k: int | None = None,
    chunks_per_email: int = 2,
) -> list[dict]:
    """Like search(), but grouped per email: returns up to top_k distinct
    emails (best-first), each with its best chunks joined as `text`."""
    top_k = top_k or settings.rag_top_k
    hits = await search(ollama, query, top_k * 4)
    grouped: dict[int, dict] = {}
    for h in hits:  # hits are ordered best-first
        g = grouped.setdefault(
            h["email_id"], {"email_id": h["email_id"], "chunks": [], "distance": h["distance"]}
        )
        if len(g["chunks"]) < chunks_per_email:
            g["chunks"].append(h["text"])
    out = []
    for g in list(grouped.values())[:top_k]:
        out.append(
            {
                "email_id": g["email_id"],
                "text": "\n[…]\n".join(g["chunks"]),
                "distance": g["distance"],
            }
        )
    return out


def chunk_count() -> int:
    return get_collection().count()


def delete_emails(email_ids: list[int]) -> None:
    if email_ids:
        get_collection().delete(where={"email_id": {"$in": email_ids}})
