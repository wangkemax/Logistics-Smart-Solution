"""Idempotent SQLite patches for databases created before the unified schema."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def _columns(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _add_column(conn, table: str, column: str, ddl: str) -> None:
    if column not in _columns(conn, table):
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def apply_migrations(engine: Engine) -> None:
    with engine.begin() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        if "assumptions" in tables:
            conn.execute(
                text(
                    """
                    DELETE FROM assumptions
                    WHERE id NOT IN (
                        SELECT MAX(id) FROM assumptions
                        GROUP BY run_id, field_key, version_id
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_assumption_run_field_version "
                    "ON assumptions(run_id, field_key, version_id)"
                )
            )
        if "financial_snapshots" in tables:
            _add_column(conn, "financial_snapshots", "npv", "npv REAL")
        if "equipment" in tables:
            conn.execute(
                text("UPDATE equipment SET version_id = 1 WHERE version_id IS NULL")
            )
        if "automation_scenarios" in tables:
            _migrate_scenario_columns(conn)


SCENARIO_COLUMNS = (
    ("scenario_code", "scenario_code TEXT"),
    ("min_area", "min_area REAL DEFAULT 0"),
    ("max_area", "max_area REAL DEFAULT 999999"),
    ("opex_year", "opex_year REAL DEFAULT 0"),
    ("region", "region TEXT DEFAULT '华东'"),
    ("notes", "notes TEXT DEFAULT ''"),
    ("priority", "priority INTEGER DEFAULT 5"),
    ("is_active", "is_active INTEGER DEFAULT 1"),
    ("weight_industry", "weight_industry REAL DEFAULT 0.20"),
    ("weight_area", "weight_area REAL DEFAULT 0.15"),
    ("weight_sku", "weight_sku REAL DEFAULT 0.20"),
    ("weight_orders", "weight_orders REAL DEFAULT 0.20"),
    ("weight_budget", "weight_budget REAL DEFAULT 0.15"),
    ("weight_region", "weight_region REAL DEFAULT 0.10"),
    ("capital_cost_per_sqm", "capital_cost_per_sqm REAL"),
    ("annual_maintenance_pct", "annual_maintenance_pct REAL"),
    ("annual_savings_per_sqm", "annual_savings_per_sqm REAL"),
    ("labor_reduction_ratio", "labor_reduction_ratio REAL"),
    ("deployment_months", "deployment_months INTEGER"),
    ("compatible_regions", "compatible_regions TEXT"),
    ("created_at", "created_at TIMESTAMP"),
    ("updated_at", "updated_at TIMESTAMP"),
)


def _migrate_scenario_columns(conn) -> None:
    for column, ddl in SCENARIO_COLUMNS:
        _add_column(conn, "automation_scenarios", column, ddl)
    conn.execute(text("UPDATE automation_scenarios SET is_active = 1 WHERE is_active IS NULL"))
    rows = conn.execute(
        text("SELECT id, scenario_id, scenario_code FROM automation_scenarios")
    ).fetchall()
    for row in rows:
        code = row[2]
        if code:
            continue
        number = row[1] if row[1] is not None else row[0]
        conn.execute(
            text("UPDATE automation_scenarios SET scenario_code = :code WHERE id = :id"),
            {"code": f"SCN{int(number):02d}", "id": row[0]},
        )


def migrate_scenarios_sqlite(conn) -> None:
    """Same column patch for a raw sqlite3 connection (repository startup)."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(automation_scenarios)")}
    for column, ddl in SCENARIO_COLUMNS:
        if column not in existing:
            conn.execute(f"ALTER TABLE automation_scenarios ADD COLUMN {ddl}")
    conn.execute("UPDATE automation_scenarios SET is_active = 1 WHERE is_active IS NULL")
    rows = conn.execute("SELECT id, scenario_id, scenario_code FROM automation_scenarios").fetchall()
    for row in rows:
        if row[2]:
            continue
        number = row[1] if row[1] is not None else row[0]
        conn.execute(
            "UPDATE automation_scenarios SET scenario_code = ? WHERE id = ?",
            (f"SCN{int(number):02d}", row[0]),
        )
