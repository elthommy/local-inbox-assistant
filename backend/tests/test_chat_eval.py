"""Chat benchmark scoring: date spellings, fact matching, language, budget."""

from datetime import date

from scripts.benchmark_chat import over_budget, summarize_model, todo_items
from scripts.chat_eval import (
    QUESTIONS,
    date_variants,
    detect_language,
    facts_found,
    score_answer,
)

SEED = date(2026, 11, 2)


def test_date_variants_cover_en_and_fr_spellings():
    variants = date_variants(SEED, 4)
    for v in ("6 November", "November 6", "6th November", "6 novembre", "06/11"):
        assert v in variants


def test_date_variants_first_of_month_in_french():
    assert "1er décembre" in date_variants(date(2026, 11, 30), 1)


def test_facts_found_is_accent_and_case_insensitive():
    expect = [["façade"], ["@date:+6"]]
    assert facts_found("Vote on the FACADE work, Sunday 8 November", expect, SEED) == [
        True,
        True,
    ]


def test_short_numbers_need_word_edges():
    assert facts_found("pool size went from 50 to 5.", [["5"]], SEED) == [True]
    assert facts_found("the 5xx rate is 50%", [["5"]], SEED) == [False]


def test_detect_language():
    assert detect_language("The tax is due on Friday, you need to pay it.") == "en"
    assert detect_language("La taxe est à payer avant vendredi, pour vous.") == "fr"


def test_detect_language_ignores_quoted_subjects():
    text = 'You have to pay it: "Taxe foncière : à payer avant le vendredi pour la"'
    assert detect_language(text) == "en"


def test_score_answer_flags_language_drift():
    q = next(q for q in QUESTIONS if q["id"] == "tax")
    good = score_answer(q, "It is 1 284 € and is due on 6 November.", SEED)
    drift = score_answer(
        q, "Le montant est de 1 284 €, à payer avant le 6 novembre.", SEED
    )
    assert good["pass"] and not drift["pass"]
    assert drift["lang"] == "fr" and drift["facts"] == 2


def test_summary_question_expects_the_email_language():
    q = next(q for q in QUESTIONS if q["id"] == "sum_fr")
    text = "- Assemblée générale le dimanche 8 novembre, vote sur le ravalement."
    assert score_answer(q, text, SEED)["pass"]


def test_question_ids_are_unique():
    ids = [q["id"] for q in QUESTIONS]
    assert len(ids) == len(set(ids))


def test_todo_items_skips_done_answers():
    done = {f"{QUESTIONS[0]['id']}#0": {}}
    todo = todo_items(done, repeats=2)
    assert len(todo) == 2 * len(QUESTIONS) - 1
    assert todo[0][0] == f"{QUESTIONS[1]['id']}#0"


def test_over_budget_needs_enough_probe_answers():
    assert over_budget({"a": {"total_s": 100}}) is None
    slow = {k: {"total_s": 100} for k in "abc"}
    assert over_budget(slow) == 100
    assert over_budget({k: {"total_s": 5} for k in "abc"}) is None


def test_summarize_model_counts_errors_and_passes():
    state = {
        "results": {
            "m": {
                "tax#0": {
                    "answer": "1 284 € due 6 November, you must pay it.",
                    "ttft_s": 1.0,
                    "total_s": 4.0,
                    "eval_count": 100,
                    "eval_duration": 2e9,
                    "seed_day": "2026-11-02",
                },
                "dinner#0": {"error": "boom", "seed_day": "2026-11-02"},
            }
        },
        "dropped": {},
        "load_s": {"m": 3.0},
    }
    row = summarize_model("m", state)
    assert row["answers"] == 1 and row["errors"] == 1
    assert row["pass"] == "100%" and row["tok_s"] == 50.0


def test_weekday_token_and_zero_padded_dates():
    assert facts_found("avant jeudi", [["@wd:+3"]], SEED) == [True]
    assert facts_found("le 05 novembre", [["@date:+3"]], SEED) == [True]


def test_any_answer_language_skips_the_language_check():
    q = next(q for q in QUESTIONS if q["id"] == "sum_en")
    assert score_answer(q, "Sarah veut l'uptime avant 16:00.", SEED)["lang_ok"]
