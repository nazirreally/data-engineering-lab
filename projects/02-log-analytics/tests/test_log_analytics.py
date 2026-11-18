"""Tests for the standalone log analytics implementation."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("log_analytics", PROJECT / "log_analytics.py")
log_analytics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(log_analytics)


def event(status=200, latency=10, service="api", path="/health"):
    return {
        "timestamp": "2026-11-18T12:00:00Z",
        "service": service,
        "path": path,
        "status": status,
        "latency_ms": latency,
    }


class LogAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.db = self.dir / "db" / "events.db"
        self.input = self.dir / "events.jsonl"

    def write(self, *lines):
        self.input.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_idempotent_import(self):
        self.write(json.dumps(event()), json.dumps(event(503, 200)))
        first = log_analytics.ingest_file(self.input, self.db)
        second = log_analytics.ingest_file(self.input, self.db)
        self.assertEqual(first, {"processed": 2, "inserted": 2, "duplicates": 0, "rejected": 0})
        self.assertEqual(second["duplicates"], 2)
        self.assertEqual(log_analytics.summarize(self.db)["total_requests"], 2)

    def test_rejects_malformed_records_and_writes_audit(self):
        self.write("{broken", json.dumps(event(status=True)), json.dumps(event(latency=-5)),
                   json.dumps(event()))
        rejects = self.dir / "rejects.jsonl"
        stats = log_analytics.ingest_file(self.input, self.db, rejects)
        self.assertEqual((stats["inserted"], stats["rejected"]), (1, 3))
        reasons = [json.loads(line) for line in rejects.read_text().splitlines()]
        self.assertEqual(len(reasons), 3)
        self.assertEqual([r["line"] for r in reasons], [1, 2, 3])

    def test_service_metrics_and_p95(self):
        self.write(
            json.dumps(event(200, 10, "api", "/users")),
            json.dumps(event(500, 20, "api", "/users")),
            json.dumps(event(200, 30, "api", "/orders")),
            json.dumps(event(200, 40, "api", "/orders")),
            json.dumps(event(200, 15, "worker", "/health")),
        )
        log_analytics.ingest_file(self.input, self.db)
        result = log_analytics.summarize(self.db)
        self.assertEqual(result["total_requests"], 5)
        api = next(s for s in result["services"] if s["service"] == "api")
        self.assertEqual(api["server_error_rate_pct"], 25)
        self.assertEqual(api["avg_latency_ms"], 25)
        self.assertEqual(api["p95_latency_ms"], 40)
        self.assertEqual(result["top_paths"][0]["requests"], 2)

    def test_requires_timezone_and_finite_latency(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            log_analytics.normalize_event({**event(), "timestamp": "2026-11-18T12:00:00"})
        with self.assertRaisesRegex(ValueError, "finite"):
            log_analytics.normalize_event({**event(), "latency_ms": float("inf")})


if __name__ == "__main__":
    unittest.main()
