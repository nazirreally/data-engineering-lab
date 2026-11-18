"""Command-line entry point: python -m pipeline.cli --help"""
from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.etl import run_etl


def main() -> None:
    parser = argparse.ArgumentParser(description="Load retail orders CSV into SQLite.")
    parser.add_argument("--input", type=Path, default=Path("data/sample_orders.csv"))
    parser.add_argument("--db", type=Path, default=Path("output/retail.db"))
    parser.add_argument("--rejects", type=Path, default=Path("output/rejected_rows.csv"))
    args = parser.parse_args()
    try:
        report = run_etl(args.input, args.db, args.rejects)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(status=1, message=f"ETL failed: {exc}\n")
    print(
        f"Extracted: {report.extracted} | loaded: {report.loaded} | "
        f"rejected: {report.rejected}"
    )
    print(
        f"Total rows in warehouse: {report.warehouse_rows} | "
        f"total revenue: ${report.revenue_dollars}"
    )
    print(f"Rejected-row audit: {args.rejects}")


if __name__ == "__main__":
    main()
