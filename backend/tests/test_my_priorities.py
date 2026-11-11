from app.my_priorities import rule_names_sender, rules_for_sender, sender_names

RULES = (
    'Votes on my ClubFunding investments ("une action est requise dans votre'
    ' Espace Club") are high priority.\n'
    "\n"
    "  - Mail from the École Jules Ferry is high.  \n"
    "Jane's messages are high."
)


def test_sender_names_from_display_name_and_org_domain():
    assert sender_names("ClubFunding", "noreply@news.clubfunding-group.com") == {
        "clubfunding",
        "clubfundinggroup",
    }


def test_sender_names_use_local_part_only_at_personal_providers():
    assert sender_names("", "jane.doe@gmail.com") == {"jane"}
    assert sender_names("", "statements@mail.vendor.com") == {"vendor"}


def test_sender_names_skip_generic_words():
    assert sender_names("Votre Espace Client", "info@x.io") == set()


def test_rule_matches_org_domain():
    assert rule_names_sender(RULES.splitlines()[0], "", "noreply@clubfunding.eu")


def test_rule_matches_run_together_name():
    assert rule_names_sender("Club Funding votes are high", "", "a@clubfunding.eu")


def test_rule_matching_ignores_case_and_accents():
    assert rule_names_sender("Mail from the ECOLE is high", "École Jules Ferry", "")


def test_quoted_common_words_do_not_reach_other_senders():
    rule = RULES.splitlines()[0]
    assert not rule_names_sender(rule, "Votre banque", "alerts@caisse.example")
    assert not rule_names_sender(rule, "Club Med", "news@clubmed.example")
    assert not rule_names_sender(rule, "Mon Espace Santé", "x@sante.example")


def test_short_names_only_match_whole_rule_words():
    assert not rule_names_sender("Acmeworks mail is high", "", "a@acme.com")
    assert rule_names_sender("Acme mail is high", "", "a@acme.com")


def test_rules_for_sender_keeps_only_matching_lines():
    assert (
        rules_for_sender(RULES, "Club Funding", "noreply@clubfunding.fr")
        == (RULES.splitlines()[0])
    )
    assert rules_for_sender(RULES, "Ecole Jules Ferry", "") == (
        "- Mail from the École Jules Ferry is high."
    )
    assert rules_for_sender(RULES, "", "jane@gmail.com") == "Jane's messages are high."


def test_rules_for_sender_empty_when_no_rule_names_sender():
    assert rules_for_sender(RULES, "Shop", "deals@shop.example") == ""
    assert rules_for_sender("", "Club Funding", "") == ""
    assert rules_for_sender(RULES, None, None) == ""
