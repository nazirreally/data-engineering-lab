"""Extract, validate and upsert retail orders into a small SQLite warehouse."""
from __future__ import annotations

import csv
import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "sql" / "schema.sql"
COLUMNS = (
    "order_id",
    "order_date",
    "customer_id",
    "region",
    "product_sku",
    "product_name",
    "quantity",
    "unit_price",
)


@dataclass(frozen=True)
class ETLReport:
    extracted: int
    loaded: int
    rejected: int
    warehouse_rows: int
    revenue_cents: int

    @property
    def revenue_dollars(self) -> str:
        return f"{self.revenue_cents / 100:,.2f}"


def _required(row: dict, key: str) -> str:
    value = row.get(key)
    if value is None or not str(value).strip():
        raise ValueError(f"{key}: required field is blank")
    return str(value).strip()


def validate_order(row: dict) -> dict:
    """Normalize one row, rejecting invalid inputs before database writes."""
    fields = {key: _required(row, key) for key in COLUMNS}
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fields["order_date"]):
        raise ValueError("order_date: expected YYYY-MM-DD")
    try:
        date.fromisoformat(fields["order_date"])
    except ValueError as exc:
        raise ValueError("order_date: invalid calendar date") from exc

    try:
        quantity = int(fields["quantity"])
    except ValueError as exc:
        raise ValueError("quantity: expected an integer") from exc
    if quantity <= 0:
        raise ValueError("quantity: must be positive")

    try:
        price = Decimal(fields["unit_price"])
        if not price.is_finite() or price < 0 or price != price.quantize(Decimal("0.01")):
            raise ValueError("unit_price: expected a nonnegative value with at most 2 decimals")
    except InvalidOperation as exc:
        raise ValueError("unit_price: invalid decimal value") from exc

    cents = int(price * 100)
    if cents > 9_000_000_000_000_000_000 // quantity:
        raise ValueError("revenue: amount is too large")
    return {
        **{key: fields[key] for key in COLUMNS[:6]},
        "quantity": quantity,
        "unit_price_cents": cents,
        "revenue_cents": cents * quantity,
    }


def _upsert_order(conn: sqlite3.Connection, order: dict) -> None:
    conn.execute(
        """INSERT INTO dim_customers(customer_id, region) VALUES (?, ?)
           ON CONFLICT(customer_id) DO UPDATE SET region=excluded.region""",
        (order["customer_id"], order["region"]),
    )
    conn.execute(
        """INSERT INTO dim_products(product_sku, product_name) VALUES (?, ?)
           ON CONFLICT(product_sku) DO UPDATE SET product_name=excluded.product_name""",
        (order["product_sku"], order["product_name"]),
    )
    conn.execute(
        """INSERT INTO fact_orders(
               order_id, order_date, customer_id, product_sku,
               quantity, unit_price_cents, revenue_cents
           ) VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(order_id) DO UPDATE SET
               order_date=excluded.order_date,
               customer_id=excluded.customer_id,
               product_sku=excluded.product_sku,
               quantity=excluded.quantity,
               unit_price_cents=excluded.unit_price_cents,
               revenue_cents=excluded.revenue_cents""",
        (
            order["order_id"], order["order_date"], order["customer_id"],
            order["product_sku"], order["quantity"],
            order["unit_price_cents"], order["revenue_cents"],
        ),
    )


def _quality_metrics(conn: sqlite3.Connection) -> tuple[int, int]:
    """Fail the transaction if a key warehouse invariant is broken."""
    bad_amounts = conn.execute(
        "SELECT COUNT(*) FROM fact_orders WHERE revenue_cents != quantity * unit_price_cents"
    ).fetchone()[0]
    broken_keys = conn.execute(
        """SELECT COUNT(*) FROM fact_orders f
           LEFT JOIN dim_customers c ON c.customer_id=f.customer_id
           LEFT JOIN dim_products p ON p.product_sku=f.product_sku
           WHERE c.customer_id IS NULL OR p.product_sku IS NULL"""
    ).fetchone()[0]
    if bad_amounts or broken_keys:
        raise RuntimeError(f"Data quality failed: amounts={bad_amounts}, broken_keys={broken_keys}")
    rows, cents = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(revenue_cents), 0) FROM fact_orders"
    ).fetchone()
    return rows, cents


def run_etl(input_path: str | Path, db_path: str | Path, rejects_path: str | Path) -> ETLReport:
    """Validate CSV, upsert valid orders atomically, and audit invalid rows."""
    source, database, rejected_file = map(Path, (input_path, db_path, rejects_path))

    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = set(COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError("Missing CSV columns: " + ", ".join(sorted(missing)))
        rows = list(reader)

    database.parent.mkdir(parents=True, exist_ok=True)
    rejected_file.parent.mkdir(parents=True, exist_ok=True)
    rejected_rows: list[dict] = []
    seen: set[str] = set()
    loaded = 0

    with sqlite3.connect(database) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        with conn:
            for row_number, row in enumerate(rows, start=2):
                try:
                    if None in row:
                        raise ValueError("CSV row has more values than the header")
                    order = validate_order(row)
                    if order["order_id"] in seen:
                        raise ValueError("order_id: duplicate within input file")
                    seen.add(order["order_id"])
                except ValueError as exc:
                    rejected_rows.append({
                        "row_number": row_number,
                        "error": str(exc),
                        **{key: row.get(key, "") for key in COLUMNS},
                    })
                    continue
                _upsert_order(conn, order)
                loaded += 1
            count, revenue = _quality_metrics(conn)

    with rejected_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["row_number", "error", *COLUMNS])
        writer.writeheader()
        writer.writerows(rejected_rows)

    return ETLReport(
        extracted=len(rows), loaded=loaded, rejected=len(rejected_rows),
        warehouse_rows=count, revenue_cents=revenue,
    )
