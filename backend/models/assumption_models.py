"""backend/models/assumption_models.py SQLAlchemy model for assumptions table (v0.9) """
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text

from backend.models.database import Base


class Assumption(Base):
    __tablename__ = "assumptions"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(40), index=True, nullable=False)
    version_id = Column(Integer, default=1)
    field_key = Column(String(50), nullable=False)
    assumption_value = Column(Text, nullable=False)
    assumption_rule = Column(Text, default="")
    source = Column(String(30), default="default_fallback")
    source_type = Column(String(30), default="system_default")
    confidence = Column(Float, default=0.5)
    is_overridden = Column(Boolean, default=False)
    validated = Column(Boolean, default=False)
    context_tags = Column(Text, default="{}")    # JSON string
    impact_factors = Column(Text, default="[]")  # JSON string
    effective_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
