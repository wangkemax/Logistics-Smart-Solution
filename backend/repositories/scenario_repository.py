"""
Scenario Repository
=================
Data access layer for automation_scenarios table.

Responsibilities:
  - Read active scenarios from DB (with fallback to hardcoded defaults)
  - Seed initial data
  - Industry + area + SKU + order_volume filtering

Called by:
  - automation_engine.load_scenarios() — replaces hardcoded fallback
  - Future: admin UI, scenario management endpoints
"""

import sys
import sqlite3
from pathlib import Path
from typing import Optional
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "logistics_presale.db"


# =============================================================================
# Hardcoded fallback scenarios — exactly the same as automation_engine defaults
# =============================================================================

DEFAULT_SCENARIOS = [
    {
        "scenario_id": 1,
        "scenario_name": "AMR拣选辅助",
        "category": "移动机器人",
        "applicable_industry": "FMCG/GENERIC_3PL",
        "sku_min": 5000, "sku_max": 100000,
        "order_min": 500, "order_max": 50000,
        "capex_min": 500000, "capex_max": 2000000,
        "opex_year": 80000,
        "labor_saving": 0.3,
        "efficiency_gain": 0.4,
        "risk_level": "中",
        "region": "华东",
        "notes": "AMR机器人辅助人工作业，适合电商中小件拣选",
        "priority": 10,
    },
    {
        "scenario_id": 2,
        "scenario_name": "GTP货到人系统",
        "category": "货到人",
        "applicable_industry": "FMCG/GENERIC_3PL",
        "sku_min": 10000, "sku_max": 200000,
        "order_min": 1000, "order_max": 100000,
        "capex_min": 2000000, "capex_max": 8000000,
        "opex_year": 300000,
        "labor_saving": 0.5,
        "efficiency_gain": 0.6,
        "risk_level": "高",
        "region": "华东",
        "notes": "穿梭车货到人方案，适合高SKU场景",
        "priority": 8,
    },
    {
        "scenario_id": 3,
        "scenario_name": "输送分拣线",
        "category": "输送分拣",
        "applicable_industry": "FMCG/GENERIC_3PL",
        "sku_min": 1000, "sku_max": 50000,
        "order_min": 2000, "order_max": 200000,
        "capex_min": 1000000, "capex_max": 5000000,
        "opex_year": 150000,
        "labor_saving": 0.4,
        "efficiency_gain": 0.5,
        "risk_level": "中",
        "region": "华东",
        "notes": "高速输送分拣线，适合快递电商",
        "priority": 9,
    },
    {
        "scenario_id": 4,
        "scenario_name": "AS/RS立体仓库",
        "category": "立体仓库",
        "applicable_industry": "MANUFACTURING/GENERIC_3PL",
        "sku_min": 5000, "sku_max": 50000,
        "order_min": 500, "order_max": 20000,
        "capex_min": 3000000, "capex_max": 15000000,
        "opex_year": 400000,
        "labor_saving": 0.6,
        "efficiency_gain": 0.7,
        "risk_level": "高",
        "region": "华东",
        "notes": "全自动化立体仓库，适合大面积高 SKU 场景",
        "priority": 7,
    },
    {
        "scenario_id": 5,
        "scenario_name": "WCS软件系统",
        "category": "软件系统",
        "applicable_industry": "MANUFACTURING/FMCG/GENERIC_3PL",
        "sku_min": 1000, "sku_max": 200000,
        "order_min": 200, "order_max": 100000,
        "capex_min": 200000, "capex_max": 800000,
        "opex_year": 50000,
        "labor_saving": 0.15,
        "efficiency_gain": 0.25,
        "risk_level": "低",
        "region": "全国",
        "notes": "仓库控制系统集成，适合轻量化改造",
        "priority": 6,
    },
    {
        "scenario_id": 6,
        "scenario_name": "自动贴标打包线",
        "category": "自动化辅助",
        "applicable_industry": "FMCG/GENERIC_3PL",
        "sku_min": 2000, "sku_max": 100000,
        "order_min": 1000, "order_max": 50000,
        "capex_min": 300000, "capex_max": 1200000,
        "opex_year": 60000,
        "labor_saving": 0.35,
        "efficiency_gain": 0.4,
        "risk_level": "低",
        "region": "华东",
        "notes": "自动贴标+打包，适合标准化品类",
        "priority": 8,
    },
    {
        "scenario_id": 7,
        "scenario_name": "智能分拣机器人",
        "category": "移动机器人",
        "applicable_industry": "GENERIC_3PL",
        "sku_min": 1000, "sku_max": 30000,
        "order_min": 5000, "order_max": 100000,
        "capex_min": 1500000, "capex_max": 6000000,
        "opex_year": 200000,
        "labor_saving": 0.55,
        "efficiency_gain": 0.65,
        "risk_level": "中",
        "region": "华东",
        "notes": "分拣机器人，适合快递网点自动化",
        "priority": 9,
    },
    {
        "scenario_id": 8,
        "scenario_name": "料箱穿梭车系统",
        "category": "货到人",
        "applicable_industry": "GENERIC_3PL",
        "sku_min": 3000, "sku_max": 80000,
        "order_min": 500, "order_max": 30000,
        "capex_min": 1800000, "capex_max": 7000000,
        "opex_year": 220000,
        "labor_saving": 0.5,
        "efficiency_gain": 0.55,
        "risk_level": "中",
        "region": "华东",
        "notes": "多穿车方案，适合医药和小件电商",
        "priority": 7,
    },

    # --- AUTOMOTIVE scenarios (v0.8) ---
    {
        "scenario_code": "AUTO-01",
        "scenario_name": "AMR料架配送机器人（汽车产线JIT）",
        "category": "自动化设备",
        "applicable_industry": "AUTOMOTIVE",
        "min_area": 5000,
        "max_area": 50000,
        "sku_min": 1000,
        "sku_max": 20000,
        "order_min": 1000,
        "order_max": 20000,
        "capital_cost_per_sqm": 2500,
        "annual_maintenance_pct": 0.08,
        "annual_savings_per_sqm": 120,
        "labor_reduction_ratio": 0.45,
        "deployment_months": 9,
        "compatible_regions": ["华东", "华南", "华北"],
        "region": "华东",
        "notes": "JIT供料专用AMR，线边配送，适合汽车零部件和主机厂产线配套",
        "priority": 5,
        "is_active": True,
    },
    {
        "scenario_code": "AUTO-02",
        "scenario_name": "产线边物流系统（产线叫料+器具管理）",
        "category": "系统集成",
        "applicable_industry": "AUTOMOTIVE",
        "min_area": 3000,
        "max_area": 30000,
        "sku_min": 500,
        "sku_max": 10000,
        "order_min": 500,
        "order_max": 10000,
        "capital_cost_per_sqm": 2000,
        "annual_maintenance_pct": 0.07,
        "annual_savings_per_sqm": 90,
        "labor_reduction_ratio": 0.38,
        "deployment_months": 12,
        "compatible_regions": ["华东", "华南", "华北"],
        "region": "华东",
        "notes": "产线边叫料系统+JIS排序+器具周转管理，适合汽车零部件",
        "priority": 4,
        "is_active": True,
    },
]


# =============================================================================
# Database table creation (idempotent)
# =============================================================================

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS automation_scenarios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_code   TEXT    UNIQUE NOT NULL,
    scenario_name   TEXT    NOT NULL,
    category        TEXT    NOT NULL DEFAULT '',
    applicable_industry TEXT NOT NULL DEFAULT '',
    min_area        REAL    DEFAULT 0,
    max_area        REAL    DEFAULT 999999,
    sku_min         INTEGER DEFAULT 0,
    sku_max         INTEGER DEFAULT 999999999,
    order_min       INTEGER DEFAULT 0,
    order_max       INTEGER DEFAULT 999999999,
    capex_min       REAL    DEFAULT 0,
    capex_max       REAL    DEFAULT 999999999,
    opex_year       REAL    DEFAULT 0,
    labor_saving    REAL    DEFAULT 0,
    efficiency_gain REAL    DEFAULT 0,
    risk_level      TEXT    DEFAULT '中',
    region          TEXT    DEFAULT '华东',
    notes           TEXT    DEFAULT '',
    priority        INTEGER DEFAULT 5,
    is_active       INTEGER DEFAULT 1,
    weight_industry REAL    DEFAULT 0.20,
    weight_area     REAL    DEFAULT 0.15,
    weight_sku      REAL    DEFAULT 0.20,
    weight_orders   REAL    DEFAULT 0.20,
    weight_budget   REAL    DEFAULT 0.15,
    weight_region   REAL    DEFAULT 0.10,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def _get_conn() -> sqlite3.Connection:
    """Get a SQLite connection with row factory."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table():
    """Create the table if it doesn't exist (idempotent)."""
    conn = _get_conn()
    try:
        conn.executescript(CREATE_TABLE_SQL)
        conn.commit()
    finally:
        conn.close()


# =============================================================================
# Data access functions
# =============================================================================

def get_active_scenarios() -> list[dict]:
    """
    Fetch all active scenarios from DB.
    Falls back to hardcoded defaults if DB is empty or unavailable.
    """
    try:
        _ensure_table()
        conn = _get_conn()
        try:
            cursor = conn.execute(
                "SELECT * FROM automation_scenarios WHERE is_active = 1 ORDER BY priority DESC, id ASC"
            )
            rows = cursor.fetchall()
            if not rows:
                print(
                    "[scenario_repository] DB empty — falling back to hardcoded scenarios",
                    file=sys.stderr,
                )
                return [s.copy() for s in DEFAULT_SCENARIOS]

            scenarios = []
            for row in rows:
                scenarios.append({
                    "scenario_id": row["id"],
                    "scenario_name": row["scenario_name"],
                    "category": row["category"] or "",
                    "applicable_industry": row["applicable_industry"] or "",
                    "sku_min": row["sku_min"] or 0,
                    "sku_max": row["sku_max"] or 999999999,
                    "order_min": row["order_min"] or 0,
                    "order_max": row["order_max"] or 999999999,
                    "capex_min": row["capex_min"] or 0,
                    "capex_max": row["capex_max"] or 999999999,
                    "opex_year": row["opex_year"] or 0,
                    "labor_saving": row["labor_saving"] or 0,
                    "efficiency_gain": row["efficiency_gain"] or 0,
                    "risk_level": row["risk_level"] or "中",
                    "region": row["region"] or "华东",
                    "notes": row["notes"] or "",
                    "priority": row["priority"] or 5,
                    # Weight columns — defaults match CREATE TABLE defaults
                    "weight_industry": row["weight_industry"] if row["weight_industry"] is not None else 0.20,
                    "weight_area": row["weight_area"] if row["weight_area"] is not None else 0.15,
                    "weight_sku": row["weight_sku"] if row["weight_sku"] is not None else 0.20,
                    "weight_orders": row["weight_orders"] if row["weight_orders"] is not None else 0.20,
                    "weight_budget": row["weight_budget"] if row["weight_budget"] is not None else 0.15,
                    "weight_region": row["weight_region"] if row["weight_region"] is not None else 0.10,
                })
            return scenarios
        finally:
            conn.close()
    except Exception as e:
        print(
            f"[scenario_repository] DB error: {e} — falling back to hardcoded",
            file=sys.stderr,
        )
        return [s.copy() for s in DEFAULT_SCENARIOS]


def get_candidate_scenarios(
    industry: Optional[str] = None,
    min_area: Optional[float] = None,
    max_area: Optional[float] = None,
    min_sku: Optional[int] = None,
    max_sku: Optional[int] = None,
) -> list[dict]:
    """
    Fetch active scenarios with optional filtering.
    Returns all active scenarios if no filters given.
    """
    scenarios = get_active_scenarios()

    filtered = []
    for s in scenarios:
        # Industry filter (supports "/" separated multi-value)
        if industry:
            applicable = [a.strip() for a in s.get("applicable_industry", "").split("/")]
            if industry not in applicable and "general" not in applicable:
                # Also check via GENERAL fallback
                continue

        # Area filter
        if min_area is not None or max_area is not None:
            area_min = s.get("min_area", 0) or 0
            area_max = s.get("max_area", 999999) or 999999
            if max_area is not None and area_min > max_area:
                continue
            if min_area is not None and area_max < min_area:
                continue

        # SKU filter
        if min_sku is not None or max_sku is not None:
            sku_min = s.get("sku_min", 0) or 0
            sku_max = s.get("sku_max", 999999999) or 999999999
            if max_sku is not None and sku_min > max_sku:
                continue
            if min_sku is not None and sku_max < min_sku:
                continue

        filtered.append(s)

    return filtered


# =============================================================================
# Seed / initialization
# =============================================================================

def seed_default_scenarios() -> int:
    """
    Seed the database with default scenarios if table is empty.
    Returns number of rows inserted.
    """
    _ensure_table()
    conn = _get_conn()
    try:
        # Check if already seeded
        count = conn.execute("SELECT COUNT(*) FROM automation_scenarios").fetchone()[0]
        if count > 0:
            # Migrate: add missing columns for AUTO-01/AUTO-02 scenarios
            cols = [r[1] for r in conn.execute("PRAGMA table_info(automation_scenarios)").fetchall()]
            for col_sql in [
                "ALTER TABLE automation_scenarios ADD COLUMN scenario_code TEXT",
                "ALTER TABLE automation_scenarios ADD COLUMN capital_cost_per_sqm REAL",
                "ALTER TABLE automation_scenarios ADD COLUMN annual_maintenance_pct REAL",
                "ALTER TABLE automation_scenarios ADD COLUMN annual_savings_per_sqm REAL",
                "ALTER TABLE automation_scenarios ADD COLUMN labor_reduction_ratio REAL",
                "ALTER TABLE automation_scenarios ADD COLUMN deployment_months INTEGER",
                "ALTER TABLE automation_scenarios ADD COLUMN compatible_regions TEXT",
            ]:
                col_name = col_sql.split("ADD COLUMN ")[1].split(" ")[0]
                if col_name not in cols:
                    try:
                        conn.execute(col_sql)
                    except Exception:
                        pass
            conn.execute("DELETE FROM automation_scenarios")

        for s in DEFAULT_SCENARIOS:
            import json as _json
            conn.execute("""
                INSERT INTO automation_scenarios (
                    scenario_code, scenario_name, category, applicable_industry,
                    min_area, max_area, sku_min, sku_max,
                    order_min, order_max, capex_min, capex_max,
                    opex_year, labor_saving, efficiency_gain,
                    risk_level, region, notes, priority,
                    weight_industry, weight_area, weight_sku,
                    weight_orders, weight_budget, weight_region,
                    capital_cost_per_sqm, annual_maintenance_pct,
                    annual_savings_per_sqm, labor_reduction_ratio,
                    deployment_months, compatible_regions,
                    is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                s.get("scenario_code") or f"SCN{s.get('scenario_id', 99):02d}",
                s["scenario_name"],
                s["category"],
                s.get("applicable_industry") or "",
                s.get("min_area") or 0,
                s.get("max_area") or 999999,
                s.get("sku_min") or 0, s.get("sku_max") or 999999999,
                s.get("order_min") or 0, s.get("order_max") or 999999999,
                s.get("capex_min") or 0, s.get("capex_max") or 999999999,
                s.get("opex_year") or s.get("annual_savings_per_sqm", 0) * s.get("min_area", 10000) * 0.1 or 0,
                s.get("labor_saving") or s.get("labor_reduction_ratio", 0),
                s.get("efficiency_gain") or 0,
                s.get("risk_level") or "中",
                s.get("region") or "华东",
                s.get("notes") or "",
                s.get("priority") or 5,
                0.20, 0.15, 0.20, 0.20, 0.15, 0.10,
                s.get("capital_cost_per_sqm"),
                s.get("annual_maintenance_pct"),
                s.get("annual_savings_per_sqm"),
                s.get("labor_reduction_ratio"),
                s.get("deployment_months"),
                _json.dumps(s.get("compatible_regions")) if s.get("compatible_regions") else None,
                s.get("is_active", True),
            ))
        conn.commit()
        return len(DEFAULT_SCENARIOS)
    finally:
        conn.close()
