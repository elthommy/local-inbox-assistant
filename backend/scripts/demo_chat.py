"""Scripted chat answers for demo recordings: no model, same output each take.

`fake_stream_answer` has the signature and output of `app.chat.stream_answer`
(an async iterator of text chunks), so `scripts.demo_server` can swap it in.
It answers:

- a typed question that matches a `DEMO_CHAT` entry (case, accents and
  punctuation ignored),
- the "summarize" button on an email listed in `DEMO_SUMMARIES`,
- anything else with a short note listing the scripted questions.

Answers use only facts present in demo_corpus and the same `{token:offset}`
date placeholders, rendered when the answer is streamed. `sources` lists the
corpus keys each answer relies on; tests check they exist (the UI does not
display sources).
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

from app.db import get_conn
from scripts.demo_corpus import render

# pause between streamed chunks, close to a local model's token rate
CHUNK_DELAY_S = 0.035

DEMO_CHAT = [
    {
        "question": "What needs my attention today?",
        "aliases": ["What needs my attention?", "What should I do today?"],
        "answer": (
            "Five things can't wait today:\n\n"
            "- **INC-3107**: checkout-api is back after Priya's 08:12 rollback; "
            "she needs the status page summary **before noon**.\n"
            "- **Sarah Whitfield**: {month:-1} infra cost and quarterly uptime "
            "for the board deck, **by 16:00**.\n"
            "- **Gitforge Security**: revoke the payments API key leaked in "
            "`northwind/api`.\n"
            "- **Signly**: the Acme MSA renewal expires **tonight at 23:59**.\n"
            "- **Finances publiques**: taxe foncière, 1 284 €, due **{fr:+4}**."
        ),
        "sources": [
            "incident_update",
            "board_numbers",
            "token_leak",
            "msa_signature",
            "tax_notice",
        ],
    },
    {
        "question": "Qu'est-ce que je dois faire pour l'AG de copropriété ?",
        "aliases": ["Que dois-je faire pour l'AG ?", "Et pour l'AG ?"],
        "answer": (
            "L'AG a lieu le **{frl:+6} à 18h30**, salle polyvalente "
            "(Syndic Duval).\n\n"
            "- Si vous ne venez pas : **retournez votre pouvoir signé avant le "
            "{frl:+5}**.\n"
            "- **Hélène (lot 12)** veut vous confier son pouvoir et propose de "
            "demander un **second devis**.\n"
            "- Point clé : résolution n°7, ravalement à **186 000 €** "
            "(environ 4 100 € pour votre lot)."
        ),
        "sources": ["syndic_ag", "syndic_neighbour"],
    },
    {
        "question": "Summarize the INC-3107 thread",
        "aliases": ["Summarize the incident", "What happened with INC-3107?"],
        "answer": (
            "- **What happened:** checkout-api 5xx rate hit 18% at 07:41 "
            "(SEV-1).\n"
            "- **Fix:** Priya rolled back to v2.14.0 at 08:12, errors are under "
            "0.5%. Likely cause: a config typo cut the DB pool from 50 to 5.\n"
            "- **For you:** the status page summary before noon, and your "
            "timeline notes before Tomasz's postmortem on **{en:+2}, 15:00**."
        ),
        "sources": ["incident_alert", "incident_update", "incident_postmortem"],
    },
    {
        "question": "Any events this week?",
        "aliases": ["What's on my calendar this week?", "Events this week?"],
        "answer": (
            "Seven coming up:\n\n"
            "- **{wd:+1} 10:00**: sprint review, Ada room\n"
            "- **{wd:+2} 15:00**: INC-3107 postmortem\n"
            "- **{wd:+3} 14:30**: dentiste\n"
            "- **{wd:+4} 19:00**: Python Lyon meetup\n"
            "- **{wd:+5} 20:00**: dîner chez Marie (bring dessert)\n"
            "- **{wd:+6} 18:30**: AG des copropriétaires\n"
            "- **{en:+7}**: crèche fermée, childcare needed"
        ),
        "sources": [
            "sprint_review",
            "incident_postmortem",
            "dentist",
            "meetup",
            "dinner",
            "syndic_ag",
            "creche",
        ],
    },
]

# "summarize" button answers, keyed by the corpus key of the pinned email;
# written in the email's own language, like the real prompt asks for
_INCIDENT_SUMMARY = DEMO_CHAT[2]["answer"]
_AG_SUMMARY = (
    "- **Qui :** le Syndic Duval convoque l'AG des copropriétaires.\n"
    "- **Quand :** {frl:+6} à 18h30, salle polyvalente.\n"
    "- **Enjeu :** résolution n°7, ravalement à 186 000 € (≈ 4 100 € pour "
    "votre lot).\n"
    "- **Action :** si vous êtes absent, renvoyez votre pouvoir signé avant "
    "le {frl:+5}."
)
DEMO_SUMMARIES = {
    "incident_alert": _INCIDENT_SUMMARY,
    "incident_update": _INCIDENT_SUMMARY,
    "incident_postmortem": _INCIDENT_SUMMARY,
    "syndic_ag": _AG_SUMMARY,
    "syndic_neighbour": _AG_SUMMARY,
    "tax_notice": (
        "- **Qui :** Finances publiques, message automatique.\n"
        "- **Quoi :** taxe foncière de **1 284 €**.\n"
        "- **Action :** payer avant le **{frd:+4}**, sinon majoration de 10 %."
    ),
    "board_numbers": (
        "- **Who:** Sarah Whitfield, for tonight's board deck (slide 9).\n"
        "- **Needs:** {month:-1} infrastructure cost and quarterly uptime.\n"
        "- **Deadline:** **today, 16:00**. This morning's incident gets a "
        "footnote."
    ),
}

CONTEXT_OFF_ANSWER = (
    "Inbox context is off, so I can't see your emails. Turn on the "
    '"inbox context" toggle and ask again.'
)


def _normalize(text: str) -> str:
    """Fold case, accents and punctuation so near-identical questions match."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", folded.lower()).split())


def fallback_answer() -> str:
    """Answer for an unscripted question: list what the demo can answer."""
    questions = "\n".join(f"- {entry['question']}" for entry in DEMO_CHAT)
    return f"Demo mode answers a few scripted questions only. Try:\n\n{questions}"


def scripted_answer(question: str) -> str | None:
    """Return the raw (unrendered) answer for a scripted question, or None."""
    wanted = _normalize(question)
    for entry in DEMO_CHAT:
        if wanted in {_normalize(q) for q in [entry["question"], *entry["aliases"]]}:
            return entry["answer"]
    return None


def _email_key(email_id: int) -> str | None:
    """Corpus key of a seeded email (its .eml file name), or None."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT maildir_file FROM emails WHERE id = ?", (email_id,)
        ).fetchone()
    return Path(row["maildir_file"]).stem if row else None


def pick_answer(history: list[dict], use_context: bool, email_id: int | None) -> str:
    """Choose the rendered answer for the last user message.

    A scripted question wins even with an email pinned: the UI keeps the
    summarized email pinned for follow-up questions.
    """
    raw = scripted_answer(history[-1]["content"]) if use_context else None
    if raw is None and email_id is not None:
        key = _email_key(email_id) or ""
        raw = DEMO_SUMMARIES.get(
            key, "Demo mode has no scripted summary for this email."
        )
    if raw is None:
        raw = fallback_answer() if use_context else CONTEXT_OFF_ANSWER
    return render(raw, date.today())


def _chunks(text: str, words_per_chunk: int = 2) -> list[str]:
    """Split text into small chunks (a couple of words, whitespace kept)."""
    tokens = re.findall(r"\S+\s*|\s+", text)
    return [
        "".join(tokens[i : i + words_per_chunk])
        for i in range(0, len(tokens), words_per_chunk)
    ]


async def fake_stream_answer(
    history: list[dict],
    use_context: bool,
    email_id: int | None = None,
    provider: str = "ollama",
) -> AsyncIterator[str]:
    """Drop-in for app.chat.stream_answer that streams a scripted answer."""
    for chunk in _chunks(pick_answer(history, use_context, email_id)):
        yield chunk
        await asyncio.sleep(CHUNK_DELAY_S)
