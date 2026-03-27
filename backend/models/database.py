from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/logistics_presale.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class AutomationScenario(Base):
    __tablename__ = "automation_scenarios"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, unique=True, index=True)
    scenario_name = Column(String(100), nullable=False)
    category = Column(String(50))
    applicable_industry = Column(String(200))
    sku_min = Column(Integer, default=0)
    sku_max = Column(Integer, default=9999999)
    order_min = Column(Integer, default=0)
    order_max = Column(Integer, default=9999999)
    capex_min = Column(Float, default=0)
    capex_max = Column(Float, default=99999999)
    labor_saving = Column(Float, default=0)
    efficiency_gain = Column(Float, default=0)
    risk_level = Column(String(10), default="中")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    project_name = Column(String(200))
    industry = Column(String(50))
    warehouse_area = Column(Float)
    sku_count = Column(Integer)
    daily_orders = Column(Integer)
    inventory = Column(Integer)
    labor_cost_level = Column(String(20))
    budget_level = Column(String(20))
    automation_expectation = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)


class Solution(Base):
    __tablename__ = "solutions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer)
    scenario_id = Column(Integer)
    score = Column(Float)
    reason = Column(Text)
    risk = Column(Text)
    cost_summary = Column(Text)
    roi = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class CostParameter(Base):
    __tablename__ = "cost_parameters"

    id = Column(Integer, primary_key=True, index=True)
    parameter_id = Column(Integer, unique=True)
    region = Column(String(20))
    warehouse_rent_per_sqm = Column(Float)
    labor_cost_per_person_year = Column(Float)
    equipment_maintenance_rate = Column(Float)
    overhead_rate = Column(Float)
    pallet_density = Column(Float, default=4)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
