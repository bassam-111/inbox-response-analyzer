#!/usr/bin/env python3
"""Inbox Response Analyzer.

A small Python/Pandas tool for an operations inbox: it reads an email log
(CSV export from a shared mailbox), measures how fast inbound client mail
gets a first reply, and writes a plain-English Markdown report plus a
per-client summary CSV.

What it measures
----------------
- First-response time for every inbound message (first outbound reply in
  the same thread, after the inbound message arrived).
- Reply rate: share of inbound messages that got any reply.
- Median / mean first-response time, overall and per client.
- Breaches against a target first-response time (default 4 hours).
- Busiest inbound hours (when client mail actually arrives).
- Per-agent outbound volume and median first-response time.
- Unanswered inbound messages older than the target: the follow-up list.

Usage
-----
    pip install -r requirements.txt
    python response_analyzer.py data/emails.csv
    python response_analyzer.py data/emails.csv --target-hours 2 --now "2026-11-06 09:00"
    python response_analyzer.py data/emails.csv --report output/report.md --summary output/summary-by-client.csv

The ``--now`` flag pins "current time" so the follow-up list is
reproducible in demos; without it the real current time is used.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {
    "message_id", "thread_id", "direction", "sender",
    "client", "subject", "sent_at", "in_reply_to",
}


def load_messages(csv_path):
    """Read the email log and validate its shape."""
    df = pd.read_csv(csv_path, parse_dates=["sent_at"])
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in {csv_path}: {sorted(missing)}")
    df["sent_at"] = pd.to_datetime(df["sent_at"])
    return df.sort_values("sent_at").reset_index(drop=True)


def first_responses(df):
    """One row per inbound message with its first reply (if any).

    A reply is the earliest outbound message in the same thread sent
    after the inbound message. Follow-up outbound messages in the same
    thread are ignored: only the first reply counts.
    """
    inbound = df[df["direction"] == "inbound"].copy()
    outbound = df[df["direction"] == "outbound"].copy()
    rows = []
    for _, msg in inbound.iterrows():
        candidates = outbound[
            (outbound["thread_id"] == msg["thread_id"])
            & (outbound["sent_at"] > msg["sent_at"])
        ]
        if candidates.empty:
            rows.append({**msg.to_dict(), "first_reply_at": pd.NaT,
                         "first_reply_by": None, "response_minutes": None})
        else:
            reply = candidates.iloc[0]
            delta = (reply["sent_at"] - msg["sent_at"]).total_seconds() / 60
            rows.append({**msg.to_dict(), "first_reply_at": reply["sent_at"],
                         "first_reply_by": reply["sender"],
                         "response_minutes": delta})
    return pd.DataFrame(rows)


def fmt_minutes(minutes):
    """Render minutes as '1h 05m' or '35m'."""
    if pd.isna(minutes):
        return "-"
    minutes = int(round(minutes))
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins:02d}m" if hours else f"{mins}m"


def analyze(df, target_hours, now):
    """Compute every metric the report needs. Returns a dict of results."""
    responses = first_responses(df)
    answered = responses.dropna(subset=["response_minutes"])
    target_minutes = target_hours * 60

    total_inbound = len(responses)
    answered_count = len(answered)
    reply_rate = answered_count / total_inbound * 100 if total_inbound else 0.0
    breaches = answered[answered["response_minutes"] > target_minutes]
    breach_rate = len(breaches) / answered_count * 100 if answered_count else 0.0

    # Unanswered mail older than the target is the follow-up list.
    stale = responses[
        responses["response_minutes"].isna()
        & ((now - responses["sent_at"]).dt.total_seconds() / 60 > target_minutes)
    ]

    # Per-client summary.
    per_client = []
    for client, group in responses.groupby("client"):
        g_answered = group.dropna(subset=["response_minutes"])
        per_client.append({
            "client": client,
            "inbound": len(group),
            "answered": len(g_answered),
            "reply_rate_pct": round(len(g_answered) / len(group) * 100, 1) if len(group) else 0.0,
            "median_response_min": round(g_answered["response_minutes"].median(), 1) if len(g_answered) else None,
            "mean_response_min": round(g_answered["response_minutes"].mean(), 1) if len(g_answered) else None,
            "breaches": int((g_answered["response_minutes"] > target_minutes).sum()),
            "unanswered": int(group["response_minutes"].isna().sum()),
        })
    per_client_df = pd.DataFrame(per_client).sort_values("inbound", ascending=False)

    # Busiest inbound hours (hour of day, 0-23).
    busy_hours = (
        responses["sent_at"].dt.hour.value_counts()
        .sort_index().rename_axis("hour").reset_index(name="inbound")
    )

    # Per-agent outbound volume and median first-response time.
    agent_rows = []
    for agent, group in answered.groupby("first_reply_by"):
        agent_rows.append({
            "agent": agent,
            "replies": len(group),
            "median_response_min": round(group["response_minutes"].median(), 1),
        })
    agents_df = pd.DataFrame(agent_rows).sort_values("replies", ascending=False)

    return {
        "responses": responses,
        "answered": answered,
        "total_inbound": total_inbound,
        "answered_count": answered_count,
        "reply_rate": reply_rate,
        "breach_count": len(breaches),
        "breach_rate": breach_rate,
        "target_minutes": target_minutes,
        "stale": stale,
        "per_client": per_client_df,
        "busy_hours": busy_hours,
        "agents": agents_df,
        "outbound_total": int((df["direction"] == "outbound").sum()),
        "period_start": df["sent_at"].min(),
        "period_end": df["sent_at"].max(),
        "now": now,
    }


def render_report(results, target_hours):
    """Build the Markdown report text."""
    r = results
    lines = [
        "# Inbox Response Report",
        "",
        f"Period: {r['period_start']:%Y-%m-%d %H:%M} to {r['period_end']:%Y-%m-%d %H:%M}  ",
        f"Checked at: {r['now']:%Y-%m-%d %H:%M}  ",
        f"First-response target: {target_hours:g} hours",
        "",
        "## Headline",
        "",
        f"- Inbound messages: **{r['total_inbound']}**",
        f"- Answered: **{r['answered_count']}** ({r['reply_rate']:.1f}% reply rate)",
        f"- Outbound messages sent: **{r['outbound_total']}**",
    ]
    if r["answered_count"]:
        lines += [
            f"- Median first response: **{fmt_minutes(r['answered']['response_minutes'].median())}**",
            f"- Mean first response: **{fmt_minutes(r['answered']['response_minutes'].mean())}**",
            f"- Slowest first response: **{fmt_minutes(r['answered']['response_minutes'].max())}**",
            f"- Breaches (over {target_hours:g}h): **{r['breach_count']}** "
            f"({r['breach_rate']:.1f}% of answered)",
        ]
    lines += ["", "## By client", "",
              "| Client | Inbound | Answered | Reply rate | Median response | Breaches | Unanswered |",
              "|--------|--------:|---------:|-----------:|----------------:|---------:|-----------:|"]
    for _, row in r["per_client"].iterrows():
        lines.append(
            f"| {row['client']} | {row['inbound']} | {row['answered']} | "
            f"{row['reply_rate_pct']:.1f}% | {fmt_minutes(row['median_response_min'])} | "
            f"{row['breaches']} | {row['unanswered']} |"
        )
    lines += ["", "## Busiest inbound hours", ""]
    for _, row in r["busy_hours"].iterrows():
        bar = "#" * int(row["inbound"])
        lines.append(f"- {int(row['hour']):02d}:00 — {row['inbound']} {bar}")
    if not r["agents"].empty:
        lines += ["", "## By agent (first replies)", "",
                  "| Agent | First replies | Median response |",
                  "|-------|--------------:|----------------:|"]
        for _, row in r["agents"].iterrows():
            lines.append(f"| {row['agent']} | {row['replies']} | "
                         f"{fmt_minutes(row['median_response_min'])} |")
    lines += ["", "## Needs follow-up", ""]
    if r["stale"].empty:
        lines.append("Nothing unanswered past the target. Inbox is clear.")
    else:
        for _, row in r["stale"].iterrows():
            waiting = fmt_minutes((r["now"] - row["sent_at"]).total_seconds() / 60)
            lines.append(
                f"- **{row['client']}** — \"{row['subject']}\" "
                f"(from {row['sender']}, {row['sent_at']:%Y-%m-%d %H:%M}, "
                f"waiting {waiting})"
            )
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Analyze first-response times in a shared operations inbox.")
    parser.add_argument("csv", help="Email log CSV (see data/emails.csv).")
    parser.add_argument("--target-hours", type=float, default=4,
                        help="First-response target in hours (default: 4).")
    parser.add_argument("--now", default=None,
                        help="Pin 'current time' as 'YYYY-MM-DD HH:MM' for reproducible reports.")
    parser.add_argument("--report", default=None,
                        help="Write the Markdown report to this path (default: print to stdout).")
    parser.add_argument("--summary", default=None,
                        help="Write the per-client summary CSV to this path.")
    args = parser.parse_args(argv)

    try:
        df = load_messages(args.csv)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    now = pd.to_datetime(args.now) if args.now else pd.Timestamp.now()
    results = analyze(df, args.target_hours, now)
    report = render_report(results, args.target_hours)

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(report, encoding="utf-8")
        print(f"Report written to {args.report}")
    else:
        print(report)

    if args.summary:
        Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
        results["per_client"].to_csv(args.summary, index=False)
        print(f"Per-client summary written to {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
