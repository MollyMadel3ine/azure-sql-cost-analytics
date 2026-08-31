"""
load_data.py — loads Azure inventory and cost exports into the analytics database.

Inputs (local only, never committed):
    data/inventory.json   — output of: az resource list --output json
    data/cost-export.csv  — Cost Management daily-granularity, grouped-by-resource CSV

Connection:
    Reads the full connection string from the SQL_CONN_STR environment variable.
    Never hardcode credentials in this file.

Idempotency:
    Safe to re-run. Resources are matched on their ARM ID (resource_id):
    new IDs are inserted with first_seen = last_seen = the export date;
    existing IDs get last_seen (and mutable attributes) updated.
"""

import json
import time
import os
import sys
from datetime import date

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

    The long timeout is deliberate: the serverless database cold-starts in
    30-90 seconds when paused, and the first connection of a session must
    wait that out rather than fail.
    """
    conn_str = os.environ.get("SQL_CONN_STR")
    if not conn_str:
        sys.exit(
            "SQL_CONN_STR is not set. Set it in this shell first, e.g.\n"
            '  $env:SQL_CONN_STR = "Driver={ODBC Driver 18 for SQL Server};'
            'Server=tcp:<server-fqdn>,1433;Database=sqldb-cost-analytics;'
            'Uid=<user>;Pwd=<password>;Encrypt=yes;Connection Timeout=90"'
        )
    attempts = 5
    for attempt in range(1, attempts+1):
        try:
            return pyodbc.connect(conn_str, timeout=90)
        except pyodbc.Error as e:
            if "40613" in str(e) and attempt < attempts:
                print(
                    f"database resuming from auto-pause "
                    f"(attempt {attempt}/{attempts}) - waiting 20s..."
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
# Step 5 — tags (sitting two)
# ---------------------------------------------------------------------------

def load_tags(cursor: pyodbc.Cursor, resource_key: int, tags: dict | None) -> None:
    """TODO (sitting two): unpivot the tags object into resource_tags.

    Plan: DELETE existing rows for this resource_key, then INSERT one row
    per key/value pair — delete-and-reload is the simple idempotent form
    for a child table this small.
    """
    pass


# ---------------------------------------------------------------------------
# Step 6 — cost entries (sitting two)
# ---------------------------------------------------------------------------

def load_costs(cursor: pyodbc.Cursor) -> None:
    """TODO (sitting two): load data/cost-export.csv into cost_entries.

    Plan: build a {lowercased resource_id: resource_key} lookup dict from
    the resources table, then match each CSV row via lower(arm_id) —
    the case-normalization defense from the Session 5 design note.
    """
    pass


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

    print("Loading resources...")
    inserted = 0
    for item in inventory:
        key = upsert_resource(cursor, item, sub_id)
        load_tags(cursor, key, item.get("tags"))  # no-op until sitting two
        inserted += 1
    print(f"  {inserted} resources upserted")

    load_costs(cursor)  # no-op until sitting two

    conn.commit()
    conn.close()
    print("Done — committed.")


if __name__ == "__main__":
    main()
