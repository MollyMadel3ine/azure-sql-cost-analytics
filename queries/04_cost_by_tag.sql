-- ------------------------------------------------------------
-- 04_cost_by_tag.sql
-- Question: Where does the money go, by project tag —
--           and how much spend is untagged?
-- Grain: one row per project value, plus one '(untagged)' row
-- ------------------------------------------------------------
SELECT
    COALESCE(rt.tag_value, '(untagged)') AS project,
    SUM(ce.daily_cost) AS total_cost,
    COUNT(DISTINCT r.resource_key) AS resource_count
FROM
    resources r
    JOIN cost_entries ce ON ce.resource_key = r.resource_key
    LEFT JOIN resource_tags rt ON rt.resource_key = r.resource_key
    AND rt.tag_key = 'project'
GROUP BY
    COALESCE(rt.tag_value, '(untagged)')
ORDER BY
    total_cost DESC;