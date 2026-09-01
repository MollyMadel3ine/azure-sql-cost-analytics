-- ============================================================
-- 01_schema.sql — Azure SQL Cost & Resource Analytics
-- Four-table normalized design (3NF). Run in dependency order:
-- tables with foreign keys need their referenced table first.
-- ============================================================
-- One row per Azure resource being tracked
CREATE TABLE
   subscriptions (
      subscription_id UNIQUEIDENTIFIER PRIMARY KEY,
      subscription_name NVARCHAR (100) NOT NULL
   );

-- One row per Azure resource, past or present
-- first seen/last seen let a deleted resource keep its row
-- (last seen in the past) - this is what makes the Phase 2
-- orphaned-spend query possible. Maintained my the load script.
CREATE TABLE
   resources (
      resource_key INT IDENTITY (1, 1) PRIMARY KEY, --surrogate: the key the other tables refernce
      resource_id NVARCHAR (400) NOT NULL UNIQUE, --the natural ARM ID, still enforced unique
      subscription_id UNIQUEIDENTIFIER NOT NULL REFERENCES subscriptions (subscription_id),
      resource_name NVARCHAR (200) NOT NULL,
      resource_group NVARCHAR (100) NOT NULL,
      resource_type NVARCHAR (150) NOT NULL,
      location NVARCHAR (50) NOT NULL,
      first_seen DATE NOT NULL,
      last_seen DATE NOT NULL
   );

-- One row per tag per resource (one-to-many).
-- Tags are rows, not columns, so adding a new tag key never
-- requires ALTER TABLE. Composite PK: a tag KEY appears at most
-- once per resource — the value depends on the whole key
-- (resource + key), which is the 2NF design.
CREATE TABLE
   resource_tags (
      resource_key INT NOT NULL REFERENCES resources (resource_key),
      tag_key NVARCHAR (100) NOT NULL,
      tag_value NVARCHAR (200) NOT NULL,
      PRIMARY KEY (resource_key, tag_key)
   );

-- One row per resource per day of cost.
-- Composite PK: neither column alone identifies a row — only
-- the pair (this resource on this date) does. daily_cost is
-- DECIMAL, never FLOAT: costs get SUMmed constantly in Phase 2,
-- and FLOAT accumulates rounding drift.
CREATE TABLE
   cost_entries (
      resource_key INT NOT NULL REFERENCES resources (resource_key),
      cost_date DATE NOT NULL,
      daily_cost DECIMAL(14, 8) NOT NULL,
      currency CHAR(3) NOT NULL DEFAULT 'USD',
      PRIMARY KEY (resource_key, cost_date)
   );