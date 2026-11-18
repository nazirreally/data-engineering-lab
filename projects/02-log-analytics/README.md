# Project 02 — HTTP Log Analytics & Monitoring Engine

A dependency-free Python + SQLite project that transforms newline-delimited JSON HTTP logs into queryable operational metrics. Built as a reproducible Data Engineering / Backend Engineering portfolio demonstration.

## Architecture

\`\`\`text
JSONL HTTP logs
    |
    v
Validate JSON, fields, timestamps, status & latency
    |                                |
    v                                v
Idempotent SQLite ingest       Rejected-row audit JSONL
    |
    v
Service + endpoint aggregations
    |
    v
JSON metrics report (error rates, mean latency, nearest-rank p95)
\`\`\`

## Quick start

Requires **Python 3.10+**. No external packages or cloud accounts needed.

From the repository root:

\`\`\`bash
python projects/02-log-analytics/log_analytics.py ingest \
  --input projects/02-log-analytics/data/sample_logs.jsonl \
  --db output/log_analytics.db \
  --rejects output/rejected_logs.jsonl

python projects/02-log-analytics/log_analytics.py report \
  --db output/log_analytics.db \
  --output output/log_report.json

python -m unittest discover -s projects/02-log-analytics/tests -v
\`\`\`

Windows PowerShell users can run each command on one line instead of using Bash's backslash continuation.

## Input contract

Each UTF-8 JSONL line contains:

\`\`\`json
{"timestamp":"2026-11-18T09:00:00Z","service":"gateway","path":"/api/users","status":200,"latency_ms":42}
\`\`\`

- \`timestamp\`: ISO-8601 with timezone (normalized to UTC).
- \`service\`: nonempty string, at most 100 characters.
- \`path\`: URL path beginning with \`/\`, at most 256 characters.
- \`status\`: integer HTTP code 100–599.
- \`latency_ms\`: nonnegative finite number.
- Invalid rows are skipped, counted and optionally written to an audit file.

## Report metrics

- Total request volume
- Requests per service
- **Server error rate**: 5xx responses divided by all responses
- Arithmetic mean latency (ms)
- **p95 latency**: nearest-rank 95th percentile
- Top 10 \`(service, path)\` combinations by count

## Engineering decisions

- SQLite database with primary-key deduplication and a service/time index.
- Idempotency key combines absolute source path, line number and original line. Importing the same file twice is safe. Moving or changing the file changes record identity by design.
- Full JSON validation, explicit timezone handling, and audit output for rejected lines.
- Parameterized SQL queries and standard-library-only implementation.
- Four automated tests: idempotency, rejected rows, aggregate correctness, invalid input.
- GitHub Actions automatically runs the project's unit tests.

## Limits and next steps

This is an **offline batch analytics demonstration**, not a deployed real-time monitoring service. The entire report is calculated in memory for simplicity. Future enhancements: streaming ingestion, Prometheus output, FastAPI metrics endpoint, hourly rollups, Docker packaging, and a Grafana dashboard.

**Data notice:** All sample logs are synthetic.
