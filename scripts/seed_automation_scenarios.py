#!/usr/bin/env python3
"""
Seed Automation Scenarios
=========================
Initializes the automation_scenarios table from hardcoded defaults.

Usage:
    python scripts/seed_automation_scenarios.py

Run from project root:
    cd ~/Projects/logistics-presale-ai && python scripts/seed_automation_scenarios.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.repositories.scenario_repository import seed_default_scenarios


def main():
    print("🌱 Seeding automation_scenarios table...")
    count = seed_default_scenarios()
    if count == 0:
        print("✅ Table already has data, skipping.")
    else:
        print(f"✅ Inserted {count} scenarios.")
    
    # Verify
    from backend.repositories.scenario_repository import get_active_scenarios
    scenarios = get_active_scenarios()
    print(f"📦 Total active scenarios: {len(scenarios)}")
    for s in scenarios:
        print(f"   [{s['scenario_id']:02d}] {s['scenario_name']} | {s['category']} | {s['applicable_industry']}")


if __name__ == "__main__":
    main()
