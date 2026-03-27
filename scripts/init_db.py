#!/usr/bin/env python3
"""Initialize the database and seed initial data."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models.database import init_db, SessionLocal, AutomationScenario, CostParameter
import pandas as pd


def seed_scenarios(db):
    """Seed automation scenarios from CSV."""
    csv_path = os.path.join(os.path.dirname(__file__), "../data/automation_scenarios.csv")

    if not os.path.exists(csv_path):
        print(f"WARNING: {csv_path} not found, skipping scenario seeding")
        return

    existing = db.query(AutomationScenario).count()
    if existing > 0:
        print(f"Scenarios already seeded ({existing} records), skipping...")
        return

    df = pd.read_csv(csv_path)
    for _, row in df.iterrows():
        scenario = AutomationScenario(
            scenario_id=int(row["scenario_id"]),
            scenario_name=row["scenario_name"],
            category=row["category"],
            applicable_industry=row["applicable_industry"],
            sku_min=int(row["sku_min"]),
            sku_max=int(row["sku_max"]),
            order_min=int(row["order_min"]),
            order_max=int(row["order_max"]),
            capex_min=float(row["capex_min"]),
            capex_max=float(row["capex_max"]),
            labor_saving=float(row["labor_saving"]),
            efficiency_gain=float(row["efficiency_gain"]),
            risk_level=row["risk_level"],
        )
        db.add(scenario)

    db.commit()
    print(f"Seeded {len(df)} automation scenarios")


def seed_cost_parameters(db):
    """Seed cost parameters from CSV."""
    csv_path = os.path.join(os.path.dirname(__file__), "../data/cost_parameters.csv")

    if not os.path.exists(csv_path):
        print(f"WARNING: {csv_path} not found, skipping cost parameter seeding")
        return

    existing = db.query(CostParameter).count()
    if existing > 0:
        print(f"Cost parameters already seeded ({existing} records), skipping...")
        return

    df = pd.read_csv(csv_path)
    for _, row in df.iterrows():
        param = CostParameter(
            parameter_id=int(row["parameter_id"]),
            region=row["region"],
            warehouse_rent_per_sqm=float(row["warehouse_rent_per_sqm"]),
            labor_cost_per_person_year=float(row["labor_cost_per_person_year"]),
            equipment_maintenance_rate=float(row["equipment_maintenance_rate"]),
            overhead_rate=float(row["overhead_rate"]),
            pallet_density=float(row["pallet_density"]),
        )
        db.add(param)

    db.commit()
    print(f"Seeded {len(df)} cost parameters")


if __name__ == "__main__":
    print("Initializing database...")
    os.makedirs("data", exist_ok=True)
    init_db()
    print("Database tables created.")

    db = SessionLocal()
    try:
        seed_scenarios(db)
        seed_cost_parameters(db)
        print("Database initialization complete!")
    finally:
        db.close()
