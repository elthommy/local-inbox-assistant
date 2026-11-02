"""Cheap English/French detection by stop-word counts (no model, no dependency).

The chat prompt names the user's language explicitly: some models (Gemma)
otherwise answer in the language of the retrieved excerpts. Anything not
clearly English or French returns "?" and the prompt keeps its generic rule.
"""

from __future__ import annotations

import re

LANGUAGE_NAMES = {"en": "English", "fr": "French"}

_EN_WORDS = set(
    "the is are and you your to of for with on at this that it be has have "
    "was will can need by from in an there no not what did do does when which "
    "who how my i".split()
)
_FR_WORDS = set(
    "le la les des est sont et vous votre vos pour avec sur une un du au aux "
    "ce cette il elle a pas ne qui que dans de en par quoi quand mon ma mes je "
    "cet".split()
)


def detect_language(text: str) -> str:
    """'en' or 'fr' by stop-word counts, ignoring quoted text; '?' if unclear.

    Quotes and inline code often carry subjects in the other language, so
    they are dropped before counting.
    """
    text = re.sub(r"`[^`]*`|\"[^\"]*\"|«[^»]*»|“[^”]*”", " ", text)
    words = re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", text.lower())
    words = [w.split("'")[-1] for w in words]
    en = sum(w in _EN_WORDS for w in words)
    fr = sum(w in _FR_WORDS for w in words)
    if en == fr:
        return "?"
    return "en" if en > fr else "fr"
