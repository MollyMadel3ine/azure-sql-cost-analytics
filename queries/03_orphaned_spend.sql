-- ----------------------------------------------------------------------
-- 03_orphaned_spend.sql
-- Question: Which resources have cost history but haven't been
--           seen in the most recent inventory?
-- Grain: one row per no-longer-current resource
-- ----------------------------------------------------------------------
SELECT
    r.resource_name,
    r.resource_group,
    r.resource_type,
    r.last_seen,
    SUM(ce.daily_cost) AS lifetime_cost,
    MAX(ce.cost_date) AS last_charge
FROM
    resources r
    JOIN cost_entries ce ON ce.resource_key = r.resource_key
WHERE
    r.last_seen < (
        SELECT
            MAX(last_seen)
        FROM
            resources
    )
GROUP BY
    r.resource_name,
    r.resource_group,
    r.resource_type,
    r.last_seen
ORDER BY
    lifetime_cost DESC;