-- ------------------------------------------------------------
-- 02_daily_trend.sql
-- Question: How does total spend move day by day?
-- Grain: one row per calendar date, across all resources
-- ------------------------------------------------------------
SELECT
    ce.cost_date,
    SUM(ce.daily_cost) AS total_cost,
    COUNT(DISTINCT ce.resource_key) AS resources_charged
FROM
    cost_entries ce
GROUP BY
    ce.cost_date
ORDER BY
    ce.cost_date;