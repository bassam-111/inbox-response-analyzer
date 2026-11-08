"""Tests for the inbox response analyzer. Run with: python -m pytest tests/ -q
(or plain: python tests/test_analyzer.py)."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from response_analyzer import analyze, first_responses, fmt_minutes, load_messages  # noqa: E402


def _tiny_df():
    return pd.DataFrame([
        {"message_id": "a1", "thread_id": "T1", "direction": "inbound",
         "sender": "c@example.com", "client": "Client A", "subject": "Help",
         "sent_at": pd.Timestamp("2026-11-02 09:00"), "in_reply_to": ""},
        {"message_id": "a2", "thread_id": "T1", "direction": "outbound",
         "sender": "Bassam Zafar", "client": "Client A", "subject": "Re: Help",
         "sent_at": pd.Timestamp("2026-11-02 09:30"), "in_reply_to": "a1"},
        # Second outbound in the same thread must NOT change the first response.
        {"message_id": "a3", "thread_id": "T1", "direction": "outbound",
         "sender": "Bassam Zafar", "client": "Client A", "subject": "Re: Help",
         "sent_at": pd.Timestamp("2026-11-02 11:00"), "in_reply_to": "a2"},
        {"message_id": "b1", "thread_id": "T2", "direction": "inbound",
         "sender": "d@example.com", "client": "Client B", "subject": "Question",
         "sent_at": pd.Timestamp("2026-11-02 10:00"), "in_reply_to": ""},
    ])


def test_first_response_uses_earliest_reply():
    resp = first_responses(_tiny_df())
    t1 = resp[resp["thread_id"] == "T1"].iloc[0]
    assert t1["response_minutes"] == 30.0
    assert t1["first_reply_by"] == "Bassam Zafar"


def test_unanswered_message_has_no_response_time():
    resp = first_responses(_tiny_df())
    t2 = resp[resp["thread_id"] == "T2"].iloc[0]
    assert pd.isna(t2["response_minutes"])


def test_reply_rate_and_breach_counts():
    results = analyze(_tiny_df(), target_hours=1, now=pd.Timestamp("2026-11-02 12:00"))
    assert results["total_inbound"] == 2
    assert results["answered_count"] == 1
    assert results["reply_rate"] == 50.0
    assert results["breach_count"] == 0  # 30 min reply is inside the 1h target
    assert len(results["stale"]) == 1  # T2 unanswered for 2h > 1h target


def test_fmt_minutes():
    assert fmt_minutes(35) == "35m"
    assert fmt_minutes(65) == "1h 05m"
    assert fmt_minutes(float("nan")) == "-"


def test_sample_data_loads():
    base = Path(__file__).resolve().parent.parent
    df = load_messages(base / "data" / "emails.csv")
    assert len(df) == 28
    assert df["direction"].value_counts()["inbound"] == 14


if __name__ == "__main__":
    test_first_response_uses_earliest_reply()
    test_unanswered_message_has_no_response_time()
    test_reply_rate_and_breach_counts()
    test_fmt_minutes()
    test_sample_data_loads()
    print("All tests passed.")
