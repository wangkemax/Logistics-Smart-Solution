"""backend/services/assumption_service.py Core assumption registry service for v0.9 """
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from backend.models.assumption_models import Assumption
from backend.models.database import SessionLocal
from backend.schemas.assumption_schemas import (
    AssumptionSchema,
    AssumptionSourceType,
)


class AssumptionService:
    """Service for managing assumption lifecycle."""

    def __init__(self):
        pass

    def _to_schema(self, model: Assumption) -> AssumptionSchema:
        return AssumptionSchema(
            field_key=model.field_key,
            value=model.assumption_value,
            rule=model.assumption_rule or "",
            source=model.source,
            source_type=model.source_type,
            confidence=model.confidence,
            is_overridden=model.is_overridden,
            validated=model.validated,
            benchmark_ref=model.assumption_rule or "",
            context_tags=json.loads(model.context_tags or "{}"),
            impact_factors=json.loads(model.impact_factors or "[]"),
            effective_date=model.effective_date,
            version_id=model.version_id,
        )

    def register(
        self,
        run_id: str,
        field_key: str,
        value: str,
        rule: str,
        source: str = "default_fallback",
        source_type: str = "system_default",
        confidence: float = 0.5,
        context_tags: dict = None,
        impact_factors: list = None,
        effective_date: datetime = None,
    ) -> AssumptionSchema:
        """Register a new assumption for a run."""
        db = SessionLocal()
        try:
            existing = db.query(Assumption).filter(
                Assumption.run_id == run_id,
                Assumption.field_key == field_key,
            ).first()

            if existing:
                existing.assumption_value = value
                existing.assumption_rule = rule
                existing.source = source
                existing.source_type = source_type
                existing.confidence = confidence
                existing.context_tags = json.dumps(context_tags or {})
                existing.impact_factors = json.dumps(impact_factors or [])
                existing.effective_date = effective_date
                existing.is_overridden = False
                db.commit()
                db.refresh(existing)
                return self._to_schema(existing)

            assumption = Assumption(
                run_id=run_id,
                field_key=field_key,
                assumption_value=value,
                assumption_rule=rule,
                source=source,
                source_type=source_type,
                confidence=confidence,
                context_tags=json.dumps(context_tags or {}),
                impact_factors=json.dumps(impact_factors or []),
                effective_date=effective_date or datetime.utcnow(),
                version_id=1,
            )
            db.add(assumption)
            db.commit()
            db.refresh(assumption)
            return self._to_schema(assumption)
        finally:
            db.close()

    def override(
        self,
        run_id: str,
        field_key: str,
        new_value: str,
        new_rule: str = "",
    ) -> Optional[AssumptionSchema]:
        """Override an existing assumption. Creates a new version."""
        db = SessionLocal()
        try:
            existing = db.query(Assumption).filter(
                Assumption.run_id == run_id,
                Assumption.field_key == field_key,
            ).first()

            if not existing:
                return None

            new_assumption = Assumption(
                run_id=run_id,
                field_key=field_key,
                assumption_value=new_value,
                assumption_rule=new_rule or existing.assumption_rule,
                source="manual_override",
                source_type=AssumptionSourceType.USER_MODIFIED.value,
                confidence=1.0,
                is_overridden=True,
                validated=False,
                context_tags=existing.context_tags,
                impact_factors=existing.impact_factors,
                effective_date=datetime.utcnow(),
                version_id=existing.version_id + 1,
            )
            # existing.is_overridden = True  # old version stays as-is (is_overridden=False means it's the latest)
            db.add(new_assumption)
            db.commit()
            db.refresh(new_assumption)
            return self._to_schema(new_assumption)
        finally:
            db.close()

    def get_for_run(self, run_id: str) -> list[AssumptionSchema]:
        """Get all assumptions for a pipeline run."""
        db = SessionLocal()
        try:
            assumptions = db.query(Assumption).filter(
                Assumption.run_id == run_id
            ).order_by(Assumption.version_id.desc()).all()

            seen = set()
            result = []
            for a in assumptions:
                if a.field_key not in seen:
                    seen.add(a.field_key)
                    result.append(self._to_schema(a))
            return result
        finally:
            db.close()

    def get_version_history(
        self, run_id: str, field_key: str
    ) -> list[AssumptionSchema]:
        """Get all versions of a specific assumption."""
        db = SessionLocal()
        try:
            assumptions = db.query(Assumption).filter(
                Assumption.run_id == run_id,
                Assumption.field_key == field_key,
            ).order_by(Assumption.version_id.desc()).all()
            return [self._to_schema(a) for a in assumptions]
        finally:
            db.close()

    def rollback(
        self, run_id: str, field_key: str, target_version: int
    ) -> Optional[AssumptionSchema]:
        """Rollback an assumption to a specific version."""
        db = SessionLocal()
        try:
            target = db.query(Assumption).filter(
                Assumption.run_id == run_id,
                Assumption.field_key == field_key,
                Assumption.version_id == target_version,
            ).first()

            if not target:
                return None

            new_version = Assumption(
                run_id=run_id,
                field_key=field_key,
                assumption_value=target.assumption_value,
                assumption_rule=target.assumption_rule,
                source="rollback",
                source_type=target.source_type,
                confidence=target.confidence,
                is_overridden=True,
                validated=False,
                context_tags=target.context_tags,
                impact_factors=target.impact_factors,
                effective_date=datetime.utcnow(),
                version_id=(
                    db.query(Assumption)
                    .filter(Assumption.run_id == run_id, Assumption.field_key == field_key)
                    .count()
                ) + 1,
            )
            db.add(new_version)
            db.commit()
            db.refresh(new_version)
            return self._to_schema(new_version)
        finally:
            db.close()
