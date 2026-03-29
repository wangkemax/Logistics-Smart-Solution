#!/usr/bin/env python3
"""
Migration script: v0.6.1 — Clarification Workflow
=================================================

Adds new columns to pipeline_runs table:
  - manual_inputs_json         TEXT
  - resolved_fields_json       TEXT
  - clarification_tasks_json   TEXT

Safe to run multiple times (checks for existing columns).
Uses sqlite3 directly — no SQLAlchemy dependency needed.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "../data/logistics_presale.db")

MIGRATION_COLUMNS = [
    ("manual_inputs_json", "TEXT"),
    ("resolved_fields_json", "TEXT"),
    ("clarification_tasks_json", "TEXT"),
]


def migrate():
    if not os.path.exists(DB_PATH):
        print(f"⚠️  Database not found at {DB_PATH}, skipping migration.")
        print("    Run `python scripts/init_db.py` first, then re-run this migration.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get existing columns
    cursor.execute("PRAGMA table_info(pipeline_runs)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    for col_name, col_type in MIGRATION_COLUMNS:
        if col_name in existing_cols:
            print(f"⏭️  Column already exists: {col_name} — skipping")
        else:
            try:
                cursor.execute(f"ALTER TABLE pipeline_runs ADD COLUMN {col_name} {col_type}")
                conn.commit()
                print(f"✅ Added column: {col_name} ({col_type})")
            except Exception as e:
                print(f"⚠️  Error adding {col_name}: {e}")

    conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    migrate()
