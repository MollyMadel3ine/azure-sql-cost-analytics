"""
load_data.py — loads Azure inventory and cost exports into the analytics database.

Inputs (local only, never committed):
    data/inventory.json   — output of: az resource list --output json
    data/cost-export.csv  — Cost Management daily-granularity CSV, grouped by resource

Connection:
    Reads the full connection string from the SQL_CONN_STR environment variable.
    Never hardcode credentials in this file.

Idempotency:
    Safe to re-run. Resources match on ARM ID; tags are delete-and-reloaded per
    resource; cost entries upsert on (resource_key, cost_date).

Operational notes:
    - Handles serverless auto-pause (SQL error 40613) with bounded retry.
    - Cost rows join to resources via lowercase-normalized ARM IDs — cost
      exports lowercase the ID, 'az resource list' preserves original casing.
    - Cost CSV may arrive at per-meter grain (multiple rows per resource per
      day); rows are summed to (resource, date) grain before loading.
"""

import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime

import pyodbc

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

INVENTORY_PATH = "data/inventory.json"
COST_CSV_PATH = "data/cost-export.csv"

# The date this export represents. For a monthly ritual, running the script
# on export day makes today's date correct. If loading an older export,
# change this to the date the export was taken.
EXPORT_DATE = date.today()


def get_connection() -> pyodbc.Connection:
    """Connect using the connection string in the SQL_CONN_STR env var.

    Retries on SQL error 40613 only — the transient 'database resuming from
    auto-pause' state. Any other error (credentials, firewall) raises
    immediately, because time won't fix those.
    """
    conn_str = os.environ.get("SQL_CONN_STR")
    if not conn_str:
        sys.exit(
            "SQL_CONN_STR is not set. Set it in this shell first, e.g.\n"
            '  $env:SQL_CONN_STR = "Driver={ODBC Driver 18 for SQL Server};'
            'Server=tcp:<server-fqdn>,1433;Database=sqldb-cost-analytics;'
            'Uid=<user>;Pwd=<password>;Encrypt=yes;Connection Timeout=90"'
        )
    """Retry the connection while the serverless database resumes from auto-pause"""
    attempts = 5
    for attempt in range(1, attempts + 1):
        try:
            return pyodbc.connect(conn_str, timeout=90)
        except pyodbc.Error as e:
            if "40613" in str(e) and attempt < attempts:
                print(
                    f"  database resuming from auto-pause "
                    f"(attempt {attempt}/{attempts}) — waiting 20s..."
                )
                time.sleep(20)
            else:
                raise


# ---------------------------------------------------------------------------
# Step 2 — subscription upsert
# ---------------------------------------------------------------------------

def upsert_subscription(cursor: pyodbc.Cursor, sub_id: str, sub_name: str) -> None:
    """Insert the subscription row if new; update the name if it changed."""
    cursor.execute(
        "SELECT subscription_name FROM subscriptions WHERE subscription_id = ?",
        sub_id,
    )
    row = cursor.fetchone()

    if row is None:
        cursor.execute(
            "INSERT INTO subscriptions (subscription_id, subscription_name) "
            "VALUES (?, ?)",
            sub_id,
            sub_name,
        )
        print(f"  subscription inserted: {sub_name}")
    elif row.subscription_name != sub_name:
        cursor.execute(
            "UPDATE subscriptions SET subscription_name = ? "
            "WHERE subscription_id = ?",
            sub_name,
            sub_id,
        )
        print(f"  subscription name updated: {sub_name}")
    else:
        print(f"  subscription unchanged: {sub_name}")


# ---------------------------------------------------------------------------
# Steps 3 & 4 — resources upsert, capturing resource_key
# ---------------------------------------------------------------------------

def upsert_resource(cursor: pyodbc.Cursor, item: dict, sub_id: str) -> int:
    """Insert or update one resource; return its integer resource_key.

    The returned key is what the child tables (resource_tags, cost_entries)
    reference — the surrogate-key lookup this schema requires.
    """
    arm_id = item["id"]

    cursor.execute(
        "SELECT resource_key FROM resources WHERE resource_id = ?",
        arm_id,
    )
    row = cursor.fetchone()

    if row is None:
        cursor.execute(
            "INSERT INTO resources "
            "(resource_id, subscription_id, resource_name, resource_group, "
            " resource_type, location, first_seen, last_seen) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            arm_id,
            sub_id,
            item["name"],
            item["resourceGroup"],
            item["type"],
            item["location"],
            EXPORT_DATE,
            EXPORT_DATE,
        )
        # Explicit re-select rather than SCOPE_IDENTITY(): one extra query,
        # but unambiguous — resource_id is UNIQUE, so this is exact.
        cursor.execute(
            "SELECT resource_key FROM resources WHERE resource_id = ?",
            arm_id,
        )
        return cursor.fetchone().resource_key

    # Existing resource: refresh last_seen and the attributes that can change.
    cursor.execute(
        "UPDATE resources "
        "SET last_seen = ?, resource_name = ?, resource_group = ?, location = ? "
        "WHERE resource_key = ?",
        EXPORT_DATE,
        item["name"],
        item["resourceGroup"],
        item["location"],
        row.resource_key,
    )
    return row.resource_key


# ---------------------------------------------------------------------------
# Step 5 — tags: delete-and-reload unpivot
# ---------------------------------------------------------------------------

def load_tags(cursor: pyodbc.Cursor, resource_key: int, tags: dict | None) -> None:
    """Replace this resource's tag rows with the current tags object.

    Delete-and-reload is the simple idempotent form for a small child table:
    tags removed in Azure disappear here too, renames land cleanly, and
    re-runs converge to the same state.
    """
    cursor.execute(
        "DELETE FROM resource_tags WHERE resource_key = ?",
        resource_key,
    )
    if not tags:
        return
    for tag_key, tag_value in tags.items():
        cursor.execute(
            "INSERT INTO resource_tags (resource_key, tag_key, tag_value) "
            "VALUES (?, ?, ?)",
            resource_key,
            tag_key,
            tag_value if tag_value is not None else "",
        )


# ---------------------------------------------------------------------------
# Step 6 — cost entries
# ---------------------------------------------------------------------------

def parse_usage_date(raw: str) -> date:
    """Parse the UsageDate column across the formats cost exports use."""
    raw = raw.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized UsageDate format: {raw!r}")


def load_costs(cursor: pyodbc.Cursor) -> None:
    """Load data/cost-export.csv into cost_entries.

    Three defenses, in order:
    1. Case-insensitive header lookup — export header casing varies.
    2. Lowercase-normalized ARM ID join — cost exports lowercase the ID,
       the inventory preserves original casing.
    3. Pre-aggregation to (resource_key, cost_date) — the CSV may be at
       per-meter grain, and the table's PK allows one row per resource
       per day.
    """
    # Lookup dict: lowercased ARM ID -> resource_key (defense 2).
    cursor.execute("SELECT resource_id, resource_key FROM resources")
    key_by_arm_id = {row.resource_id.lower(): row.resource_key for row in cursor}

    with open(COST_CSV_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        # Case-insensitive header map (defense 1): 'ResourceId', 'resourceID',
        # etc. all resolve to the actual header string in this file.
        headers = {h.lower().strip(): h for h in reader.fieldnames}
        try:
            col_id = headers["resourceid"]
            col_date = headers["usagedate"]
            col_cost = headers["costusd"]
        except KeyError as missing:
            sys.exit(
                f"Expected column {missing} not found in {COST_CSV_PATH}. "
                f"Headers present: {reader.fieldnames}"
            )

        # Aggregate to (resource_key, cost_date) grain (defense 3).
        totals: dict[tuple[int, date], float] = defaultdict(float)
        unmatched_ids: set[str] = set()
        for row in reader:
            arm_id = (row[col_id] or "").strip().lower()
            if not arm_id:
                # Subscription-level lines (taxes, purchases) have no
                # resource — outside this table's grain, skipped by design.
                continue
            resource_key = key_by_arm_id.get(arm_id)
            if resource_key is None:
                # Cost history for resources deleted before the inventory
                # export — expected with destroy-and-rebuild repos.
                unmatched_ids.add(arm_id)
                continue
            totals[(resource_key, parse_usage_date(row[col_date]))] += float(
                row[col_cost]
            )

    # Upsert each aggregated total.
    inserted = updated = 0
    for (resource_key, cost_date), daily_cost in totals.items():
        cursor.execute(
            "SELECT daily_cost FROM cost_entries "
            "WHERE resource_key = ? AND cost_date = ?",
            resource_key,
            cost_date,
        )
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                "INSERT INTO cost_entries "
                "(resource_key, cost_date, daily_cost, currency) "
                "VALUES (?, ?, ?, 'USD')",
                resource_key,
                cost_date,
                round(daily_cost, 8),
            )
            inserted += 1
        else:
            cursor.execute(
                "UPDATE cost_entries SET daily_cost = ? "
                "WHERE resource_key = ? AND cost_date = ?",
                round(daily_cost, 8),
                resource_key,
                cost_date,
            )
            updated += 1

    print(
        f"  cost entries: {inserted} inserted, {updated} updated, "
        f"{len(unmatched_ids)} resource IDs unmatched (deleted resources)"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    with open(INVENTORY_PATH, encoding="utf-8") as f:
        inventory = json.load(f)
    print(f"Inventory: {len(inventory)} resources in {INVENTORY_PATH}")

    # Every ARM ID starts /subscriptions/<guid>/... — take the GUID from
    # the first resource rather than asking for it separately.
    sub_id = inventory[0]["id"].split("/")[2]
    sub_name = os.environ.get("SQL_SUB_NAME", "my-subscription")

    conn = get_connection()
    cursor = conn.cursor()

    print("Loading subscription...")
    upsert_subscription(cursor, sub_id, sub_name)

    print("Loading resources and tags...")
    count = 0
    for item in inventory:
        key = upsert_resource(cursor, item, sub_id)
        load_tags(cursor, key, item.get("tags"))
        count += 1
    print(f"  {count} resources upserted")

    print("Loading cost entries...")
    load_costs(cursor)

    conn.commit()
    conn.close()
    print("Done — committed.")


if __name__ == "__main__":
    main()
