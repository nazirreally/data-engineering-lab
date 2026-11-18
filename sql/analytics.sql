-- Query 1: Daily order counts and revenue (USD)
SELECT order_date,
       COUNT(*) AS orders,
       ROUND(SUM(revenue_cents) / 100.0, 2) AS revenue_usd
FROM fact_orders
GROUP BY order_date
ORDER BY order_date;

-- Query 2: Top products by sales revenue
SELECT p.product_name,
       SUM(f.quantity) AS units_sold,
       COUNT(*) AS orders,
       ROUND(SUM(f.revenue_cents) / 100.0, 2) AS revenue_usd
FROM fact_orders f
JOIN dim_products p ON f.product_sku = p.product_sku
GROUP BY p.product_sku, p.product_name
ORDER BY SUM(f.revenue_cents) DESC;

-- Query 3: Regional performance
SELECT c.region,
       COUNT(DISTINCT f.customer_id) AS active_customers,
       COUNT(*) AS orders,
       ROUND(SUM(f.revenue_cents) / 100.0, 2) AS revenue_usd
FROM fact_orders f
JOIN dim_customers c ON f.customer_id = c.customer_id
GROUP BY c.region
ORDER BY SUM(f.revenue_cents) DESC;

-- Query 4: Warehouse integrity check; all values should be zero
SELECT
  (SELECT COUNT(*) FROM fact_orders
   WHERE revenue_cents != quantity * unit_price_cents) AS invalid_amounts,
  (SELECT COUNT(*) FROM fact_orders f
   LEFT JOIN dim_customers c ON f.customer_id = c.customer_id
   WHERE c.customer_id IS NULL) AS missing_customers,
  (SELECT COUNT(*) FROM fact_orders f
   LEFT JOIN dim_products p ON f.product_sku = p.product_sku
   WHERE p.product_sku IS NULL) AS missing_products;
