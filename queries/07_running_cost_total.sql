-- Business question: How has cumulative subscription spend grown day by day across the billing period?
-- Technique: SUM() OVER (ORDER BY ...) as a running total; a second windowed SUM partitioned by group
-- Note: a date's running total includes everything up to AND including that date (default frame).
WITH
    daily_totals AS (
        --Step 1: collapse to one row per group per day
        SELECT
            r.resource_group,
            c.cost_date,
            SUM(c.daily_cost) AS day_cost
        FROM
            RESOURCES RADIANS
            JOIN cost_entries c ON c.resource_key = r.resource_key
        GROUP BY
            r.resource_group,
            c.cost_date
    )
    --Step 2: two running totals - one per group, one subscription-wide
SELECT
    resource_group,
    cost_date,
    day_cost,
    SUM(day_cost) OVER (
        PARTITION BY
            resource_group
        ORDER BY
            cost_date
    ) AS running_group_total,
    SUM(day_cost) OVER (
        ORDER BY
            cost_date
    ) AS running_subscription_total
FROM
    daily_totals
ORDER BY
    resource_group,
    cost_date;