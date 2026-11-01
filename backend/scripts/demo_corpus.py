"""Synthetic mailbox used by scripts/seed_demo.py and scripts/demo_server.py.

Entirely invented content: every person, company and domain is made up
(`.example` domains), nothing comes from a real mailbox.

Story: back from a week off, the inbox is full. A handful of emails really
matter today (an incident, a manager ask, a leaked token, a signature, two
French admin deadlines); the rest is newsletters, receipts and notifications
that triage should leave out of the priority view.

Each entry carries the canned `extraction` that the LLM pass would normally
produce, so seeding needs no model and stays deterministic.

Dates never go stale: `hours_ago` is resolved against today 08:45 (seed_demo
`--clock`), and dates inside subjects, bodies and extractions are written as
`{token:offset}` placeholders that `render()` fills in at seed time, `offset`
being days from today (months for `month`). Tokens:

    fr    05/11              frd   05/11/2026        frl  jeudi 5 novembre
    frwd  jeudi              en    Thursday 5 November
    ens   5 November         wd    Thursday          month  October

`reply_to` names the key of the email being answered; the seeder sets
In-Reply-To/References so the messages form a thread.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

_EN_MONTHS = [
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
]  # fmt: skip
_FR_MONTHS = [
    "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
    "août", "septembre", "octobre", "novembre", "décembre",
]  # fmt: skip
_EN_WEEKDAYS = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
]  # fmt: skip
_FR_WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

_TOKEN_RE = re.compile(r"\{(frd|frl|frwd|fr|ens|en|wd|month):([+-]?\d+)\}")


def _shift_month(today: date, months: int) -> int:
    """Return the month number (1-12) `months` away from today's month."""
    return (today.month - 1 + months) % 12 + 1


def _format_token(kind: str, offset: int, today: date) -> str:
    """Render one placeholder: `offset` days (or months) from `today`."""
    if kind == "month":
        return _EN_MONTHS[_shift_month(today, offset) - 1]
    d = today + timedelta(days=offset)
    fr_day = "1er" if d.day == 1 else str(d.day)
    return {
        "fr": f"{d:%d/%m}",
        "frd": f"{d:%d/%m/%Y}",
        "frl": f"{_FR_WEEKDAYS[d.weekday()]} {fr_day} {_FR_MONTHS[d.month - 1]}",
        "frwd": _FR_WEEKDAYS[d.weekday()],
        "en": f"{_EN_WEEKDAYS[d.weekday()]} {d.day} {_EN_MONTHS[d.month - 1]}",
        "ens": f"{d.day} {_EN_MONTHS[d.month - 1]}",
        "wd": _EN_WEEKDAYS[d.weekday()],
    }[kind]


def render(text: str, today: date) -> str:
    """Fill every `{token:offset}` date placeholder in text, relative to today."""
    return _TOKEN_RE.sub(
        lambda m: _format_token(m.group(1), int(m.group(2)), today), text
    )


def render_value(value: Any, today: date) -> Any:
    """Recursively render placeholders in strings inside dicts and lists."""
    if isinstance(value, str):
        return render(value, today)
    if isinstance(value, list):
        return [render_value(v, today) for v in value]
    if isinstance(value, dict):
        return {k: render_value(v, today) for k, v in value.items()}
    return value


def rendered_corpus(today: date) -> list[dict]:
    """Return DEMO_EMAILS with every date placeholder filled in for today."""
    return [render_value(spec, today) for spec in DEMO_EMAILS]


def _none() -> dict:
    """Canned extraction of an email that needs nothing from the user."""
    return {"priority": "low", "tasks": [], "events": []}


NORTHWIND = "northwind-labs.example"

# folder: mailbox folder under the maildir root; unread: X-Mozilla-Status bit.
DEMO_EMAILS = [
    # --- thread 1: production incident (alert + two replies) ---------------
    {
        "key": "incident_alert",
        "folder": "INBOX",
        "sender": "Opsbell",
        "sender_email": "alerts@opsbell.example",
        "subject": "[SEV-1] checkout-api: 5xx rate at 18%",
        "hours_ago": 0.97,
        "unread": True,
        "body": (
            "INC-3107 triggered — SEV-1\n\n"
            "Service: checkout-api (production, eu-west)\n"
            "Signal: HTTP 5xx rate 18.2% (threshold 2%) for 6 minutes\n"
            "Started: 07:41 CET\n"
            "On call: you (secondary), Priya Raman (primary)\n\n"
            "Incident bridge: https://meet.northwind-labs.example/inc-3107\n"
            "Runbook: https://wiki.northwind-labs.example/runbooks/checkout"
        ),
        "extraction": {
            "priority": "high",
            "tasks": [{"text": "Join the INC-3107 incident bridge", "due": "today"}],
            "events": [],
        },
    },
    {
        "key": "incident_update",
        "folder": "INBOX",
        "sender": "Priya Raman",
        "sender_email": f"priya.raman@{NORTHWIND}",
        "subject": "Re: [SEV-1] checkout-api: 5xx rate at 18%",
        "reply_to": "incident_alert",
        "hours_ago": 0.42,
        "unread": True,
        "body": (
            "Update: rolled back to v2.14.0 at 08:12, 5xx rate is back under "
            "0.5%.\n\n"
            "Root cause looks like DB connection pool exhaustion after Friday's "
            "config change (pool size 50 -> 5, typo).\n\n"
            "Can you write the customer-facing summary for the status page "
            "before noon? I'll keep watching the dashboards.\n\n"
            "Priya"
        ),
        "extraction": {
            "priority": "high",
            "tasks": [
                {"text": "Write the INC-3107 status page summary", "due": "noon"}
            ],
            "events": [],
        },
    },
    {
        "key": "incident_postmortem",
        "folder": "INBOX",
        "sender": "Tomasz Nowak",
        "sender_email": f"tomasz.nowak@{NORTHWIND}",
        "subject": "Re: [SEV-1] checkout-api: 5xx rate at 18%",
        "reply_to": "incident_update",
        "hours_ago": 0.2,
        "unread": True,
        "body": (
            "Thanks both. Postmortem on {en:+2} at 15:00, blameless as usual.\n\n"
            "Please add your view of the 31 minutes between the first alert "
            "and the rollback to the timeline draft beforehand.\n\n"
            "Tomasz"
        ),
        "extraction": {
            "priority": "medium",
            "tasks": [
                {"text": "Add your notes to the INC-3107 timeline", "due": "{ens:+2}"}
            ],
            "events": [
                {"title": "INC-3107 postmortem", "date": "{en:+2}", "time": "15:00"}
            ],
        },
    },
    # --- the other things that matter today --------------------------------
    {
        "key": "board_numbers",
        "folder": "INBOX",
        "sender": "Sarah Whitfield",
        "sender_email": f"sarah.whitfield@{NORTHWIND}",
        "subject": "Board deck: your numbers by 16:00",
        "hours_ago": 0.3,
        "unread": True,
        "body": (
            "Welcome back! Sorry to start your week like this.\n\n"
            "The board deck goes out tonight and slide 9 is still empty. I "
            "need two figures from you by 16:00 today:\n"
            "- infrastructure cost for {month:-1}\n"
            "- uptime for the quarter (excluding this morning, we'll footnote "
            "it)\n\n"
            "Sarah"
        ),
        "extraction": {
            "priority": "high",
            "tasks": [
                {
                    "text": "Send infra cost and quarterly uptime to Sarah",
                    "due": "today 16:00",
                }
            ],
            "events": [],
        },
    },
    {
        "key": "token_leak",
        "folder": "INBOX",
        "sender": "Gitforge Security",
        "sender_email": "security@gitforge.example",
        "subject": "[northwind/api] Exposed API token detected",
        "hours_ago": 9,
        "unread": True,
        "body": (
            "Secret scanning found a credential in a public commit.\n\n"
            "Repository: northwind/api\n"
            "Commit: 4f1c8ad (branch: hotfix/pool-size)\n"
            "Secret type: payments provider API key\n\n"
            "Revoke this credential now: removing the commit does not revoke "
            "the secret.\n\n"
            "View the alert: https://gitforge.example/northwind/api/security"
        ),
        "extraction": {
            "priority": "high",
            "tasks": [{"text": "Revoke and rotate the leaked API key", "due": "today"}],
            "events": [],
        },
    },
    {
        "key": "msa_signature",
        "folder": "INBOX",
        "sender": "Signly",
        "sender_email": "no-reply@signly.example",
        "subject": "Signature needed today: Acme MSA renewal",
        "hours_ago": 3,
        "unread": True,
        "body": (
            "Léa Martin (Acme Retail) sent you a document to sign.\n\n"
            "Document: Master Services Agreement (renewal)\n"
            "Expires: today at 23:59\n\n"
            "If it expires, the renewal goes back to procurement and the "
            "current contract lapses at the end of the month.\n\n"
            "Review and sign: https://signly.example/s/7Q2K"
        ),
        "extraction": {
            "priority": "high",
            "tasks": [{"text": "Sign the Acme MSA renewal", "due": "today 23:59"}],
            "events": [],
        },
    },
    {
        "key": "tax_notice",
        "folder": "INBOX",
        "sender": "Finances publiques",
        "sender_email": "ne-pas-repondre@finances-publiques.example",
        "subject": "Taxe foncière : à payer avant le {frl:+4}",
        "hours_ago": 50,
        "unread": True,
        "body": (
            "Bonjour,\n\n"
            "Votre avis de taxe foncière est disponible dans votre espace "
            "particulier.\n\n"
            "Montant : 1 284 €\n"
            "Date limite de paiement : {frd:+4}\n\n"
            "Passé ce délai, une majoration de 10 % sera appliquée. Le "
            "paiement en ligne est possible jusqu'au {frl:+9}.\n\n"
            "Ce message est envoyé automatiquement, merci de ne pas y répondre."
        ),
        "extraction": {
            "priority": "high",
            "tasks": [{"text": "Payer la taxe foncière (1 284 €)", "due": "{fr:+4}"}],
            "events": [],
        },
    },
    # --- thread 2: co-ownership general assembly (French) -------------------
    {
        "key": "syndic_ag",
        "folder": "INBOX",
        "sender": "Syndic Duval",
        "sender_email": "gestion@syndic-duval.example",
        "subject": "Convocation à l'assemblée générale du {fr:+6}",
        "hours_ago": 140,
        "unread": False,
        "body": (
            "Madame, Monsieur,\n\n"
            "Vous êtes convoqué(e) à l'assemblée générale ordinaire des "
            "copropriétaires le {frl:+6} à 18h30, salle polyvalente.\n\n"
            "À l'ordre du jour : approbation des comptes, et résolution n°7 "
            "sur le ravalement de façade (devis de 186 000 €, soit environ "
            "4 100 € pour votre lot).\n\n"
            "En cas d'absence, merci de retourner votre pouvoir signé avant "
            "le {frl:+5}.\n\n"
            "Cordialement,\nCabinet Duval"
        ),
        "extraction": {
            "priority": "high",
            "tasks": [
                {"text": "Retourner le pouvoir signé au syndic", "due": "{fr:+5}"}
            ],
            "events": [
                {
                    "title": "AG des copropriétaires",
                    "date": "{frd:+6}",
                    "time": "18:30",
                }
            ],
        },
    },
    {
        "key": "syndic_neighbour",
        "folder": "INBOX",
        "sender": "Hélène Garnier",
        "sender_email": "helene.garnier@mailbox.example",
        "subject": "Re: Convocation à l'assemblée générale du {fr:+6}",
        "reply_to": "syndic_ag",
        "hours_ago": 30,
        "unread": True,
        "body": (
            "Bonjour,\n\n"
            "Je ne pourrai pas être là le {frwd:+6}. Est-ce que je peux te "
            "donner mon pouvoir ?\n\n"
            "Et 186 000 € pour le ravalement, ça me paraît énorme : on demande "
            "un second devis avant de voter ?\n\n"
            "Hélène (lot 12)"
        ),
        "extraction": {
            "priority": "medium",
            "tasks": [
                {"text": "Répondre à Hélène (pouvoir + second devis)", "due": ""}
            ],
            "events": [],
        },
    },
    # --- thread 3: family dinner ---------------------------------------------
    {
        "key": "dinner",
        "folder": "INBOX",
        "sender": "Marie Fontaine",
        "sender_email": "marie.fontaine@mailbox.example",
        "subject": "Dîner {frwd:+5} soir ?",
        "hours_ago": 46,
        "unread": False,
        "body": (
            "Coucou,\n\n"
            "On fait un dîner à la maison le {frl:+5} vers 20h, tout le monde "
            "est dispo. Tu viens ?\n\n"
            "Ramène juste le dessert si tu passes devant la boulangerie.\n\n"
            "Bises,\nMarie"
        ),
        "extraction": {
            "priority": "medium",
            "tasks": [{"text": "Apporter le dessert chez Marie", "due": "{fr:+5}"}],
            "events": [
                {"title": "Dîner chez Marie", "date": "{frd:+5}", "time": "20:00"}
            ],
        },
    },
    {
        "key": "dinner_reply",
        "folder": "INBOX",
        "sender": "Julien Fontaine",
        "sender_email": "julien.fontaine@mailbox.example",
        "subject": "Re: Dîner {frwd:+5} soir ?",
        "reply_to": "dinner",
        "hours_ago": 40,
        "unread": False,
        "body": "Super, j'apporte le vin. On arrive vers 20h15.\n\nJulien",
        "extraction": _none(),
    },
    # --- work, medium -----------------------------------------------------
    {
        "key": "sprint_review",
        "folder": "INBOX",
        "sender": "Camille Lefèvre",
        "sender_email": f"camille.lefevre@{NORTHWIND}",
        "subject": "Sprint review moved to {wd:+1} 10:00",
        "hours_ago": 20,
        "unread": True,
        "body": (
            "Hi,\n\n"
            "The sprint review moves to {en:+1} at 10:00 in the Ada room.\n\n"
            "Could you show the new search indexing? Five minutes is plenty.\n\n"
            "Thanks,\nCamille"
        ),
        "extraction": {
            "priority": "medium",
            "tasks": [
                {"text": "Prepare a 5-minute search indexing demo", "due": "{wd:+1}"}
            ],
            "events": [
                {
                    "title": "Sprint review (Ada room)",
                    "date": "{en:+1}",
                    "time": "10:00",
                }
            ],
        },
    },
    {
        "key": "code_review",
        "folder": "INBOX",
        "sender": "Gitforge",
        "sender_email": "notifications@gitforge.example",
        "subject": "[northwind/api] Review requested on #512",
        "hours_ago": 26,
        "unread": True,
        "body": (
            "Priya Raman requested your review on pull request #512.\n\n"
            "Retry payment webhooks with backoff\n"
            "  +188 -41 across 7 files\n\n"
            "https://gitforge.example/northwind/api/pull/512"
        ),
        "extraction": {
            "priority": "medium",
            "tasks": [{"text": "Review PR #512 (webhook retries)", "due": ""}],
            "events": [],
        },
    },
    {
        "key": "offsite",
        "folder": "INBOX",
        "sender": "Nadia Belkacem",
        "sender_email": f"nadia.belkacem@{NORTHWIND}",
        "subject": "Team offsite: dietary needs by {wd:+3}",
        "hours_ago": 75,
        "unread": False,
        "body": (
            "Hi everyone,\n\n"
            "The offsite in Annecy is confirmed. I need dietary requirements "
            "and arrival times from everyone by {en:+3} to book the "
            "restaurant.\n\n"
            "Nadia"
        ),
        "extraction": {
            "priority": "medium",
            "tasks": [
                {"text": "Send Nadia dietary needs and arrival time", "due": "{wd:+3}"}
            ],
            "events": [],
        },
    },
    {
        "key": "meetup",
        "folder": "INBOX",
        "sender": "Python Lyon",
        "sender_email": "hello@pylyon.example",
        "subject": "Meetup {wd:+4}: local LLMs in practice",
        "hours_ago": 100,
        "unread": False,
        "body": (
            "Hello Pythonistas,\n\n"
            "Next meetup: {en:+4}, 19:00, at La Cordée. Two talks: running "
            "models on a laptop GPU, and RAG without a cloud.\n\n"
            "You RSVP'd yes. See you there!"
        ),
        "extraction": {
            "priority": "medium",
            "tasks": [],
            "events": [
                {"title": "Python Lyon meetup", "date": "{en:+4}", "time": "19:00"}
            ],
        },
    },
    {
        "key": "dentist",
        "folder": "INBOX",
        "sender": "Cabinet dentaire Villeneuve",
        "sender_email": "rdv@cabinet-villeneuve.example",
        "subject": "Rappel : rendez-vous le {fr:+3} à 14h30",
        "hours_ago": 28,
        "unread": False,
        "body": (
            "Bonjour,\n\n"
            "Nous vous rappelons votre rendez-vous de contrôle le {frl:+3} à "
            "14h30.\n\n"
            "Merci de nous prévenir 48 heures à l'avance en cas d'empêchement."
        ),
        "extraction": {
            "priority": "medium",
            "tasks": [],
            "events": [
                {"title": "Dentiste (contrôle)", "date": "{frd:+3}", "time": "14:30"}
            ],
        },
    },
    {
        "key": "creche",
        "folder": "INBOX",
        "sender": "Crèche Les Petits Pas",
        "sender_email": "direction@petits-pas.example",
        "subject": "Fermeture exceptionnelle le {frl:+7}",
        "hours_ago": 60,
        "unread": True,
        "body": (
            "Chers parents,\n\n"
            "La crèche sera exceptionnellement fermée le {frl:+7} (journée de "
            "formation de l'équipe).\n\n"
            "Merci de prévoir une solution de garde ce jour-là.\n\n"
            "L'équipe des Petits Pas"
        ),
        "extraction": {
            "priority": "medium",
            "tasks": [
                {
                    "text": "Organiser la garde du {frwd:+7} (crèche fermée)",
                    "due": "{fr:+7}",
                }
            ],
            "events": [{"title": "Crèche fermée", "date": "{frd:+7}", "time": ""}],
        },
    },
    # --- noise: newsletters, receipts, notifications ------------------------
    {
        "key": "pydigest",
        "folder": "Newsletters",
        "sender": "PyDigest",
        "sender_email": "digest@pydigest.example",
        "subject": "PyDigest #318: task groups, WAL, uv tips",
        "hours_ago": 30,
        "unread": True,
        "body": (
            "This week: asyncio task groups in anger, why WAL mode is not a "
            "magic bullet, and ten uv tips.\n\n"
            "Unsubscribe: https://pydigest.example/unsubscribe"
        ),
        "extraction": _none(),
    },
    {
        "key": "invoice",
        "folder": "INBOX",
        "sender": "Cloudnest",
        "sender_email": "billing@cloudnest.example",
        "subject": "Your {month:-1} invoice is ready",
        "hours_ago": 22,
        "unread": False,
        "body": (
            "Your invoice for {month:-1} is available.\n\n"
            "Invoice: CN-11187\nAmount: EUR 23.90\n\n"
            "Payment is collected automatically. No action is required."
        ),
        "extraction": _none(),
    },
    {
        "key": "parcel",
        "folder": "INBOX",
        "sender": "ColisExpress",
        "sender_email": "suivi@colisexpress.example",
        "subject": "Votre colis a été livré",
        "hours_ago": 54,
        "unread": False,
        "body": (
            "Votre colis 6A18829937461 a été déposé dans votre boîte aux "
            "lettres.\n\nSuivi : https://colisexpress.example/6A18829937461"
        ),
        "extraction": _none(),
    },
    {
        "key": "tunewave",
        "folder": "Newsletters",
        "sender": "Tunewave",
        "sender_email": "no-reply@tunewave.example",
        "subject": "Your Duo plan renews on {ens:+9}",
        "hours_ago": 80,
        "unread": False,
        "body": (
            "Your Duo plan renews on {ens:+9} for EUR 14.99.\n\n"
            "No action is needed to keep listening."
        ),
        "extraction": _none(),
    },
    {
        "key": "pixelvault",
        "folder": "Newsletters",
        "sender": "Pixelvault",
        "sender_email": "deals@pixelvault.example",
        "subject": "Autumn sale: up to 80% off",
        "hours_ago": 36,
        "unread": True,
        "html": (
            "<html><body>"
            "<h2>Autumn sale is live</h2>"
            "<p>Up to <b>80% off</b> on 2,000 games. Three items on your "
            "wishlist are discounted.</p>"
            "<p><a href='https://pixelvault.example/sale'>Browse the sale</a></p>"
            "</body></html>"
        ),
        "extraction": _none(),
    },
    {
        "key": "maison_lune",
        "folder": "Newsletters",
        "sender": "Maison Lune",
        "sender_email": "newsletter@maison-lune.example",
        "subject": "-30 % sur la collection hiver",
        "hours_ago": 64,
        "unread": True,
        "html": (
            "<html><body>"
            "<h2>La collection hiver est arrivée</h2>"
            "<p><b>-30 %</b> sur les plaids, bougies et linge de lit, ce "
            "week-end seulement.</p>"
            "<p><a href='https://maison-lune.example/hiver'>Découvrir</a></p>"
            "</body></html>"
        ),
        "extraction": _none(),
    },
    {
        "key": "bank",
        "folder": "INBOX",
        "sender": "Banque Horizon",
        "sender_email": "info@banque-horizon.example",
        "subject": "Votre relevé de compte est disponible",
        "hours_ago": 90,
        "unread": False,
        "body": (
            "Bonjour,\n\nVotre relevé de compte mensuel est disponible dans "
            "votre espace client.\n\nBanque Horizon"
        ),
        "extraction": _none(),
    },
    {
        "key": "linkwise",
        "folder": "INBOX",
        "sender": "Linkwise",
        "sender_email": "notifications@linkwise.example",
        "subject": "You appeared in 14 searches this week",
        "hours_ago": 110,
        "unread": True,
        "body": "See who's looking at your profile: https://linkwise.example/me",
        "extraction": _none(),
    },
    {
        "key": "teamtalk",
        "folder": "INBOX",
        "sender": "Teamtalk",
        "sender_email": "digest@teamtalk.example",
        "subject": "37 unread messages in #platform",
        "hours_ago": 13,
        "unread": True,
        "body": (
            "You have 37 unread messages in #platform and 5 in #random.\n\n"
            "Open Teamtalk: https://teamtalk.example/northwind"
        ),
        "extraction": _none(),
    },
    {
        "key": "recruiter",
        "folder": "INBOX",
        "sender": "Jonas Ekström",
        "sender_email": "jonas@talentbridge.example",
        "subject": "Backend role, worth a quick chat?",
        "hours_ago": 150,
        "unread": False,
        "body": (
            "Hi,\n\nA Series B company building developer tooling in Python is "
            "hiring a senior backend engineer, remote within Europe. Open to a "
            "chat? If the timing is wrong, I will not chase.\n\nJonas"
        ),
        "extraction": _none(),
    },
]
