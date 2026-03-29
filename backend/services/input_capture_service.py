"""
input_capture_service.py — Manual Input Validation & Storage
==========================================================

Responsibilities:
  1. Validate incoming manual input (value, unit, range)
  2. Normalize units (month→day for orders, etc.)
  3. Save manual_inputs to database (pipeline_run record)
  4. Track source_type, timestamp, user comment

Version: v0.6.1
"""

import json
import re
from datetime import datetime
from typing import Any, Optional
from dataclasses import dataclass, field


# =============================================================================
# Input definition registry
# =============================================================================

@dataclass
class InputDefinition:
    """Definition of an acceptable manual input field."""
    field_key: str
    display_name: str
    input_type: str                        # number | number_with_unit | text | choice | boolean
    acceptable_units: list[str] = field(default_factory=list)
    required_for_p0: bool = False
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    choices: list[Any] = field(default_factory=list)   # for choice type
    description: str = ""
    unit_conversion_hint: str = ""


MANUAL_INPUT_DEFINITIONS: dict[str, InputDefinition] = {
    "daily_orders": InputDefinition(
        field_key="daily_orders",
        display_name="日均订单量",
        input_type="number_with_unit",
        acceptable_units=["orders/day", "orders/month", "orders/year", "日订单量", "月订单量", "年订单量"],
        required_for_p0=True,
        min_value=1,
        max_value=10_000_000,
        description="订单量口径可按日、月或年填写，系统将自动换算为日均值。",
        unit_conversion_hint="月订单量÷30=日订单量；年订单量÷365=日订单量",
    ),
    "total_warehouse_area": InputDefinition(
        field_key="total_warehouse_area",
        display_name="总仓库面积",
        input_type="number_with_unit",
        acceptable_units=["sqm", "sqmeters", "平方米", "万sqm", "万平米"],
        required_for_p0=True,
        min_value=100,
        max_value=10_000_000,
        description="请填写所有仓库面积之和（平方米），等同于warehouse_area。",
        unit_conversion_hint="1万平米 = 10,000平方米",
    ),
    "warehouse_area": InputDefinition(
        field_key="warehouse_area",
        display_name="仓库总面积",
        input_type="number_with_unit",
        acceptable_units=["sqm", "sqmeters", "平方米", "万sqm", "万平米"],
        required_for_p0=True,
        min_value=100,
        max_value=10_000_000,
        description="请填写实际测算口径对应的仓储面积（平方米）。",
        unit_conversion_hint="1万平米 = 10,000平方米",
    ),
    "contract_years": InputDefinition(
        field_key="contract_years",
        display_name="合同年限",
        input_type="number",
        acceptable_units=["years", "年"],
        required_for_p0=True,
        min_value=1,
        max_value=20,
        description="请填写正式报价口径下采用的合同年限（含续约选项的锁定年限）。",
    ),
    "dc_count": InputDefinition(
        field_key="dc_count",
        display_name="仓库/ DC 数量",
        input_type="number",
        acceptable_units=[" DCs", "个", "个DC"],
        required_for_p0=True,
        min_value=1,
        max_value=100,
        description="请确认本项目实际覆盖的仓库数量。",
    ),
    "service_scope": InputDefinition(
        field_key="service_scope",
        display_name="服务范围矩阵",
        input_type="service_scope_matrix",  # v0.6.4: structured matrix
        required_for_p0=True,
        description="入库/存储/出库/增值服务/支持服务的结构化矩阵。从Clarification Workspace勾选。",
    ),
    "sku_count": InputDefinition(
        field_key="sku_count",
        display_name="SKU 数量",
        input_type="number",
        acceptable_units=["个", "SKU"],
        required_for_p0=False,
        min_value=1,
        max_value=10_000_000,
        description="请提供投标SKU总数及ABC分类结构。",
    ),
    "inventory": InputDefinition(
        field_key="inventory",
        display_name="平均库存量",
        input_type="number_with_unit",
        acceptable_units=["件", "板", "箱", "units"],
        required_for_p0=False,
        min_value=0,
        description="请提供平均库存量和峰值库存量。",
    ),
    "peak_factor": InputDefinition(
        field_key="peak_factor",
        display_name="峰值系数",
        input_type="number",
        acceptable_units=["x", "倍"],
        required_for_p0=False,
        min_value=1.0,
        max_value=20.0,
        description="旺季峰值量与平时量级的比值，如双11为平时的3倍。",
    ),
    "labor_cost_level": InputDefinition(
        field_key="labor_cost_level",
        display_name="人工成本水平",
        input_type="choice",
        choices=["低", "中", "高"],
        required_for_p0=False,
        description="项目所在地人工成本水平。",
    ),
    "kpi_targets": InputDefinition(
        field_key="kpi_targets",
        display_name="KPI 指标",
        input_type="text",
        required_for_p0=False,
        description="请提供KPI考核指标列表，包含目标值、考核维度和惩罚规则。",
    ),
    "penalty_rules": InputDefinition(
        field_key="penalty_rules",
        display_name="惩罚条款",
        input_type="text",
        required_for_p0=False,
        description="招标文件中的强制条款和否决项清单。",
    ),
    "automation_expectation": InputDefinition(
        field_key="automation_expectation",
        display_name="自动化期望",
        input_type="choice",
        choices=["低", "中", "高"],
        required_for_p0=False,
        description="客户对自动化程度的期望或要求。",
    ),
    "region": InputDefinition(
        field_key="region",
        display_name="项目区域",
        input_type="choice",
        choices=["华东", "华北", "华南", "华中", "西南", "西北", "东北"],
        required_for_p0=False,
        description="项目主要运营区域。",
    ),
    "industry": InputDefinition(
        field_key="industry",
        display_name="行业",
        input_type="choice",
        choices=["电商", "3PL", "零售", "制造", "快递", "医药", "食品", "汽车零部件"],
        required_for_p0=False,
        description="所属行业。",
    ),
}


# =============================================================================
# Validation
# =============================================================================

@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    normalized_value: Any = None
    normalized_unit: Optional[str] = None
    warning: str = ""


def _canonicalize_unit(field_key: str, unit: Optional[str]) -> Optional[str]:
    """Map various unit string representations to canonical form."""
    if unit is None:
        return None
    unit = str(unit).strip()

    canonical_map = {
        "orders/day": "orders/day",
        "日订单量": "orders/day",
        "日": "orders/day",
        "orders/month": "orders/month",
        "月订单量": "orders/month",
        "月": "orders/month",
        "orders/year": "orders/year",
        "年订单量": "orders/year",
        "年": "orders/year",
        "sqm": "sqm",
        "sqmeters": "sqm",
        "平方米": "sqm",
        "万sqm": "万sqm",
        "万平米": "万sqm",
        "years": "years",
        "年": "years",
        " DCs": "DCs",
        "个": "DCs",
        "个DC": "DCs",
        "件": "units",
        "板": "units",
        "箱": "units",
        "units": "units",
        "x": "x",
        "倍": "x",
    }
    return canonical_map.get(unit, unit)


def validate_manual_input(
    field_key: str,
    value: Any,
    unit: Optional[str] = None,
    comment: str = "",
) -> ValidationResult:
    """
    Validate a single manual input.

    Args:
        field_key:  Field identifier
        value:      User-provided value
        unit:       User-provided unit (optional)
        comment:    User-provided comment (optional)

    Returns:
        ValidationResult
    """
    errors = []

    # Check field is defined
    if field_key not in MANUAL_INPUT_DEFINITIONS:
        return ValidationResult(
            valid=False,
            errors=[f"未知字段: {field_key}，不支持人工补录"],
        )

    definition = MANUAL_INPUT_DEFINITIONS[field_key]

    # Check required value
    if value is None or (isinstance(value, str) and not value.strip()):
        errors.append(f"「{definition.display_name}」的值不能为空")
        return ValidationResult(valid=False, errors=errors)

    # Type-specific validation
    norm_unit = _canonicalize_unit(field_key, unit)

    if definition.input_type == "number" or definition.input_type == "number_with_unit":
        try:
            num_value = float(value)
        except (ValueError, TypeError):
            errors.append(f"「{definition.display_name}」的值必须是数字，当前值: {value}")
            return ValidationResult(valid=False, errors=errors)

        # Range check
        if definition.min_value is not None and num_value < definition.min_value:
            errors.append(f"「{definition.display_name}」的值不能小于 {definition.min_value}")
        if definition.max_value is not None and num_value > definition.max_value:
            errors.append(f"「{definition.display_name}」的值不能大于 {definition.max_value}")

        # Unit check
        if definition.input_type == "number_with_unit":
            if norm_unit and definition.acceptable_units:
                # Accept any canonical form — just warn if unusual
                pass

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            normalized_value=num_value,
            normalized_unit=norm_unit,
        )

    elif definition.input_type == "choice":
        if value not in definition.choices:
            errors.append(
                f"「{definition.display_name}」的值必须是以下之一: {', '.join(map(str, definition.choices))}"
            )
            return ValidationResult(valid=False, errors=errors)
        return ValidationResult(
            valid=True,
            normalized_value=value,
            normalized_unit=None,
        )

    elif definition.input_type == "text":
        return ValidationResult(
            valid=True,
            normalized_value=str(value).strip(),
            normalized_unit=None,
        )

    # v0.6.4: service_scope_matrix — structured dict {category: {service: bool}}
    elif definition.input_type == "service_scope_matrix":
        if not isinstance(value, dict):
            return ValidationResult(
                valid=False,
                normalized_value=None,
                normalized_unit=None,
                errors=[f"service_scope 必须为结构化矩阵对象，实际类型: {type(value).__name__}"],
            )
        # Count selected services
        total = sum(sum(v.values()) for v in value.values() if isinstance(v, dict))
        if total == 0:
            return ValidationResult(
                valid=False,
                normalized_value=None,
                normalized_unit=None,
                errors=["请至少选择一项服务"],
            )
        return ValidationResult(
            valid=True,
            normalized_value=value,
            normalized_unit=None,
        )

    return ValidationResult(valid=True, normalized_value=value, normalized_unit=norm_unit)


# =============================================================================
# Batch save
# =============================================================================

def validate_batch(inputs: dict) -> tuple[list[dict], list[dict]]:
    """
    Validate a batch of manual inputs.

    Returns:
        (valid_inputs, validation_errors)
        valid_inputs: list of {field_key, value, unit, comment, updated_at}
        validation_errors: list of {field_key, errors}
    """
    valid_inputs = []
    validation_errors = []

    for field_key, input_data in inputs.items():
        if not isinstance(input_data, dict):
            validation_errors.append({"field_key": field_key, "errors": ["输入格式错误"]})
            continue

        result = validate_manual_input(
            field_key=field_key,
            value=input_data.get("value"),
            unit=input_data.get("unit"),
            comment=input_data.get("comment", ""),
        )

        if result.valid:
            valid_inputs.append({
                "field_key": field_key,
                "value": result.normalized_value,
                "unit": result.normalized_unit,
                "source_type": "manual_input",
                "status": "manual_confirmed",
                "comment": input_data.get("comment", ""),
                "updated_at": datetime.utcnow().isoformat(),
            })
        else:
            validation_errors.append({
                "field_key": field_key,
                "errors": result.errors,
            })

    return valid_inputs, validation_errors


# =============================================================================
# Storage helpers
# =============================================================================

def save_manual_inputs_to_pipeline(
    pipeline_id: str,
    inputs: list[dict],
    db_session,
) -> dict:
    """
    Write validated manual inputs to a PipelineRun record.

    Args:
        pipeline_id:    Pipeline ID (task_id)
        inputs:        Validated input list from validate_batch()
        db_session:    SQLAlchemy session

    Returns:
        {"saved_count": int, "pipeline_id": str}
    """
    from backend.models.database import PipelineRun

    run = db_session.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
    if not run:
        raise ValueError(f"Pipeline run not found: {pipeline_id}")

    # Load existing manual_inputs
    existing = {}
    if run.manual_inputs_json:
        try:
            existing = json.loads(run.manual_inputs_json)
        except (json.JSONDecodeError, TypeError):
            existing = {}

    # Merge new inputs (new values override existing for same field_key)
    for inp in inputs:
        existing[inp["field_key"]] = {
            "value": inp["value"],
            "unit": inp["unit"],
            "source_type": inp["source_type"],
            "status": inp["status"],
            "comment": inp.get("comment", ""),
            "updated_at": inp["updated_at"],
        }

    run.manual_inputs_json = json.dumps(existing, ensure_ascii=False)
    db_session.commit()

    return {"saved_count": len(inputs), "pipeline_id": pipeline_id}


def get_manual_inputs(pipeline_id: str, db_session) -> dict:
    """Read manual_inputs from a PipelineRun record."""
    from backend.models.database import PipelineRun

    run = db_session.query(PipelineRun).filter_by(pipeline_id=pipeline_id).first()
    if not run or not run.manual_inputs_json:
        return {}

    try:
        return json.loads(run.manual_inputs_json)
    except (json.JSONDecodeError, TypeError):
        return {}
