<div align="center">

# 🏗️ Data Engineering Lab

### Practical pipelines. Reliable data. Reproducible results.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![SQL](https://img.shields.io/badge/SQL-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
![Tests](https://img.shields.io/badge/Tests-unittest-2ea44f)
![License](https://img.shields.io/badge/License-MIT-blue)

**An evolving collection of hands-on Data Engineering projects by [Nazir Ali Khan](https://github.com/nazirreally).**

</div>

---

## 🚀 Project 01 — Retail Orders ETL

A small, working **batch ETL pipeline** using **Python + SQL + SQLite**, intentionally built without external runtime dependencies.

It takes a CSV of retail orders, validates each record, loads a relational analytics model, and exposes SQL reporting queries. Invalid rows are written to a separate rejection file rather than silently discarded.

### Architecture

```text
        Retail orders CSV
                │
                ▼
        Python extraction
                │
                ▼
  Schema + business validation ─────► Rejected rows CSV
                │
                ▼
   Idempotent dimension + fact loads
                │
                ▼
      SQLite analytics database
                │
                ▼
   SQL metrics / reporting queries
```

### What's engineered here?

| Capability | Implementation |
| --- | --- |
| Data ingestion | Standard-library `csv.DictReader` |
| Validation | Required fields, ISO dates, positive quantities, nonnegative prices, duplicate IDs |
| Currency correctness | `decimal.Decimal` → integer cents; no binary floating point math |
| Data modeling | `dim_customers`, `dim_products`, `fact_orders` with foreign keys |
| Incremental reruns | `ON CONFLICT ... DO UPDATE` to upsert existing orders |
| Data quality | Rejected-row audit file, referential integrity, revenue reconciliation |
| Analytics | SQL reporting queries |
| Testing | `unittest` tests, including idempotency and bad-data scenarios |
| CI | GitHub Actions runs tests on pushes and pull requests |

## ⚡ Quick start

Requires **Python 3.11+**. No `pip install` needed.

```bash
git clone https://github.com/nazirreally/data-engineering-lab.git
cd data-engineering-lab

# Run sample ETL
python -m pipeline.cli --input data/sample_orders.csv --db output/retail.db --rejects output/rejected_rows.csv

# Run automated tests
python -m unittest discover -s tests -v
```

Example console summary (numbers depend on the input):

```text
Extracted: ... | loaded: ... | rejected: ...
Total rows in warehouse: ... | total revenue: $...
```

Run the included analytical SQL using your preferred SQLite client:

```bash
sqlite3 -header -column output/retail.db < sql/analytics.sql
```

The `sqlite3` command-line tool is optional. Python itself is sufficient to run the pipeline.

## 📁 Repository structure

```text
data-engineering-lab/
├── pipeline/
│   ├── __init__.py
│   ├── cli.py             # CLI, validation, orchestration & quality checks
│   └── etl.py             # extract / transform / load logic
├── data/
│   └── sample_orders.csv  # synthetic example orders
├── sql/
│   ├── schema.sql         # analytics warehouse tables
│   └── analytics.sql      # ready-to-run business queries
├── tests/
│   └── test_etl.py        # automated tests
├── .github/workflows/
│   └── ci.yml             # GitHub Actions workflow
└── .gitignore
```

## 🔍 Engineering decisions

- **Re-runnable loads:** Stable natural keys and SQLite upserts prevent the same input from creating duplicate orders.
- **Explicit rejected records:** Bad data is visible with row numbers and error reasons.
- **Deterministic currency:** Prices are converted to integer cents after decimal validation.
- **Transactional writes:** A database transaction protects a batch from partial loads if a database error occurs.
- **Honest scope:** This is a local batch ETL proof of concept, not a production-scale streaming system.

### Next iterations

- [ ] Add structured logging and run-level audit metadata
- [ ] Introduce PostgreSQL + Docker Compose
- [ ] Add a scheduler / Airflow DAG
- [ ] Model transformations with dbt
- [ ] Add cloud storage and observability

---

<div align="center">

**Build it • Test it • Document it • Improve it**

Made for learning and portfolio demonstration by **Nazir Ali Khan**.

</div>


## Project 02 — HTTP Log Analytics & Monitoring Engine

A dependency-free Python/SQLite log ingestion, validation, and operational metrics project with idempotent loads, rejected-row auditing, p95 latency, and automated tests.

➡️ [See Project 02](projects/02-log-analytics/README.md)
