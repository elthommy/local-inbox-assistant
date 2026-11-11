"""Pre-filter for the "My priorities" rules: keep the ones naming the sender.

Appending every rule to every extraction prompt shifted the priority of ~1% of
unrelated emails. A rule (one per line) is now added to an email's prompt only
when it names the sender — a word of the sender's display name, address or
organisation domain appears in it — so an email no rule names gets exactly
the default prompt."""

from __future__ import annotations

import re
import unicodedata

MIN_WORD = 4  # shorter sender words ("e", "sa", "fr") never select a rule
MIN_SUBSTRING = 8  # sender words this long also match a rule's run-together words

# Words common in senders' names and addresses ("Foo Notifications
# <noreply@mail.foo.com>", "Votre conseiller") that do not identify anyone.
STOPWORDS = frozenset(
    """
    mail mails email emails courriel message messages info infos contact
    noreply donotreply reply repondre news newsletter newsletters
    notification notifications notify alert alerts alerte alertes team equipe
    support service services account accounts compte client clients
    votre notre your from club espace space group groupe store shop boutique
    billing invoice invoices statements receipts factures facture
    """.split()
)
# Personal mailbox providers: there the address local part names a person
# ("jane.doe@gmail.com"); elsewhere it is a role ("statements@", "billing@").
PERSONAL_DOMAINS = frozenset(
    """
    gmail googlemail hotmail outlook live yahoo icloud proton protonmail gmx
    laposte free orange wanadoo sfr
    """.split()
)


def _fold(text: str) -> str:
    """Lower-case and strip accents, so "Équipe" and "equipe" compare equal."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _words(text: str) -> list[str]:
    """Alphanumeric words of the folded text."""
    return re.findall(r"[a-z0-9]+", _fold(text))


def _org_label(domain: str) -> str:
    """The organisation part of a mail domain: "caz.caisse-epargne.fr" →
    "caisse-epargne", "mail.anthropic.com" → "anthropic"."""
    labels = [p for p in _fold(domain).split(".") if p]
    return labels[-2] if len(labels) >= 2 else ""


def sender_names(sender: str | None, sender_email: str | None) -> set[str]:
    """Words that identify a sender: display name, plus the organisation domain
    (also run together: "clubfunding-group" → "clubfundinggroup"), or the
    address local part at a personal mailbox provider."""
    local, _, domain = (sender_email or "").rpartition("@")
    org = _org_label(domain)
    if org in PERSONAL_DOMAINS:
        org = ""
    else:
        local = ""
    words = _words(f"{sender or ''} {local} {org}") + ["".join(_words(org))]
    return {w for w in words if len(w) >= MIN_WORD and w not in STOPWORDS}


def rule_names_sender(rule: str, sender: str | None, sender_email: str | None) -> bool:
    """Whether a word identifying the sender is a whole word of the rule, or,
    when long, part of the rule's run-together words ("Club Funding")."""
    words = _words(rule)
    rule_words, joined = set(words), "".join(words)
    return any(
        name in rule_words or (len(name) >= MIN_SUBSTRING and name in joined)
        for name in sender_names(sender, sender_email)
    )


def rules_for_sender(rules: str, sender: str | None, sender_email: str | None) -> str:
    """The lines of `rules` that name this sender, joined; "" when none does."""
    return "\n".join(
        line.strip()
        for line in rules.splitlines()
        if line.strip() and rule_names_sender(line, sender, sender_email)
    )
