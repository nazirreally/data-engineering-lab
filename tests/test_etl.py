"""Regression tests for extraction, data quality, upserts, and sample data."""
import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pipeline.etl import COLUMNS, ROOT, run_etl


class ETLTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name)
        self.csv_path = folder / "input.csv"
        self.db_path = folder / "warehouse.db"
        self.rejects_path = folder / "rejects.csv"

    def write_orders(self, rows, columns=COLUMNS):
        with self.csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def order(**overrides):
        row = {
            "order_id": "O-1",
            "order_date": "2026-10-01",
            "customer_id": "C-1",
            "region": "North",
            "product_sku": "SKU-1",
            "product_name": "Notebook",
            "quantity": "2",
            "unit_price": "12.50",
        }
        row.update(overrides)
        return row

    def run_pipeline(self):
        return run_etl(self.csv_path, self.db_path, self.rejects_path)

    def test_first_load_creates_dimensions_and_fact(self):
        self.write_orders([self.order()])
        report = self.run_pipeline()
        self.assertEqual((report.extracted, report.loaded, report.rejected), (1, 1, 0))
        self.assertEqual(report.revenue_cents, 2500)
        with sqlite3.connect(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM dim_customers").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM dim_products").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM fact_orders").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_rerun_is_idempotent(self):
        self.write_orders([self.order()])
        self.run_pipeline()
        report = self.run_pipeline()
        self.assertEqual(report.warehouse_rows, 1)
        self.assertEqual(report.revenue_cents, 2500)

    def test_existing_order_updates_in_place(self):
        self.write_orders([self.order()])
        self.run_pipeline()
        self.write_orders([self.order(quantity="3", unit_price="1.10")])
        report = self.run_pipeline()
        self.assertEqual(report.warehouse_rows, 1)
        self.assertEqual(report.revenue_cents, 330)

    def test_invalid_and_duplicate_rows_are_audited(self):
        self.write_orders([
            self.order(),
            self.order(),  # duplicate ID within this CSV
            self.order(order_id="O-2", quantity="0"),
            self.order(order_id="O-3", order_date="2026-02-30"),
            self.order(order_id="O-4", unit_price="12.345"),
            self.order(order_id="O-5", customer_id=""),
        ])
        report = self.run_pipeline()
        self.assertEqual((report.extracted, report.loaded, report.rejected), (6, 1, 5))
        with self.rejects_path.open(newline="", encoding="utf-8") as handle:
            rejected = list(csv.DictReader(handle))
        self.assertEqual(len(rejected), 5)
        self.assertIn("duplicate", rejected[0]["error"])
        self.assertEqual(report.revenue_cents, 2500)

    def test_missing_column_fails_fast(self):
        columns = tuple(column for column in COLUMNS if column != "product_name")
        self.write_orders([{k: self.order()[k] for k in columns}], columns=columns)
        with self.assertRaisesRegex(ValueError, "product_name"):
            self.run_pipeline()
        self.assertFalse(self.db_path.exists())

    def test_cents_are_exact(self):
        self.write_orders([self.order(unit_price="0.10", quantity="3")])
        self.assertEqual(self.run_pipeline().revenue_cents, 30)

    def test_repository_sample_data(self):
        report = run_etl(ROOT / "data" / "sample_orders.csv", self.db_path, self.rejects_path)
        self.assertEqual((report.extracted, report.loaded, report.rejected), (12, 12, 0))
        self.assertEqual(report.revenue_cents, 98690)


if __name__ == "__main__":
    unittest.main()
