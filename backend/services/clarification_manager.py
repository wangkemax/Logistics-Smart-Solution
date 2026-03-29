"""
clarification_manager.py — Build Clarification Task Lists for UI
===============================================================

Responsibilities:
  1. Take current project state (from PipelineRun) and build a structured
     Clarification Task List for the frontend Clarification Workspace.
  2. Group tasks by priority (P0_must / P1_should / P2_nice)
  3. Identify conflict items (ambiguous fields)
  4. Surface current assumptions (for review)

This module does NOT handle user input capture —
that is handled by input_capture_service.py.

Version: v0.6.1
"""

from typing import Optional
from dataclasses import dataclass, field
from backend.services.tender_clarification import generate_clarification_questions
from backend.services.tender_schema import FIELD_REGISTRY


# =============================================================================
# Task group definitions
# =============================================================================

@dataclass
class ClarificationTask:
    """A single clarification task shown to the user."""
    question_id: str
    field_key: str
    display_name: str
    priority: str                          # P0 | P1 | P2
    category: str                         # missing | ambiguous | conflict | assumption_review
    title: str
    question_text: str
    guidance: str
    expected_input_type: str
    acceptable_units: list[str] = field(default_factory=list)
    current_status: str = "open"         # open | resolved | skipped
    blocking_impact: str = ""
    suggested_answer_format: str = ""
    example_answer: str = ""
    current_value: Optional[str] = None   # what system currently has
    conflict_candidates: list = field(default_factory=list)  # for ambiguous fields
    service_matrix: Optional[dict] = None  # v0.6.4: structured service scope matrix

    def to_dict(self) -> dict:
        return {
            "question_id": self.question_id,
            "field_key": self.field_key,
            "display_name": self.display_name,
            "priority": self.priority,
            "category": self.category,
            "title": self.title,
            "question_text": self.question_text,
            "guidance": self.guidance,
            "expected_input_type": self.expected_input_type,
            "acceptable_units": self.acceptable_units,
            "current_status": self.current_status,
            "blocking_impact": self.blocking_impact,
            "suggested_answer_format": self.suggested_answer_format,
            "example_answer": self.example_answer,
            "current_value": self.current_value,
            "conflict_candidates": self.conflict_candidates,
            "service_matrix": self.service_matrix,
        }


@dataclass
class ClarificationTaskList:
    """Full clarification task list for a project."""
    project_id: str
    current_mode: str                     # blocked | range_estimate | full_calc
    readiness_score: float
    must_answer: list[ClarificationTask]  # P0 blocking items
    should_answer: list[ClarificationTask]  # P1 items
    nice_to_have: list[ClarificationTask]   # P2 items
    conflict_items: list[ClarificationTask]  # ambiguous / conflicting fields
    assumption_review: list[ClarificationTask]  # current assumptions to review
    resolved_count: int = 0
    total_count: int = 0

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "current_mode": self.current_mode,
            "readiness_score": self.readiness_score,
            "must_answer": [t.to_dict() for t in self.must_answer],
            "should_answer": [t.to_dict() for t in self.should_answer],
            "nice_to_have": [t.to_dict() for t in self.nice_to_have],
            "conflict_items": [t.to_dict() for t in self.conflict_items],
            "assumption_review": [t.to_dict() for t in self.assumption_review],
            "resolved_count": self.resolved_count,
            "total_count": self.total_count,
            "summary": {
                "must_total": len(self.must_answer),
                "should_total": len(self.should_answer),
                "nice_total": len(self.nice_to_have),
                "conflict_total": len(self.conflict_items),
                "assumption_total": len(self.assumption_review),
                "resolved": self.resolved_count,
            }
        }


# =============================================================================
# Task builder
# =============================================================================

def build_clarification_tasks(
    pipeline_id: str,
    readiness: dict,
    downstream_input: dict,
    normalized_fields: dict,
    manual_inputs: dict,
    clarification_questions: list[dict],
    resolved_fields: dict | None = None,
) -> ClarificationTaskList:
    """
    Build the full ClarificationTaskList from current project state.

    Args:
        pipeline_id:         Pipeline/task ID
        readiness:           Readiness dict from tender_readiness
        downstream_input:     Cost model downstream_input
        normalized_fields:   Normalized fields from analyze_and_extract
        manual_inputs:       Already-confirmed manual inputs {field_key: {...}}
        clarification_questions: Questions from tender_clarification
        resolved_fields:     Resolved fields dict {field_key: ResolvedField} (optional)

    Returns:
        ClarificationTaskList
    """
    readiness_level = readiness.get("level", "blocked") if isinstance(readiness, dict) else "blocked"
    readiness_score = readiness.get("readiness_score", 0.0) if isinstance(readiness, dict) else 0.0
    recommended_mode = downstream_input.get("recommended_mode", "blocked") if isinstance(downstream_input, dict) else "blocked"

    must_answer = []
    should_answer = []
    nice_to_have = []
    conflict_items = []
    assumption_review = []
    resolved_count = 0

    # ---- Map existing clarification questions to tasks ----
    for q in clarification_questions:
        field_key = q.get("field_key", "")
        status = q.get("status", "pending")
        severity = q.get("severity", "P1")
        category = _infer_category(q, normalized_fields.get(field_key, {}))

        # Check if already resolved by manual input
        is_resolved = (
            field_key in manual_inputs
            or status == "resolved"
        )
        if is_resolved and severity == "P0":
            resolved_count += 1

        fdef = FIELD_REGISTRY.get(field_key) if field_key else None
        display_name = fdef.display_name if fdef else (field_key or "通用字段")
        priority_tag = severity

        # Current value in the system
        current_val = _get_current_value(field_key, normalized_fields, manual_inputs)

        # Conflict candidates (for ambiguous fields)
        conflict_candidates = q.get("candidate_values", [])

        # Impact statement
        impact = ""
        if isinstance(downstream_input, dict):
            ri = downstream_input.get("required_inputs", {}).get(field_key, {})
            impact = ri.get("impact", "") or q.get("why_it_matters", "")

        task = ClarificationTask(
            question_id=q.get("id", f"Q-{field_key}"),
            field_key=field_key,
            display_name=display_name,
            priority=priority_tag,
            category=category,
            title=q.get("question", f"请补充「{display_name}」"),
            question_text=q.get("question", ""),
            guidance=q.get("why_it_matters", ""),
            expected_input_type=_get_input_type(field_key),
            acceptable_units=_get_acceptable_units(field_key),
            current_status="resolved" if is_resolved else "open",
            blocking_impact=impact,
            suggested_answer_format=q.get("suggested_answer_format", ""),
            example_answer=q.get("example_answer", ""),
            current_value=current_val,
            conflict_candidates=conflict_candidates,
        )

        # Categorize by priority and category
        if category == "conflict":
            conflict_items.append(task)
        elif priority_tag == "P0":
            must_answer.append(task)
        elif priority_tag == "P1":
            should_answer.append(task)
        else:
            nice_to_have.append(task)

    # ---- Check required_inputs from downstream_input for missing P0 fields ----
    if isinstance(downstream_input, dict):
        required = downstream_input.get("required_inputs", {})
        for fkey, req in required.items():
            pri = req.get("priority", "P1")
            status = req.get("status", "missing")
            if pri == "P0" and status in ("missing", "ambiguous") and status != "provided":
                # Already have a task for this?
                if not any(t.field_key == fkey for t in must_answer + conflict_items):
                    fdef = FIELD_REGISTRY.get(fkey)
                    display_name = fdef.display_name if fdef else fkey
                    # v0.6.4: attach SERVICE_MATRIX for service_scope
                    svc_matrix = None
                    if fkey == "service_scope":
                        from backend.services.tender_schema import SERVICE_MATRIX
                        svc_matrix = SERVICE_MATRIX
                    task = ClarificationTask(
                        question_id=f"Q-AUTO-{fkey}",
                        field_key=fkey,
                        display_name=display_name,
                        priority="P0",
                        category="missing",
                        title=f"请补充「{display_name}」",
                        question_text=req.get("clarification_question", f"请提供「{display_name}」的具体数据。"),
                        guidance=req.get("impact", "该字段影响下游成本测算"),
                        expected_input_type=_get_input_type(fkey),
                        acceptable_units=_get_acceptable_units(fkey),
                        current_status="resolved" if fkey in manual_inputs else "open",
                        blocking_impact=req.get("impact", ""),
                        service_matrix=svc_matrix,
                    )
                    must_answer.append(task)

    # ---- Fallback: if no P0 tasks exist and pipeline may be blocked,
    #     generate tasks for all P0 fields that are NOT resolved in resolved_fields ----
    if not must_answer and (recommended_mode == "blocked" or not recommended_mode):
        from backend.services.tender_schema import get_p0_fields
        already_done = {t.field_key for t in conflict_items}
        for fkey in get_p0_fields():
            if fkey in already_done:
                continue
            # resolved_fields: dict of ResolvedField objects or dicts with .usable / usable key
            rf = (resolved_fields or {}).get(fkey)
            if rf:
                # Check if field is resolved (usable=True)
                usable = getattr(rf, "usable", None)
                if usable is None and isinstance(rf, dict):
                    usable = rf.get("usable")
                if usable:
                    continue  # Field is resolved — skip
            fdef = FIELD_REGISTRY.get(fkey)
            display_name = fdef.display_name if fdef else fkey
            svc_matrix = None
            if fkey == "service_scope":
                from backend.services.tender_schema import SERVICE_MATRIX
                svc_matrix = SERVICE_MATRIX
            task = ClarificationTask(
                question_id=f"Q-AUTO-{fkey}",
                field_key=fkey,
                display_name=display_name,
                priority="P0",
                category="missing",
                title=f"请补充「{display_name}」",
                question_text=f"请提供「{display_name}」的具体数据，以便进入成本测算。",
                guidance="该字段为P0关键字段，缺失将导致系统无法进入任何形式的成本测算。",
                expected_input_type=_get_input_type(fkey),
                acceptable_units=_get_acceptable_units(fkey),
                current_status="resolved" if (rf and (getattr(rf, "usable", False) or (isinstance(rf, dict) and rf.get("usable")))) else "open",
                blocking_impact="P0关键字段，缺失将阻塞成本测算",
                service_matrix=svc_matrix,
            )
            must_answer.append(task)

    total_count = (len(must_answer) + len(should_answer) + len(nice_to_have)
                   + len(conflict_items) + len(assumption_review))

    return ClarificationTaskList(
        project_id=pipeline_id,
        current_mode=recommended_mode,
        readiness_score=readiness_score,
        must_answer=must_answer,
        should_answer=should_answer,
        nice_to_have=nice_to_have,
        conflict_items=conflict_items,
        assumption_review=assumption_review,
        resolved_count=resolved_count,
        total_count=total_count,
    )


# =============================================================================
# Helpers
# =============================================================================

def _infer_category(question: dict, field_obj: dict) -> str:
    """Infer the category of a clarification question."""
    q_text = question.get("question", "").lower()
    if "冲突" in q_text or "矛盾" in q_text or "不一致" in q_text:
        return "conflict"
    if "假设" in q_text or "推断" in q_text:
        return "assumption_review"
    fstatus = field_obj.get("status", "missing") if isinstance(field_obj, dict) else "missing"
    if fstatus == "ambiguous":
        return "conflict"
    return question.get("category", "missing")


def _get_current_value(field_key: str, normalized_fields: dict, manual_inputs: dict) -> Optional[str]:
    """Get the current string value for display."""
    if field_key in manual_inputs:
        mi = manual_inputs[field_key]
        val = mi.get("value")
        unit = mi.get("unit", "")
        if unit:
            return f"{val} {unit}"
        return str(val) if val is not None else None

    nf = normalized_fields.get(field_key, {})
    if isinstance(nf, dict):
        val = nf.get("value")
        unit = nf.get("unit", "")
        status = nf.get("status", "")
        if status == "ambiguous":
            sources = nf.get("source_basis", "")
            return f"歧义: {sources[:50]}..."
        if val is not None:
            if unit:
                return f"{val} {unit}"
            return str(val)
    return None


def _get_input_type(field_key: str) -> str:
    """Map field_key to expected input type for frontend."""
    choice_fields = {"labor_cost_level", "automation_expectation", "region", "industry"}
    text_fields = {"kpi_targets", "penalty_rules"}  # service_scope now uses matrix
    if field_key == "service_scope":
        return "service_scope_matrix"
    if field_key in text_fields:
        return "text"
    if field_key in choice_fields:
        return "choice"
    return "number_with_unit"


def _get_acceptable_units(field_key: str) -> list[str]:
    """Get acceptable units for a field."""
    from backend.services.input_capture_service import MANUAL_INPUT_DEFINITIONS
    defn = MANUAL_INPUT_DEFINITIONS.get(field_key)
    if defn:
        return defn.acceptable_units
    return []


# =============================================================================
# Compute readiness after manual inputs are merged
# =============================================================================

def compute_readiness_after_inputs(
    resolved_fields: dict,
    p0_field_keys: list[str],
    p1_field_keys: list[str],
) -> dict:
    """
    Re-compute readiness level based on resolved fields.

    This is a simplified readiness recalc used by the recompute pipeline.
    """
    from backend.services.field_resolution_service import ResolvedField

    p0_usable = 0
    p0_total = len(p0_field_keys)
    p1_usable = 0
    p1_total = len(p1_field_keys)

    for fkey in p0_field_keys:
        rf = resolved_fields.get(fkey)
        if isinstance(rf, ResolvedField) and rf.usable:
            p0_usable += 1

    for fkey in p1_field_keys:
        rf = resolved_fields.get(fkey)
        if isinstance(rf, ResolvedField) and rf.usable:
            p1_usable += 1

    p0_ready = p0_usable == p0_total
    p1_ready = p1_usable == p1_total

    if p0_ready and p1_ready:
        level = "ready"
    elif p0_ready:
        level = "partial_ready"
    else:
        level = "blocked"

    readiness_score = 0.0
    if p0_total > 0:
        readiness_score += (p0_usable / p0_total) * 0.6
    if p1_total > 0:
        readiness_score += (p1_usable / p1_total) * 0.4

    return {
        "level": level,
        "readiness_score": round(readiness_score, 3),
        "for_cost_model": p0_ready,
        "for_solution_design": p0_ready,
        "for_contract_review": p1_ready,
        "p0_summary": {"total": p0_total, "usable": p0_usable, "missing": p0_total - p0_usable},
        "p1_summary": {"total": p1_total, "usable": p1_usable, "missing": p1_total - p1_usable},
    }
