"""Section builders for BaseSolution generation (v0.8)."""

from backend.solution.section_builders.operation_mode_builder import build_operation_mode
from backend.solution.section_builders.process_design_builder import build_process_design
from backend.solution.section_builders.labor_model_builder import build_labor_model
from backend.solution.section_builders.kpi_framework_builder import build_kpi_framework

__all__ = [
    "build_operation_mode",
    "build_process_design",
    "build_labor_model",
    "build_kpi_framework",
]
