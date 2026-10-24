"""Startup must survive the automation_scenarios schema and answer /api/health."""
from fastapi.testclient import TestClient

from backend.main import app


def test_health_during_lifespan():
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["service"] == "logistics-presale-ai"


def test_seed_keeps_existing_rows_and_preserves_capex(tmp_path, monkeypatch):
    import sqlite3

    db_file = tmp_path / "presale.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        CREATE TABLE automation_scenarios (
            id INTEGER PRIMARY KEY,
            scenario_id INTEGER,
            scenario_name TEXT,
            category TEXT,
            applicable_industry TEXT,
            sku_min INTEGER,
            sku_max INTEGER,
            order_min INTEGER,
            order_max INTEGER,
            capex_min REAL,
            capex_max REAL,
            labor_saving REAL,
            efficiency_gain REAL,
            risk_level TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO automation_scenarios (
            scenario_id, scenario_name, category, applicable_industry,
            sku_min, sku_max, order_min, order_max, capex_min, capex_max,
            labor_saving, efficiency_gain, risk_level
        ) VALUES (1, '保留方案', '移动机器人', '电商', 1, 9, 1, 9, 500000, 2000000, 0.3, 0.4, '中')
        """
    )
    conn.commit()
    conn.close()

    from backend.repositories.scenario_repository import seed_default_scenarios, get_active_scenarios

    inserted = seed_default_scenarios()
    assert inserted == 0

    check = sqlite3.connect(db_file)
    row = check.execute(
        "SELECT scenario_name, capex_min, min_area, is_active, scenario_code FROM automation_scenarios"
    ).fetchone()
    check.close()
    assert row[0] == "保留方案"
    assert row[1] == 500000
    assert row[2] == 0
    assert row[3] == 1
    assert row[4] == "SCN01"

    active = get_active_scenarios()
    assert active[0]["scenario_id"] == 1
    assert active[0]["capex_min"] == 500000


def test_pdf_upload_rejects_bad_magic_and_oversize(monkeypatch):
    monkeypatch.setenv("MAX_PDF_BYTES", "32")
    with TestClient(app) as client:
        rejected = client.post(
            "/rfp/extract/pdf",
            files={"file": ("note.pdf", b"hello", "application/pdf")},
        )
        assert rejected.status_code == 400
        huge = client.post(
            "/rfp/extract/pdf",
            files={"file": ("note.pdf", b"%PDF" + b"x" * 64, "application/pdf")},
        )
        assert huge.status_code == 413
