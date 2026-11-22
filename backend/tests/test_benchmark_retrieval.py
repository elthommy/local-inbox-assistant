"""Retrieval benchmark helpers: email grouping, ranks, cross-language flags."""

import re
from datetime import date

import numpy as np

from scripts.benchmark_retrieval import (
    CONFIGS,
    LOOKUP_QUESTIONS,
    NEAR_DUP_REFS,
    near_duplicates,
    rank_of,
    retrieval_questions,
    summary_row,
    top_emails,
)


def test_top_emails_groups_chunks_by_email():
    owners = ["a", "a", "b", "c"]
    scores = np.array([0.9, 0.8, 0.7, 0.1])
    assert top_emails(scores, owners, k=2) == ["a", "b"]


def test_rank_of_uses_each_email_best_chunk():
    owners = ["a", "b", "b"]
    scores = np.array([0.5, 0.1, 0.9])
    assert rank_of(scores, owners, "b") == 1
    assert rank_of(scores, owners, "a") == 2


def test_retrieval_questions_flag_cross_language():
    corpus = [
        {"key": "parcel", "body": "Votre colis a été déposé dans votre boîte."},
        {"key": "invoice", "body": "Your invoice for October is available."},
    ]
    qs = {
        q["id"]: q
        for q in retrieval_questions(corpus)
        if q["id"] in ("parcel", "invoice")
    }
    assert qs["parcel"]["cross"] and not qs["invoice"]["cross"]
    assert qs["parcel"]["target"] == "demo:parcel"


def test_summary_row_splits_cross_and_same_language():
    res = {
        "label": "m",
        "chunks_per_s": 10.0,
        "questions": {
            "x": {"hit": True, "rank": 1, "cross": True, "group": "chat"},
            "y": {"hit": False, "rank": 10, "cross": False, "group": "chat"},
            "z": {"hit": True, "rank": 2, "cross": False, "group": "lookup"},
        },
    }
    row = summary_row(res)
    assert row["top6_chat"] == "1/2"
    assert row["cross_lang"] == "1/1" and row["same_lang"] == "0/1"
    assert row["mrr_chat"] == 0.55 and row["missed"] == "y"
    assert row["lookup"] == "1/1" and row["mrr_lookup"] == 0.5


def test_summary_row_reads_results_saved_before_groups():
    res = {
        "label": "old",
        "chunks_per_s": 1.0,
        "questions": {"x": {"hit": True, "rank": 1, "cross": False}},
    }
    row = summary_row(res)
    assert row["top6_chat"] == "1/1" and row["lookup"] == "0/0"
    assert row["mrr_lookup"] == "-"


def test_lookup_questions_point_at_demo_emails():
    from scripts.demo_corpus import rendered_corpus

    keys = {e["key"] for e in rendered_corpus(date(2026, 11, 2))}
    for q in LOOKUP_QUESTIONS:
        assert q["source"][0] in keys, q["id"]


def test_retrieval_questions_tag_lookup_group():
    corpus = [{"key": "invoice", "body": "Your invoice for October is available."}]
    qs = {q["id"]: q for q in retrieval_questions(corpus)}
    assert qs["invoice"]["group"] == "chat"
    assert qs["ref_invoice"]["group"] == "lookup"
    assert not qs["ref_invoice"]["cross"]


def test_config_labels_are_unique():
    labels = [c[0] for c in CONFIGS]
    assert len(labels) == len(set(labels))


def test_question_ids_are_unique_across_sets():
    from scripts.chat_eval import QUESTIONS

    ids = [q["id"] for q in QUESTIONS + LOOKUP_QUESTIONS]
    assert len(ids) == len(set(ids))


def _demo_rows() -> list[dict]:
    rows = rendered_demo()
    return [
        {**r, "id": f"demo:{r['key']}", "date_utc": "2026-11-22T08:00:00+00:00"}
        for r in rows
    ]


def rendered_demo() -> list[dict]:
    from scripts.demo_corpus import rendered_corpus

    return [
        {
            "key": e["key"],
            "sender": e["sender"],
            "sender_email": e["sender_email"],
            "subject": e["subject"],
            "body": e.get("body", ""),
        }
        for e in rendered_corpus(date(2026, 11, 22))
    ]


def test_near_duplicates_change_only_the_references():
    demo = _demo_rows()
    dups = near_duplicates(demo, 3, seed_n=1)
    assert len(dups) == 3 * len(NEAR_DUP_REFS)
    invoice = next(r for r in demo if r["key"] == "invoice")
    copies = [d for d in dups if d["id"].startswith("dup:invoice:")]
    for d in copies:
        assert d["key"] is None and d["sender"] == invoice["sender"]
        assert "CN-11187" not in d["body"] and "23.90" not in d["body"]
        assert re.sub(r"CN-\d+|EUR \S+", "", d["body"]) == re.sub(
            r"CN-\d+|EUR \S+", "", invoice["body"]
        )
    assert [d["date_utc"][:10] for d in copies] == [
        "2026-11-15",
        "2026-11-08",
        "2026-11-01",
    ]


def test_near_duplicates_replace_every_occurrence_of_a_reference():
    demo = _demo_rows()
    pr = next(
        d for d in near_duplicates(demo, 1, seed_n=2) if d["id"] == "dup:code_review:0"
    )
    assert "512" not in pr["subject"] + pr["body"]
    [number] = set(re.findall(r"(?<=#)\d+", pr["subject"]))
    assert f"#{number}" in pr["body"] and f"/pull/{number}" in pr["body"]


def test_near_dups_make_chat_questions_on_copied_emails_ambiguous():
    corpus = [
        {"key": "invoice", "body": "Your invoice for October is available."},
        {"key": "dentist", "body": "Rappel : rendez-vous le 3 à 14h30."},
    ]
    qs = {q["id"]: q for q in retrieval_questions(corpus, near_dups=5)}
    assert qs["invoice"]["group"] == "ambiguous"
    assert qs["ref_invoice"]["group"] == "lookup"
    assert qs["dentist"]["group"] == "chat"
