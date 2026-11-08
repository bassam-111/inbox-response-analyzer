# Inbox Response Analyzer

A small Python/Pandas command-line tool for a shared operations inbox. It
reads an email log (a CSV export from a shared mailbox), measures how fast
inbound client mail gets a first reply, and produces a plain-English
Markdown report plus a per-client summary CSV — the kind of check an
Operations Executive runs each morning to see what is slipping.

Built with **Python and Pandas** — skills on the resume, nothing extra
claimed. All clients, people and email addresses in the sample data are
fictional.

## What it does

- **First-response time** for every inbound message: the first outbound
  reply in the same thread, sent after the inbound message arrived.
  Follow-up replies in the same thread are ignored, so only the first
  reply counts.
- **Reply rate**: share of inbound messages that got any reply.
- **Median / mean / slowest** first-response time, overall and per client.
- **Breaches** against a configurable target (default 4 hours).
- **Busiest inbound hours**: when client mail actually arrives, so cover
  can be planned around it.
- **Per-agent stats**: outbound volume and median first-response time.
- **Follow-up list**: inbound messages still unanswered past the target.

## Files

| File | What it is |
|------|-----------|
| `response_analyzer.py` | The analyzer (CLI, Pandas) |
| `data/emails.csv` | Sample email log: 28 messages, 4 fictional clients, 2–5 Nov 2026 |
| `requirements.txt` | `pandas>=2.0` |
| `tests/test_analyzer.py` | 5 tests (first-reply logic, unanswered mail, reply rate, formatting, sample data) |
| `output/report.md` | Sample report generated from the sample data |
| `output/summary-by-client.csv` | Sample per-client summary |

## How to run

```bash
pip install -r requirements.txt

# Print the report for the sample data
python response_analyzer.py data/emails.csv

# Stricter 2-hour target, reproducible "now" for the follow-up list
python response_analyzer.py data/emails.csv --target-hours 2 --now "2026-11-06 09:00"

# Write the report and per-client summary to files
python response_analyzer.py data/emails.csv --target-hours 4 --now "2026-11-06 09:00" \
    --report output/report.md --summary output/summary-by-client.csv

# Run the tests (pytest optional; plain python works too)
python tests/test_analyzer.py
python -m pytest tests/ -q
```

## Input format

One row per message. `in_reply_to` is optional; threads are matched on
`thread_id` and timestamps.

```csv
message_id,thread_id,direction,sender,client,subject,sent_at,in_reply_to
m001,T1,inbound,client@northwind.example,Northwind Retail,Invoice discrepancy,2026-11-02 09:12,
m002,T1,outbound,Bassam Zafar,Northwind Retail,Re: Invoice discrepancy,2026-11-02 09:47,m001
```

## Sample output

Report generated from `data/emails.csv` with the default 4-hour target
(checked at 2026-11-06 09:00):

- Inbound messages: **14**, answered: **12** (85.7% reply rate)
- Median first response: **35m** · Mean: **2h 32m** · Slowest: **17h 30m**
- Breaches (over 4h): **2** (16.7% of answered)
- Best client: Northwind Retail and Bluepeak Media, 100% reply rate;
  weakest: Harbor Foods, 66.7% (1 breach, 1 unanswered)
- Busiest inbound hours: 09:00–11:00 and 15:00
- Needs follow-up: Harbor Foods "New starter onboarding checklist"
  (waiting 88h 20m) and Acme Logistics "Driver shift cover for
  Thursday" (waiting 44h 40m)

See `output/report.md` for the full report.

## Test result

All 5 tests pass (`python tests/test_analyzer.py` → "All tests passed.").
Report numbers were also checked by hand against the sample data
(median 35m, 2 breaches, 2 items on the follow-up list).
