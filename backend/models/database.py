from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, JSON
from sqlalchemy.orm import declarative_base
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


class PipelineRun(Base):
    """Pipeline execution record — survives page refresh."""
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, index=True)
    pipeline_id = Column(String(20), unique=True, index=True)
    job_id = Column(String(40), index=True, nullable=True)  # external job identifier (unique enforced at service layer)
    status = Column(String(20), default="RUNNING")           # RUNNING / COMPLETE / FAILED / CANCELLED / RETRY
    tender_document = Column(Text, default="")
    tender_document_hash = Column(String(64), nullable=True, index=True)  # SHA256 for deduplication
    params_json = Column(Text, default="{}")                  # JSON string
    profile_json = Column(Text, default="{}")
    recommendations_json = Column(Text, default="[]")
    comparisons_json = Column(Text, default="[]")
    qa_verdict = Column(String(20), default="")
    pdf_path = Column(String(500), nullable=True)
    pdf_url = Column(String(200), nullable=True)
    error = Column(Text, nullable=True)
    total_duration_seconds = Column(Float, nullable=True)
    retry_count = Column(Integer, default=0)                 # how many times retried
    max_retries = Column(Integer, default=2)                 # max retries allowed
    parent_job_id = Column(String(40), nullable=True)        # for retry chains
    worker_pid = Column(Integer, nullable=True)              # tracking which worker
    api_base_url = Column(String(200), nullable=True)        # base URL used for this run
    compare_scenario_ids = Column(Text, nullable=True)       # JSON list of scenario IDs
    result_summary = Column(Text, nullable=True)            # JSON summary for task list UI
    # Stage 1 — Tender Understanding fields
    analysis_markdown = Column(Text, nullable=True)        # Full 13-section Markdown report
    analysis_sections_json = Column(Text, nullable=True)   # v0.2: 13-dimension section texts {section_name: text}
    normalized_fields_json = Column(Text, nullable=True)   # JSON: normalized fields with priority/impact
    missing_items_json = Column(Text, nullable=True)        # JSON: {p0: [...], p1: [...]}
    clarification_questions_json = Column(Text, nullable=True)  # JSON: list of clarification questions
    quality_score_json = Column(Text, nullable=True)       # JSON: completeness/evidence/readiness scores
    readiness_json = Column(Text, nullable=True)         # v0.2: readiness per downstream module
    analysis_version = Column(String(20), default="v0.2")  # Schema version for benchmark comparison
    prompt_version = Column(String(20), default="tender_understanding_v0.2")  # Prompt version
    model_name = Column(String(80), nullable=True)         # v0.2: LLM model used (MiniMax-M2.7-highspeed etc.)
    pipeline_gate_json = Column(Text, nullable=True)     # JSON: {cost_model: BLOCK|PASS, ...}
    # v0.6.1 — Clarification Workflow fields
    manual_inputs_json = Column(Text, nullable=True)       # JSON: {field_key: {value, unit, source_type, status, comment, updated_at}}
    resolved_fields_json = Column(Text, nullable=True)     # JSON: {field_key: ResolvedField.to_dict()}
    clarification_tasks_json = Column(Text, nullable=True)  # JSON: ClarificationTaskList.to_dict()
    operation_profile_json = Column(Text, nullable=True)    # v0.6.5: OperationProfile derived from service_scope
    base_solution_json = Column(Text, nullable=True)       # v0.7: BaseSolution JSON
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)


class PipelineStage(Base):
    """Individual stage record within a pipeline run."""
    __tablename__ = "pipeline_stages"

    id = Column(Integer, primary_key=True, index=True)
    pipeline_id = Column(String(20), index=True)
    stage_name = Column(String(50))
    status = Column(String(20))                               # PENDING / RUNNING / DONE / FAILED / SKIPPED
    duration_seconds = Column(Float, nullable=True)
    error = Column(Text, nullable=True)
    output_file = Column(String(500), nullable=True)
    extra_json = Column(Text, default="{}")                   # stage-specific extra data
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # Late import to avoid circular import; Assumption registers itself with Base on import
    from backend.models import assumption_models  # noqa: F401
    from backend.models import equipment_models  # noqa: F401
    from backend.models.workspace_models import Workspace  # noqa: F401
    Base.metadata.create_all(bind=engine)
