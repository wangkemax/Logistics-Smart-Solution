"""backend/schemas/assumption_schemas.py Assumption Pydantic Schemas for v0.9 """
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AssumptionSourceType(str, Enum):
    SYSTEM_DEFAULT = "system_default"    # 系统默认值
    LLM_INFERRED = "llm_inferred"       # LLM 推断
    USER_MODIFIED = "user_modified"     # 用户手动输入/覆盖


class AssumptionSchema(BaseModel):
    """Single assumption record."""
    field_key: str
    value: str
    rule: str = ""
    source: str = "default_fallback"
    source_type: AssumptionSourceType = AssumptionSourceType.SYSTEM_DEFAULT
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    is_overridden: bool = False
    validated: bool = False
    benchmark_ref: str = ""
    context_tags: dict = Field(default_factory=dict)
    impact_factors: list[str] = Field(default_factory=list)
    effective_date: Optional[datetime] = None
    version_id: int = 1

    class Config:
        use_enum_values = True


class AssumptionOverrideRequest(BaseModel):
    """Request to override an assumption value."""
    field_key: str
    new_value: str
    new_rule: str = ""
    override_reason: str = ""


class QAIssue(BaseModel):
    """A single QA issue raised during assumption validation."""
    rule: str
    severity: str = Field(default="warning")  # error | warning | note
    message: str
    field_key: str = ""


class AssumptionQAResult(BaseModel):
    """Result of QA validation on assumptions."""
    passed: bool
    issues: list[QAIssue] = Field(default_factory=list)
    overall_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
