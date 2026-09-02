-- Business question: Which resources have dropped out of the inventory, and what did they cost over their lifetime?
-- Technique: layered CTEs replacing a scalar subquery — each step named, read top-to-bottom.
-- Refactored from the original subquery version; results are identical.
WITH
    latest_inventory AS (
        -- Step 1: when did the most recent inventory load happen?
        SELECT
            MAX(last_seen) AS latest_seen
        FROM
            resources
    ),
    stale_resources AS (
        -- Step 2: resources absent from that latest load
        SELECT
            r.resource_key,
            r.resource_name,
            r.resource_group,
            r.resource_type,
            r.last_seen
        FROM
            resources r
            CROSS JOIN latest_inventory li
        WHERE
            r.last_seen < li.latest_seen
    )
    -- Step 3: attach lifetime cost to each stale resource
SELECT
    s.resource_name,
    s.resource_group,
    s.resource_type,
    s.last_seen,
    SUM(ce.daily_cost) AS lifetime_cost,
    MAX(ce.cost_date) AS last_charge
FROM
    stale_resources s
    JOIN cost_entries ce ON ce.resource_key = s.resource_key
GROUP BY
    s.resource_name,
    s.resource_group,
    s.resource_type,
    s.last_seen
ORDER BY
    lifetime_cost DESC;