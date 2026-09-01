-- ------------------------------------------------------------
-- 01_cost_by_resource_group.sql
-- Question: Where does the money go, by resource group?
-- Grain: one row per resource group, totaled across all dates
-- ------------------------------------------------------------
SELECT
    r.resource_group,
    SUM(ce.daily_cost) AS total_cost,
    COUNT(DISTINCT r.resource_key) AS resource_count,
    MIN(ce.cost_date) AS first_charge,
    MAX(ce.cost_date) AS last_charge
FROM
    resources r
    JOIN cost_entries ce ON ce.resource_key = r.resource_key
GROUP BY
    r.resource_group
ORDER BY
    total_cost DESC;