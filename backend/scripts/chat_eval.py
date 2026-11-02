"""Chat evaluation set over the synthetic demo mailbox, and its scoring.

Used by scripts/benchmark_chat.py to compare chat models. The questions are
about scripts/demo_corpus.py (invented content, half French, half English),
so the set can live in the public repo and the expected facts are known.

Each question checks two things automatically:
- facts: every group in `expect` must have at least one alternative present
  in the answer (case- and accent-insensitive). `@date:+N` stands for the
  date N days after the seeding day, in any common EN/FR spelling, and
  `@wd:+N` its weekday name (EN or FR).
- language: the answer must be in `answer_lang` (default: the question's
  language; "any" skips the check). English questions about French mail
  are the drift test.

Scores are a screen, not a verdict: the benchmark also writes every answer
to a report for a human read.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

from app.lang import detect_language
from scripts.demo_corpus import _EN_MONTHS, _EN_WEEKDAYS, _FR_MONTHS, _FR_WEEKDAYS

# answers that admit the mailbox does not hold the information
_NOT_FOUND = [
    "not find", "couldn't find", "could not find", "can't find", "cannot find",
    "no email", "no mention", "not mention", "don't see", "do not see",
    "doesn't contain", "does not contain", "no information", "nothing about",
    "not in the", "don't have any", "do not have any", "pas trouve",
    "pas de trace", "n'ai pas", "je ne trouve", "aucun", "ne vois pas", "ne contient pas",
    "pas d'information", "pas de mention", "rien",
]  # fmt: skip

QUESTIONS: list[dict] = [
    # --- English questions, French mail: the language-drift test
    {"id": "tax", "lang": "en", "q": "When is the property tax due, and how much is it?",
     "expect": [["1 284", "1,284", "1284", "1.284"], ["@date:+4"]]},
    {"id": "ag", "lang": "en", "q": "When is the co-owners' general meeting and what is the big vote about?",
     "expect": [["@date:+6"], ["18:30", "18h30", "6:30", "6.30"], ["facade", "façade", "ravalement"]]},
    {"id": "creche", "lang": "en", "q": "When is the nursery closed?",
     "expect": [["@date:+7"]]},
    {"id": "dentist", "lang": "en", "q": "When is my dentist appointment?",
     "expect": [["@date:+3"], ["14:30", "14h30", "2:30", "2.30"]]},
    {"id": "dinner", "lang": "en", "q": "What should I bring to Marie's dinner, and what is Julien bringing?",
     "expect": [["dessert"], ["wine", "vin"]]},
    {"id": "helene", "lang": "en", "q": "What did Hélène ask me?",
     "expect": [["proxy", "pouvoir", "power of attorney"], ["second quote", "second estimate", "another quote", "second devis", "other quote", "new quote"]]},
    {"id": "parcel", "lang": "en", "q": "Was my parcel delivered?",
     "expect": [["yes", "delivered"], ["letterbox", "letter box", "mailbox", "boite aux lettres", "boîte aux lettres"]]},
    # --- English questions, English mail
    {"id": "today", "lang": "en", "q": "What do I need to do today?",
     "expect": [["16:00", "4 pm", "4pm", "board"], ["sign", "msa"], ["status page", "customer-facing", "summary"]]},
    {"id": "root_cause", "lang": "en", "q": "What caused the checkout-api incident?",
     "expect": [["connection pool", "pool"], ["50"], ["5"]]},
    {"id": "board", "lang": "en", "q": "Which figures does Sarah need for the board deck, and by when?",
     "expect": [["infrastructure cost", "infra cost", "infrastructure"], ["uptime"], ["16:00", "4 pm", "4pm", "4:00"]]},
    {"id": "token", "lang": "en", "q": "Which secret leaked, and what should I do about it?",
     "expect": [["payment"], ["revoke", "rotate"]]},
    {"id": "invoice", "lang": "en", "q": "How much is the Cloudnest invoice?",
     "expect": [["23.90", "23,90"]]},
    {"id": "missing_en", "lang": "en", "q": "What did my landlord say about the rent increase?",
     "expect": [_NOT_FOUND]},
    # --- French questions, English mail: the drift test the other way
    {"id": "postmortem", "lang": "fr", "q": "Quand a lieu le postmortem de l'incident ?",
     "expect": [["@date:+2"], ["15:00", "15h", "15 h"]]},
    {"id": "priya", "lang": "fr", "q": "Qu'est-ce que Priya m'a demandé de faire ?",
     "expect": [["page de statut", "page d'etat", "status page", "statut", "clients", "client"], ["midi", "12h", "12:00", "noon"]]},
    {"id": "tunewave", "lang": "fr", "q": "Combien coûte mon abonnement Tunewave et quand est-il renouvelé ?",
     "expect": [["14,99", "14.99"], ["@date:+9"]]},
    {"id": "offsite", "lang": "fr", "q": "Que faut-il envoyer à Nadia pour le séminaire, et avant quand ?",
     "expect": [["alimentaire", "régime", "regime", "dietary", "allergie"], ["arrivée", "arrivee", "heure", "arrival"], ["@date:+3", "@wd:+3"]]},
    {"id": "meetup", "lang": "fr", "q": "C'est quand le meetup Python et de quoi parlent les talks ?",
     "expect": [["@date:+4"], ["19:00", "19h", "19 h"], ["rag", "gpu", "laptop", "portable"]]},
    {"id": "missing_fr", "lang": "fr", "q": "Est-ce que j'ai reçu ma nouvelle carte Vitale ?",
     "expect": [_NOT_FOUND]},
    # --- "summarize this email": answer in the email's language, by design
    # the dashboard button always asks in English (src/App.jsx summarizeEmail)
    {"id": "sum_fr", "lang": "en", "answer_lang": "fr", "focus": "syndic_ag",
     "q": 'Summarize this email from Syndic Duval: "Convocation à l\'assemblée générale"',
     "expect": [["@date:+6"], ["ravalement", "façade", "facade"]]},
    # typed by the user in French: either language is a fair answer
    {"id": "sum_en", "lang": "fr", "answer_lang": "any", "focus": "board_numbers", "q": "Résume cet email.",
     "expect": [["uptime"], ["16:00", "4 pm", "4pm"]]},
]  # fmt: skip


def fold(text: str) -> str:
    """Lower-case and strip accents, so 'Façade' matches 'facade'."""
    norm = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in norm if not unicodedata.combining(c))


def _ordinal(day: int) -> str:
    """English ordinal suffix for a day of the month: 1st, 2nd, 3rd, 4th."""
    if 11 <= day % 100 <= 13:
        return f"{day}th"
    return f"{day}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th') }"


def date_variants(seed_day: date, offset: int) -> list[str]:
    """Common EN/FR spellings of the date `offset` days after seed_day."""
    d = seed_day + timedelta(days=offset)
    en, fr = _EN_MONTHS[d.month - 1], _FR_MONTHS[d.month - 1]
    fr_day = "1er" if d.day == 1 else str(d.day)
    return [
        f"{d.day} {en}",
        f"{en} {d.day}",
        f"{_ordinal(d.day)} {en}",
        f"{_ordinal(d.day)} of {en}",
        f"{fr_day} {fr}",
        f"{d:%d} {en}",
        f"{d:%d} {fr}",
        f"{d:%d/%m}",
        f"{d.day}/{d.month}",
        f"{d:%Y-%m-%d}",
    ]


def expand(alternatives: list[str], seed_day: date) -> list[str]:
    """Replace each `@date:+N` alternative by its date spellings."""
    out: list[str] = []
    for alt in alternatives:
        if m := re.fullmatch(r"@date:([+-]\d+)", alt):
            out += date_variants(seed_day, int(m.group(1)))
        elif m := re.fullmatch(r"@wd:([+-]\d+)", alt):
            d = seed_day + timedelta(days=int(m.group(1)))
            out += [_EN_WEEKDAYS[d.weekday()], _FR_WEEKDAYS[d.weekday()]]
        else:
            out.append(alt)
    return out


def _contains(answer: str, alt: str) -> bool:
    """Whether `alt` occurs in the folded answer; short numbers need word edges."""
    a, needle = fold(answer), fold(alt)
    if needle.isdigit() and len(needle) <= 2:
        return re.search(rf"(?<![\w.,]){needle}(?!\w|[.,]\d)", a) is not None
    return needle in a


def facts_found(answer: str, expect: list[list[str]], seed_day: date) -> list[bool]:
    """For each expected fact group, whether any alternative is in the answer."""
    return [
        any(_contains(answer, alt) for alt in expand(group, seed_day))
        for group in expect
    ]


def score_answer(question: dict, answer: str, seed_day: date) -> dict:
    """Facts found, language and overall pass for one answer."""
    found = facts_found(answer, question["expect"], seed_day)
    want = question.get("answer_lang", question["lang"])
    got = detect_language(answer)
    return {
        "facts": sum(found),
        "facts_total": len(found),
        "missing": [g[0] for g, ok in zip(question["expect"], found) if not ok],
        "lang": got,
        "lang_ok": want == "any" or got == want,
        "pass": all(found) and (want == "any" or got == want),
    }
