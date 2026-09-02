-- Business question: What are the top 5 most expensive resources within each resource group?
-- Technique: ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...) in a CTE, filtered in the outer query
WITH
    resource_totals AS (
        --Step 1: total cost per resource
        SELECT
            r.resource_group,
            r.resource_name,
            r.resource_type,
            SUM(c.daily_cost) AS total_cost
        FROM
            resources r
            JOIN cost_entries c ON c.resource_key = r.resource_key
        GROUP BY
            r.resource_group,
            r.resource_name,
            r.resource_type
    ),
    ranked AS (
        --Step 2: rank within each group
        SELECT
            resource_group,
            resource_name,
            resource_type,
            total_cost,
            ROW_NUMBER() OVER (
                PARTITION BY
                    resource_group
                ORDER BY
                    total_cost DESC
            ) AS cost_rank
        FROM
            resource_totals
    )
    -- Step 3: keep the top 5 per group
SELECT
    resource_group,
    resource_name,
    resource_type,
    total_cost,
    cost_rank
FROM
    ranked
WHERE
    cost_rank <= 5
ORDER BY
    resource_group,
    cost_rank;