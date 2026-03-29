#!/usr/bin/env python3
"""
Backfill migration: add all missing pipeline_runs columns.
Handles both v0.2 and v0.6.1 missing columns.
Safe to run multiple times (checks column existence).
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "../data/logistics_presale.db")

# All columns that should exist in pipeline_runs (from SQLAlchemy model)
ALL_COLUMNS = [
    ("analysis_markdown",            "TEXT"),
    ("analysis_sections_json",       "TEXT"),
    ("normalized_fields_json",       "TEXT"),
    ("missing_items_json",          "TEXT"),
    ("clarification_questions_json", "TEXT"),
    ("quality_score_json",           "TEXT"),
    ("readiness_json",              "TEXT"),
    ("analysis_version",             "TEXT DEFAULT 'v0.2'"),
    ("prompt_version",              "TEXT DEFAULT 'tender_understanding_v0.2'"),
    ("model_name",                  "TEXT"),
    ("pipeline_gate_json",           "TEXT"),
    # v0.6.1
    ("manual_inputs_json",          "TEXT"),
    ("resolved_fields_json",         "TEXT"),
    ("clarification_tasks_json",     "TEXT"),
]


def main():
    if not os.path.exists(DB_PATH):
        print(f"⚠️  Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(pipeline_runs)")
    existing = {row[1] for row in cur.fetchall()}

    added = []
    skipped = []
    for col_name, col_type in ALL_COLUMNS:
        if col_name in existing:
            skipped.append(col_name)
        else:
            try:
                cur.execute(f"ALTER TABLE pipeline_runs ADD COLUMN {col_name} {col_type}")
                conn.commit()
                added.append(col_name)
                print(f"✅ Added: {col_name}")
            except Exception as e:
                print(f"⚠️  Error adding {col_name}: {e}")

    conn.close()
    print(f"\nDone. Added {len(added)}, already existed {len(skipped)}.")


if __name__ == "__main__":
    main()
