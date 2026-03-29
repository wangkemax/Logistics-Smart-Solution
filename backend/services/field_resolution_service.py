"""
field_resolution_service.py — Merge Multiple Field Sources into Final Values
============================================================================

Responsibility:
  Take one field's multiple sources (extracted / assumed / manual_input)
  and resolve it to a single final value with priority rules and full trace.

Priority (highest to lowest):
  1. manual_confirmed   — user explicitly entered or confirmed
  2. extracted_provided — explicitly stated in tender document
  3. extracted_inferred — reasonably inferred from document context
  4. assumed            — system-generated assumption from template
  5. missing            — no value available

Version: v0.6.1
"""

from typing import Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


# =============================================================================
# Priority constants
# =============================================================================
SOURCE_PRIORITY = {
    "manual_confirmed":   100,
    "extracted_provided": 80,
    "extracted_inferred": 60,
    "assumed":            40,
    "missing":             0,
}

SOURCE_STATUS_LABELS = {
    "manual_confirmed":   "✅ 人工确认",
    "extracted_provided": "📄 原文提取",
    "extracted_inferred": "🔍 文档推断",
    "assumed":            "⚠️ 系统假设",
    "missing":            "❌ 缺失",
}


# =============================================================================
# Input source dataclasses
# =============================================================================

@dataclass
class FieldSource:
    """One source of truth for a field value."""
    source_type: str                           # manual_confirmed | extracted_provided | etc.
    value: Any = None
    unit: Optional[str] = None
    status: str = "pending"                    # pending | resolved
    comment: str = ""
    updated_at: Optional[str] = None
    section: str = ""                          # which section of tender this came from
    snippet: str = ""                          # excerpt from source document

    def to_dict(self) -> dict:
        return {
            "source_type": self.source_type,
            "value": self.value,
            "unit": self.unit,
            "status": self.status,
            "comment": self.comment,
            "updated_at": self.updated_at,
            "section": self.section,
            "snippet": self.snippet[:200] if self.snippet else "",
        }


@dataclass
class ResolvedField:
    """Final resolved output for one field."""
    field_key: str
    final_value: Any
    final_unit: Optional[str]
    final_status: str                          # resolved | blocked
    source_type: str                            # which source won
    usable: bool
    priority: str = "P0"                        # P0 | P1 | P2
    impact: str = ""
    confidence: float = 0.0                     # 0.0 – 1.0
    trace: list[dict] = field(default_factory=list)
    resolution_note: str = ""

    def to_dict(self) -> dict:
        return {
            "field_key": self.field_key,
            "final_value": self.final_value,
            "final_unit": self.final_unit,
            "final_status": self.final_status,
            "source_type": self.source_type,
            "usable": self.usable,
            "priority": self.priority,
            "impact": self.impact,
            "confidence": self.confidence,
            "trace": self.trace,
            "resolution_note": self.resolution_note,
        }


# =============================================================================
# Unit conversion helpers
# =============================================================================

# Orders per month → orders per day (assuming 30 days/month)
ORDERS_PER_DAY_FROM_MONTH = 1 / 30
# Orders per year → orders per day (assuming 365 days/year)
ORDERS_PER_DAY_FROM_YEAR = 1 / 365
# Square meters — no conversion needed
AREA_UNITS = {"sqm", "sqmeters", "平方米"}


def _normalize_unit(field_key: str, value: Any, unit: Optional[str]) -> tuple[Any, Optional[str]]:
    """
    Normalize value to standard internal unit.
    Returns (normalized_value, normalized_unit).
    """
    if value is None:
        return None, None

    # Daily orders: convert month/year to day
    if field_key == "daily_orders":
        if unit in ("orders/month", "orders/months", "月订单量", "月"):
            return round(value * ORDERS_PER_DAY_FROM_MONTH), "orders/day"
        elif unit in ("orders/year", "orders/yearly", "年订单量", "年"):
            return round(value * ORDERS_PER_DAY_FROM_YEAR), "orders/day"
        elif unit in ("orders/day", "日订单量", "日", None):
            return value, "orders/day"

    # Warehouse area: normalize to sqm
    if field_key == "warehouse_area":
        return value, "sqm"

    # Contract years: normalize to years
    if field_key == "contract_years":
        return value, "years"

    # DC count: no unit
    if field_key == "dc_count":
        return value, "DCs"

    return value, unit


# =============================================================================
# Core resolution functions
# =============================================================================

def resolve_field(
    field_key: str,
    extracted_field: Optional[dict] = None,
    manual_input: Optional[dict] = None,
    assumed_input: Optional[dict] = None,
    priority: str = "P0",
    impact: str = "",
) -> ResolvedField:
    """
    Resolve a single field from multiple sources.

    Args:
        field_key:          Field identifier (e.g. "daily_orders", "contract_years")
        extracted_field:    Dict with keys: value, unit, status, section, snippet
        manual_input:       Dict with keys: value, unit, source_type(="manual_confirmed"), comment, updated_at
        assumed_input:      Dict with keys: value, unit, assumption_rule
        priority:            P0 | P1 | P2
        impact:             Business impact description

    Returns:
        ResolvedField
    """
    now = datetime.utcnow().isoformat()
    trace = []
    candidates = []

    # ---- Build candidate list ----
    # 1. Extracted source
    if extracted_field and isinstance(extracted_field, dict):
        ext_status = extracted_field.get("status", "missing")
        ext_value = extracted_field.get("value")
        ext_unit = extracted_field.get("unit")
        if ext_status == "explicit":
            ext_source_type = "extracted_provided"
        elif ext_status in ("inferred", "partial"):
            ext_source_type = "extracted_inferred"
        elif ext_status == "ambiguous":
            ext_source_type = "extracted_inferred"  # treat as inferred until resolved
        else:
            ext_source_type = "missing"

        if ext_value is not None:
            norm_val, norm_unit = _normalize_unit(field_key, ext_value, ext_unit or extracted_field.get("unit"))
            candidates.append({
                "source_type": ext_source_type,
                "value": norm_val,
                "unit": norm_unit,
                "priority_score": SOURCE_PRIORITY[ext_source_type],
                "section": extracted_field.get("section", ""),
                "snippet": extracted_field.get("source_basis", "")[:200],
            })
        trace.append({
            "source_type": ext_source_type,
            "value": ext_value,
            "status": ext_status,
            "note": "招标文件提取" if ext_value is not None else "招标文件未提供",
        })

    # 2. Manual input (manual_confirmed)
    if manual_input and isinstance(manual_input, dict):
        m_val = manual_input.get("value")
        m_unit = manual_input.get("unit")
        if m_val is not None:
            norm_val, norm_unit = _normalize_unit(field_key, m_val, m_unit)
            candidates.append({
                "source_type": "manual_confirmed",
                "value": norm_val,
                "unit": norm_unit,
                "priority_score": SOURCE_PRIORITY["manual_confirmed"],
                "comment": manual_input.get("comment", ""),
                "updated_at": manual_input.get("updated_at", now),
            })
        trace.append({
            "source_type": "manual_confirmed",
            "value": m_val,
            "unit": m_unit,
            "note": manual_input.get("comment", "人工补录"),
            "updated_at": manual_input.get("updated_at", now),
        })

    # 3. Assumed input
    if assumed_input and isinstance(assumed_input, dict):
        a_val = assumed_input.get("value")
        a_unit = assumed_input.get("unit")
        if a_val is not None:
            norm_val, norm_unit = _normalize_unit(field_key, a_val, a_unit)
            candidates.append({
                "source_type": "assumed",
                "value": norm_val,
                "unit": norm_unit,
                "priority_score": SOURCE_PRIORITY["assumed"],
                "assumption_rule": assumed_input.get("assumption_rule", ""),
            })
        trace.append({
            "source_type": "assumed",
            "value": a_val,
            "note": assumed_input.get("assumption_rule", "系统假设"),
        })

    # ---- Select winner ----
    if not candidates:
        # No value from any source
        return ResolvedField(
            field_key=field_key,
            final_value=None,
            final_unit=None,
            final_status="blocked",
            source_type="missing",
            usable=False,
            priority=priority,
            impact=impact,
            confidence=0.0,
            trace=trace,
            resolution_note="所有来源均无有效值",
        )

    winner = max(candidates, key=lambda c: c["priority_score"])
    final_value = winner["value"]
    final_unit = winner.get("unit")
    source_type = winner["source_type"]

    # ---- Usability rules ----
    # P0 field: only manual_confirmed or extracted_provided are usable in full_calc
    if priority == "P0":
        usable = source_type in ("manual_confirmed", "extracted_provided")
        confidence = 1.0 if source_type == "manual_confirmed" else 0.85
        if not usable:
            resolution_note = f"P0字段来源为「{SOURCE_STATUS_LABELS.get(source_type, source_type)}」，不允许进入正式测算"
        else:
            resolution_note = f"值来自{SOURCE_STATUS_LABELS.get(source_type, source_type)}，可用于正式测算"
    elif priority == "P1":
        usable = source_type in ("manual_confirmed", "extracted_provided", "extracted_inferred", "assumed")
        confidence = 0.9 if source_type == "manual_confirmed" else 0.7 if source_type == "extracted_provided" else 0.5
        resolution_note = f"值来自{SOURCE_STATUS_LABELS.get(source_type, source_type)}，可用于估算"
    else:
        usable = True
        confidence = 0.6
        resolution_note = f"值来自{SOURCE_STATUS_LABELS.get(source_type, source_type)}"

    return ResolvedField(
        field_key=field_key,
        final_value=final_value,
        final_unit=final_unit,
        final_status="resolved",
        source_type=source_type,
        usable=usable,
        priority=priority,
        impact=impact,
        confidence=confidence,
        trace=trace,
        resolution_note=resolution_note,
    )


def resolve_all_fields(
    extracted_fields: dict,
    manual_inputs: dict,
    assumptions: Optional[dict] = None,
    field_priorities: Optional[dict] = None,
    field_impacts: Optional[dict] = None,
) -> dict[str, ResolvedField]:
    """
    Resolve all fields in extracted_fields using manual_inputs and assumptions.

    Args:
        extracted_fields:  {field_key: field_obj} from normalized_fields
        manual_inputs:     {field_key: {value, unit, source_type, comment, updated_at}}
        assumptions:       {field_key: {value, unit, assumption_rule}}  (optional)
        field_priorities:  {field_key: "P0"|"P1"|"P2"}  (optional, defaults to P0)
        field_impacts:     {field_key: impact_string}    (optional)

    Returns:
        {field_key: ResolvedField}
    """
    assumptions = assumptions or {}
    field_priorities = field_priorities or {}
    field_impacts = field_impacts or {}

    # All field keys from extracted + manual_inputs
    all_keys = set(extracted_fields.keys()) | set(manual_inputs.keys()) | set(assumptions.keys())

    resolved = {}
    for fkey in all_keys:
        resolved[fkey] = resolve_field(
            field_key=fkey,
            extracted_field=extracted_fields.get(fkey),
            manual_input=manual_inputs.get(fkey),
            assumed_input=assumptions.get(fkey),
            priority=field_priorities.get(fkey, "P0"),
            impact=field_impacts.get(fkey, ""),
        )

    return resolved


def build_resolved_fields_summary(resolved_fields: dict[str, ResolvedField]) -> dict:
    """
    Build a human-readable summary from resolved fields.

    Returns dict with:
      - total_count
      - usable_count
      - blocked_count
      - by_priority: {P0: {total, usable, blocked}, P1: {...}, P2: {...}}
      - by_source: {manual_confirmed: [...], extracted_provided: [...], ...}
    """
    by_priority = {"P0": {"total": 0, "usable": 0, "blocked": 0},
                   "P1": {"total": 0, "usable": 0, "blocked": 0},
                   "P2": {"total": 0, "usable": 0, "blocked": 0}}
    by_source = {}

    for rf in resolved_fields.values():
        pri = rf.priority
        if pri not in by_priority:
            by_priority[pri] = {"total": 0, "usable": 0, "blocked": 0}
        by_priority[pri]["total"] += 1
        if rf.usable:
            by_priority[pri]["usable"] += 1
        else:
            by_priority[pri]["blocked"] += 1

        src = rf.source_type
        by_source.setdefault(src, []).append(rf.field_key)

    total = len(resolved_fields)
    usable = sum(1 for rf in resolved_fields.values() if rf.usable)
    blocked = total - usable

    return {
        "total_count": total,
        "usable_count": usable,
        "blocked_count": blocked,
        "by_priority": by_priority,
        "by_source": by_source,
    }
