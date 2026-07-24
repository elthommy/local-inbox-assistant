"""Synthetic mailbox used by scripts/seed_demo.py.

Entirely invented content — no real mailbox is read and nothing here is
personal data. Two bodies (`orange_airbox`, `steam_wishlist`) are lightly
edited transactional mail kept because they show what real newsletter and
service mail looks like in the reading view.

Each entry carries the canned `extraction` that the LLM pass would normally
produce, so seeding needs no extraction model and stays deterministic.
`hours_ago` is resolved against the seeding time, keeping the corpus inside
the default 14-day extraction window however long the file sits in git.
"""

# folder: mailbox folder under the maildir root; unread: X-Mozilla-Status bit.
DEMO_EMAILS = [
    {
        "key": "sprint_review",
        "folder": "INBOX",
        "sender": "Camille Lefevre",
        "sender_email": "camille.lefevre@northwind-labs.example",
        "subject": "Sprint review moved to tomorrow 10:00",
        "hours_ago": 2,
        "unread": True,
        "body": (
            "Hi,\n\n"
            "We had to move the sprint review forward: it now starts tomorrow "
            "at 10:00 in the Ada room (video link in the invite).\n\n"
            "Could you have the indexing demo ready to show? Five minutes is "
            "plenty — mostly we want to see the incremental re-index working "
            "on a cold cache.\n\n"
            "Thanks,\nCamille"
        ),
        "extraction": {
            "priority": "high",
            "tasks": [
                {"text": "Prepare the 5-minute indexing demo", "due": "tomorrow"}
            ],
            "events": [
                {
                    "title": "Sprint review (Ada room)",
                    "date": "tomorrow",
                    "time": "10:00",
                }
            ],
        },
    },
    {
        "key": "security_alert",
        "folder": "INBOX",
        "sender": "GitHub",
        "sender_email": "noreply@github.example",
        "subject": "[northwind/api] Secret scanning found an exposed token",
        "hours_ago": 12,
        "unread": True,
        "body": (
            "Secret scanning found a credential in a public commit.\n\n"
            "Repository: northwind/api\n"
            "Commit: 4f1c8ad\n"
            "Secret type: generic API key\n\n"
            "Revoke this credential now — anyone who saw the commit can still "
            "use it. Removing the commit does not revoke the secret.\n\n"
            "View the alert: https://github.example/northwind/api/security"
        ),
        "extraction": {
            "priority": "high",
            "tasks": [
                {"text": "Revoke and rotate the exposed API key", "due": "today"},
                {"text": "Audit access logs for use of the leaked key", "due": ""},
            ],
            "events": [],
        },
    },
    {
        "key": "orange_airbox",
        "folder": "INBOX",
        "sender": "Orange",
        "sender_email": "service.client@orange.example",
        "subject": "Pret d'une Airbox : conditions de restitution",
        "hours_ago": 72,
        "unread": True,
        "body": (
            "Bonjour,\n\n"
            "Nous sommes heureux de vous preter une Airbox pour vous permettre "
            "de continuer a utiliser vos services Orange.\n\n"
            "Vous voudrez bien nous la restituer avant le 25/09/2026 :\n"
            "- prioritairement dans le point relais de votre choix en utilisant "
            "le bon de restitution qui sera joint au prochain e-mail (egalement "
            "disponible dans votre espace client) ;\n"
            "- a defaut dans une boutique Orange (liste des boutiques sur "
            "orange.fr > trouver une boutique).\n\n"
            "Attention, n'oubliez pas de nous la retourner avant la date limite, "
            "sans quoi une somme de 49 euros vous sera facturee pour retard de "
            "restitution. Avouez que ce serait dommage !\n\n"
            "Vous trouverez en piece jointe les conditions specifiques du pret "
            "d'Airbox."
        ),
        "extraction": {
            "priority": "high",
            "tasks": [
                {
                    "text": "Restituer l'Airbox Orange (49 EUR de penalite sinon)",
                    "due": "25/09/2026",
                }
            ],
            "events": [
                {
                    "title": "Date limite de restitution Airbox",
                    "date": "25/09/2026",
                    "time": "",
                }
            ],
        },
    },
    {
        "key": "code_review",
        "folder": "INBOX",
        "sender": "GitHub",
        "sender_email": "noreply@github.example",
        "subject": "[northwind/api] Review requested on #482: streaming chat endpoint",
        "hours_ago": 6,
        "unread": True,
        "body": (
            "Priya Raman requested your review on pull request #482.\n\n"
            "Streaming chat endpoint\n"
            "  +214 -37 across 9 files\n\n"
            "Replaces the buffered /chat response with server-sent events so "
            "the frontend can render tokens as they arrive. Adds a regression "
            "test for SSE frames split across network chunks.\n\n"
            "https://github.example/northwind/api/pull/482"
        ),
        "extraction": {
            "priority": "medium",
            "tasks": [{"text": "Review PR #482 (streaming chat endpoint)", "due": ""}],
            "events": [],
        },
    },
    {
        "key": "q3_report",
        "folder": "INBOX",
        "sender": "Sarah Whitfield",
        "sender_email": "sarah.whitfield@northwind-labs.example",
        "subject": "Q3 report — figures still missing from your section",
        "hours_ago": 26,
        "unread": False,
        "body": (
            "Hello,\n\n"
            "I am assembling the Q3 report and your section is the last one "
            "open. I need the infrastructure cost figures and the incident "
            "count for the quarter.\n\n"
            "Finance closes the consolidation on Friday, so anything after "
            "Thursday evening will not make it in.\n\n"
            "Best,\nSarah"
        ),
        "extraction": {
            "priority": "high",
            "tasks": [
                {"text": "Send Q3 infrastructure costs to Sarah", "due": "Thursday"},
                {"text": "Compile Q3 incident count", "due": "Thursday"},
            ],
            "events": [],
        },
    },
    {
        "key": "steam_wishlist",
        "folder": "Newsletters",
        "sender": "Steam",
        "sender_email": "noreply@steampowered.example",
        "subject": "An item on your Steam Wishlist has just released!",
        "hours_ago": 22,
        "unread": True,
        "html": (
            "<html><body>"
            "<h2>An item on your Steam Wishlist has just released!</h2>"
            "<h3>NTE: Neverness to Everness</h3>"
            "<p>NTE is a supernatural urban open-world RPG developed by Hotta "
            "Studio. Your story begins in Hethereau as an unlicensed anomaly "
            "hunter. Team up with a diverse cast of companions, each with "
            "unique abilities, to unravel the city's mysteries.</p>"
            "<p><a href='https://store.steampowered.example/app/000000'>"
            "View in store</a></p>"
            "</body></html>"
        ),
        "extraction": {"priority": "low", "tasks": [], "events": []},
    },
    {
        "key": "dentist",
        "folder": "INBOX",
        "sender": "Cabinet Dentaire Villeneuve",
        "sender_email": "rdv@cabinet-villeneuve.example",
        "subject": "Confirmation de votre rendez-vous",
        "hours_ago": 96,
        "unread": False,
        "body": (
            "Bonjour,\n\n"
            "Nous confirmons votre rendez-vous de controle annuel le "
            "12/08/2026 a 14h30 au cabinet.\n\n"
            "Merci de nous prevenir au moins 48 heures a l'avance en cas "
            "d'empechement.\n\n"
            "Cordialement,\nLe secretariat"
        ),
        "extraction": {
            "priority": "medium",
            "tasks": [],
            "events": [
                {
                    "title": "Rendez-vous dentiste (controle annuel)",
                    "date": "12/08/2026",
                    "time": "14:30",
                }
            ],
        },
    },
    {
        "key": "postmortem",
        "folder": "INBOX",
        "sender": "Tomasz Nowak",
        "sender_email": "tomasz.nowak@northwind-labs.example",
        "subject": "Postmortem: search latency incident (INC-2291)",
        "hours_ago": 120,
        "unread": False,
        "body": (
            "Team,\n\n"
            "The postmortem for INC-2291 is scheduled for Tuesday 28 July at "
            "15:00. Blameless as always.\n\n"
            "Please read the timeline draft beforehand and add anything you "
            "saw that is missing — particularly around the 40-minute gap "
            "between the first alert and the rollback.\n\n"
            "Tomasz"
        ),
        "extraction": {
            "priority": "high",
            "tasks": [
                {
                    "text": "Read and annotate the INC-2291 timeline draft",
                    "due": "28/07/2026",
                }
            ],
            "events": [
                {
                    "title": "Postmortem INC-2291",
                    "date": "28/07/2026",
                    "time": "15:00",
                }
            ],
        },
    },
    {
        "key": "offsite",
        "folder": "INBOX",
        "sender": "Nadia Belkacem",
        "sender_email": "nadia.belkacem@northwind-labs.example",
        "subject": "Team offsite — dietary requirements needed",
        "hours_ago": 90,
        "unread": True,
        "body": (
            "Hi everyone,\n\n"
            "The offsite is confirmed for 3-4 September in Annecy. I need "
            "dietary requirements and arrival times from everyone before I can "
            "book the restaurant.\n\n"
            "Reply to this thread rather than to me directly, it saves me "
            "collating twelve separate emails.\n\n"
            "Nadia"
        ),
        "extraction": {
            "priority": "medium",
            "tasks": [
                {"text": "Reply with dietary requirements and arrival time", "due": ""}
            ],
            "events": [
                {"title": "Team offsite in Annecy", "date": "2026-09-03", "time": ""}
            ],
        },
    },
    {
        "key": "syndic",
        "folder": "INBOX",
        "sender": "Syndic Duval",
        "sender_email": "gestion@syndic-duval.example",
        "subject": "Convocation a l'assemblee generale des coproprietaires",
        "hours_ago": 144,
        "unread": False,
        "body": (
            "Madame, Monsieur,\n\n"
            "Vous etes convoque a l'assemblee generale ordinaire des "
            "coproprietaires qui se tiendra le 30/07/2026 a 18h00, salle "
            "communale.\n\n"
            "L'ordre du jour et les pouvoirs sont joints. En cas "
            "d'indisponibilite, merci de retourner votre pouvoir signe avant "
            "la veille de l'assemblee.\n\n"
            "Cordialement"
        ),
        "extraction": {
            "priority": "medium",
            "tasks": [
                {"text": "Retourner le pouvoir signe si absent", "due": "29/07/2026"}
            ],
            "events": [
                {
                    "title": "Assemblee generale des coproprietaires",
                    "date": "30/07/2026",
                    "time": "18:00",
                }
            ],
        },
    },
    {
        "key": "cfp",
        "folder": "INBOX",
        "sender": "PyConFR",
        "sender_email": "cfp@pyconfr.example",
        "subject": "Call for proposals closes in one week",
        "hours_ago": 210,
        "unread": False,
        "body": (
            "The call for proposals closes on 15 August at 23:59 CEST.\n\n"
            "We are still short on talks about local-first and offline "
            "tooling, so if you have been sitting on an idea, this is the "
            "moment.\n\n"
            "Proposals: https://pyconfr.example/cfp"
        ),
        "extraction": {
            "priority": "medium",
            "tasks": [{"text": "Submit talk proposal to PyConFR", "due": "15 August"}],
            "events": [],
        },
    },
    {
        "key": "invoice",
        "folder": "INBOX",
        "sender": "Hetzner Online",
        "sender_email": "billing@hetzner.example",
        "subject": "Invoice R0042871 for July 2026",
        "hours_ago": 190,
        "unread": False,
        "body": (
            "Your invoice for July 2026 is available.\n\n"
            "Invoice number: R0042871\n"
            "Amount: EUR 23.90\n"
            "Due: 10 August 2026\n\n"
            "Payment will be collected automatically from the account on "
            "file. No action is required unless the payment fails."
        ),
        "extraction": {"priority": "low", "tasks": [], "events": []},
    },
    {
        "key": "parcel",
        "folder": "INBOX",
        "sender": "Colissimo",
        "sender_email": "suivi@colissimo.example",
        "subject": "Votre colis 6A18829937461 est en cours de livraison",
        "hours_ago": 48,
        "unread": True,
        "body": (
            "Votre colis est arrive au centre de distribution et sera livre "
            "aujourd'hui entre 9h et 13h.\n\n"
            "En cas d'absence, il sera depose au point relais le plus proche "
            "et conserve 10 jours ouvres.\n\n"
            "Suivi : https://colissimo.example/suivi/6A18829937461"
        ),
        "extraction": {"priority": "low", "tasks": [], "events": []},
    },
    {
        "key": "python_weekly",
        "folder": "Newsletters",
        "sender": "Python Weekly",
        "sender_email": "digest@pythonweekly.example",
        "subject": "Python Weekly - Issue 702",
        "hours_ago": 70,
        "unread": False,
        "body": (
            "This week: structural pattern matching in anger, a deep dive into "
            "asyncio task groups, and why your SQLite writes are slower than "
            "they should be.\n\n"
            "Articles\n"
            "- Task groups replaced my custom supervisor\n"
            "- WAL mode is not a magic bullet\n"
            "- Profiling embeddings pipelines end to end\n\n"
            "Unsubscribe: https://pythonweekly.example/unsubscribe"
        ),
        "extraction": {"priority": "low", "tasks": [], "events": []},
    },
    {
        "key": "family_dinner",
        "folder": "INBOX",
        "sender": "Marie",
        "sender_email": "marie.fontaine@example.net",
        "subject": "Diner le 1er aout ?",
        "hours_ago": 30,
        "unread": False,
        "body": (
            "Coucou,\n\n"
            "On pensait faire un diner le samedi 1er aout vers 20h a la "
            "maison, tout le monde est dispo. Tu peux venir ?\n\n"
            "Ramene juste le dessert si tu passes devant la boulangerie.\n\n"
            "Bises,\nMarie"
        ),
        # Pinned to an explicit date like the rest of the corpus: a relative
        # "samedi" resolves against the email date, so it drifts into the past
        # and then shows up under upcoming events.
        "extraction": {
            "priority": "medium",
            "tasks": [
                {"text": "Apporter le dessert pour le diner", "due": "01/08/2026"}
            ],
            "events": [
                {"title": "Diner de famille", "date": "01/08/2026", "time": "20:00"}
            ],
        },
    },
    {
        "key": "spotify",
        "folder": "Newsletters",
        "sender": "Spotify",
        "sender_email": "no-reply@spotify.example",
        "subject": "Your subscription renews on 3 August",
        "hours_ago": 240,
        "unread": False,
        "body": (
            "Your Premium Duo plan renews on 3 August 2026 for EUR 14.99 per "
            "month.\n\n"
            "No action is needed to continue. You can change or cancel your "
            "plan at any time from your account page."
        ),
        "extraction": {"priority": "low", "tasks": [], "events": []},
    },
    {
        "key": "recruiter",
        "folder": "INBOX",
        "sender": "Jonas Ekstrom",
        "sender_email": "jonas@talentbridge.example",
        "subject": "Backend role — worth a quick chat?",
        "hours_ago": 264,
        "unread": False,
        "body": (
            "Hi,\n\n"
            "I am working with a Series B company building developer tooling "
            "in Python. They are hiring a senior backend engineer, remote "
            "within Europe.\n\n"
            "Happy to send the details if you are open to a conversation. If "
            "the timing is wrong, just say so and I will not chase.\n\n"
            "Jonas"
        ),
        "extraction": {"priority": "low", "tasks": [], "events": []},
    },
]
