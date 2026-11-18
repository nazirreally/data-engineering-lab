"""Dependency-free HTTP log analytics: validate, ingest, summarize.

Usage:
  python log_analytics.py ingest --input data/sample_logs.jsonl --db output/events.db
  python log_analytics.py report --db output/events.db --output output/report.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    occurred_at TEXT NOT NULL,
    service TEXT NOT NULL,
    path TEXT NOT NULL,
    status INTEGER NOT NULL,
    latency_ms REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_service_time ON events(service, occurred_at);
"""


def normalize_event(value: Any) -> dict[str, Any]:
    """Validate and normalize one JSON object, rejecting ambiguous values."""
    if not isinstance(value, dict):
        raise ValueError("event must be a JSON object")
    timestamp = value.get("timestamp")
    if not isinstance(timestamp, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone information")
    service = value.get("service")
    if not isinstance(service, str) or not service.strip() or len(service) > 100:
        raise ValueError("service must be a nonempty string (max 100 chars)")
    path = value.get("path")
    if not isinstance(path, str) or not path.startswith("/") or len(path) > 256:
        raise ValueError("path must start with / and be at most 256 chars")
    status = value.get("status")
    if type(status) is not int or not 100 <= status <= 599:
        raise ValueError("status must be an HTTP status integer (100..599)")
    latency = value.get("latency_ms")
    if type(latency) not in (int, float) or not math.isfinite(latency) or latency < 0:
        raise ValueError("latency_ms must be a finite nonnegative number")
    return {
        "occurred_at": parsed.astimezone(timezone.utc).isoformat(),
        "service": service.strip(),
        "path": path,
        "status": status,
        "latency_ms": float(latency),
    }


def ingest_file(input_path: Path, database_path: Path, rejects_path: Path | None = None) -> dict[str, int]:
    """Ingest JSONL idempotently. Re-importing the same file skips existing rows."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if rejects_path is not None:
        rejects_path.parent.mkdir(parents=True, exist_ok=True)
    stats = {"processed": 0, "inserted": 0, "duplicates": 0, "rejected": 0}
    with sqlite3.connect(database_path) as conn:
        conn.executescript(SCHEMA)
        reject_out = rejects_path.open("w", encoding="utf-8") if rejects_path else None
        try:
            with input_path.open("r", encoding="utf-8") as source:
                for lineno, line in enumerate(source, 1):
                    if not line.strip():
                        continue
                    stats["processed"] += 1
                    try:
                        value = normalize_event(json.loads(line))
                    except (ValueError, json.JSONDecodeError) as exc:
                        stats["rejected"] += 1
                        if reject_out is not None:
                            reject_out.write(json.dumps({
                                "line": lineno, "error": str(exc), "raw": line.rstrip("\n")
                            }) + "\n")
                        continue
                    key_material = f"{input_path.resolve()}:{lineno}:{line.rstrip()}".encode("utf-8")
                    event_id = hashlib.sha256(key_material).hexdigest()
                    cursor = conn.execute(
                        """INSERT OR IGNORE INTO events
                        (event_id, occurred_at, service, path, status, latency_ms)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (event_id, value["occurred_at"], value["service"],
                         value["path"], value["status"], value["latency_ms"]),
                    )
                    if cursor.rowcount == 1:
                        stats["inserted"] += 1
                    else:
                        stats["duplicates"] += 1
        finally:
            if reject_out is not None:
                reject_out.close()
    return stats


def summarize(database_path: Path) -> dict[str, Any]:
    """Calculate service-level error rate, mean latency and nearest-rank p95."""
    by_service: dict[str, list[tuple[int, float]]] = defaultdict(list)
    paths: dict[tuple[str, str], int] = defaultdict(int)
    with sqlite3.connect(database_path) as conn:
        conn.executescript(SCHEMA)
        records = conn.execute(
            "SELECT service, path, status, latency_ms FROM events ORDER BY service, path"
        )
        for service, path, status, latency in records:
            by_service[service].append((status, latency))
            paths[(service, path)] += 1
    services = []
    for name, events in sorted(by_service.items()):
        count = len(events)
        latencies = sorted(latency for _, latency in events)
        errors = sum(status >= 500 for status, _ in events)
        services.append({
            "service": name,
            "requests": count,
            "server_errors": errors,
            "server_error_rate_pct": round(100 * errors / count, 2),
            "avg_latency_ms": round(sum(latencies) / count, 2),
            "p95_latency_ms": latencies[math.ceil(0.95 * count) - 1],
        })
    popular_paths = [
        {"service": s, "path": p, "requests": n}
        for (s, p), n in sorted(paths.items(), key=lambda pair: (-pair[1], pair[0]))[:10]
    ]
    return {
        "total_requests": sum(len(events) for events in by_service.values()),
        "services": services,
        "top_paths": popular_paths,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Local HTTP log analytics with SQLite")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="Validate and load newline-delimited JSON")
    ingest.add_argument("--input", required=True, type=Path)
    ingest.add_argument("--db", required=True, type=Path)
    ingest.add_argument("--rejects", type=Path, help="Optional rejected-row audit JSONL")
    report = commands.add_parser("report", help="Export HTTP metrics as JSON")
    report.add_argument("--db", required=True, type=Path)
    report.add_argument("--output", type=Path, help="Write JSON to a file instead of stdout")
    args = parser.parse_args()
    if args.command == "ingest":
        print(json.dumps(ingest_file(args.input, args.db, args.rejects), indent=2))
    else:
        payload = json.dumps(summarize(args.db), indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
            print(f"Report written to {args.output}")
        else:
            print(payload, end="")


if __name__ == "__main__":
    main()
