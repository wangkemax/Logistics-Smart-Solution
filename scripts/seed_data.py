#!/usr/bin/env python3
"""Re-seed or update database data."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.init_db import seed_scenarios, seed_cost_parameters
from backend.models.database import SessionLocal, init_db


if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        seed_scenarios(db)
        seed_cost_parameters(db)
        print("Data seeding complete!")
    finally:
        db.close()
