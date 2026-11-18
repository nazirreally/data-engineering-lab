PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dim_customers (
    customer_id TEXT PRIMARY KEY,
    region TEXT NOT NULL CHECK(length(trim(region)) > 0)
);

CREATE TABLE IF NOT EXISTS dim_products (
    product_sku TEXT PRIMARY KEY,
    product_name TEXT NOT NULL CHECK(length(trim(product_name)) > 0)
);

CREATE TABLE IF NOT EXISTS fact_orders (
    order_id TEXT PRIMARY KEY,
    order_date TEXT NOT NULL,
    customer_id TEXT NOT NULL REFERENCES dim_customers(customer_id),
    product_sku TEXT NOT NULL REFERENCES dim_products(product_sku),
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents >= 0),
    revenue_cents INTEGER NOT NULL CHECK(revenue_cents = quantity * unit_price_cents)
);

CREATE INDEX IF NOT EXISTS idx_fact_orders_date ON fact_orders(order_date);
CREATE INDEX IF NOT EXISTS idx_fact_orders_customer ON fact_orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_fact_orders_product ON fact_orders(product_sku);
