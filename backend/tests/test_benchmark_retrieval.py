"""Retrieval benchmark helpers: email grouping, ranks, cross-language flags."""

import numpy as np

from scripts.benchmark_retrieval import (
    CONFIGS,
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
            "x": {"hit": True, "rank": 1, "cross": True},
            "y": {"hit": False, "rank": 10, "cross": False},
        },
    }
    row = summary_row(res)
    assert row["cross_lang"] == "1/1" and row["same_lang"] == "0/1"
    assert row["mrr"] == 0.55 and row["missed"] == "y"


def test_config_labels_are_unique():
    labels = [c[0] for c in CONFIGS]
    assert len(labels) == len(set(labels))
