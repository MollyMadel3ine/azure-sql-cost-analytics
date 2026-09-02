-- Business question: How did each resource group's monthly cost change compared to the prior month?
-- Technique: LAG() OVER (PARTITION BY ... ORDER BY ...) against pre-aggregated monthly totals in a CTE
-- Note: the first month in each group has no prior month, so prior_month_cost and the deltas are NULL by design.
WITH
    monthly_totals AS (
        -- Step 1: collape daily cost rows to one row per group per month
        SELECT
            r.resource_group,
            DATEFROMPARTS (YEAR (c.cost_date), MONTH (c.cost_date), 1) AS cost_month,
            SUM(c.daily_cost) AS month_cost
        FROM
            resources r
            JOIN cost_entries c ON c.resource_key = r.resource_key
        GROUP BY
            r.resource_group,
            DATEFROMPARTS (YEAR (c.cost_date), MONTH (c.cost_date), 1)
    )
    --Step 2: each row peels one row back within its own group
SELECT
    resource_group,
    cost_month,
    month_cost,
    LAG (month_cost) OVER (
        PARTITION BY
            resource_group
        ORDER BY
            cost_month
    ) AS prior_month_cost,
    month_cost - LAG (month_cost) OVER (
        PARTITION BY
            resource_group
        ORDER BY
            cost_month
    ) AS change_from_prior
FROM
    monthly_totals
ORDER BY
    resource_group,
    cost_month;