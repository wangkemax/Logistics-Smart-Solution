"""tests/test_workspace_diff.py — v1.4 Bid Scenario Diffing Tests"""
from __future__ import annotations

import pytest

from backend.services.workspace_diff_service import WorkspaceDiffService


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def diff_service() -> WorkspaceDiffService:
    return WorkspaceDiffService()


@pytest.fixture
def context_a() -> dict:
    return {
        "workspace_id": "ws-aaaa-bbbb",
        "pipeline_id": "pipe-001",
        "project_name": "华道汽车 JIT 项目",
        "industry": "AUTOMOTIVE",
        "region": "华东",
        "operation_type": "JIT",
        "complexity_level": "high",
        "complexity_score": 85,
        "warehouse_area": 25000,
        "daily_orders": 5000,
        "headcount_reduction": 15,
        "contract_years": 3,
        "cost_mode": "full",
        "roi_summary": {
            "roi_5y": 86.5,
            "payback_years": 2.8,
            "capex_total": 500.0,
            "irr": 32.1,
            "npv": 850.0,
            "net_annual_benefit": 180.0,
        },
        "active_assumptions": [
            {"field_key": "warehouse_area", "value": 25000},
        ],
    }


@pytest.fixture
def context_b() -> dict:
    return {
        "workspace_id": "ws-cccc-dddd",
        "pipeline_id": "pipe-001",
        "project_name": "华道汽车 JIT 项目",
        "industry": "AUTOMOTIVE",
        "region": "华东",
        "operation_type": "JIT",
        "complexity_level": "high",
        "complexity_score": 90,
        "warehouse_area": 30000,  # 变化：+5000 (+20%)
        "daily_orders": 5000,       # 无变化
        "headcount_reduction": 20,  # 变化：+5
        "contract_years": 5,        # 变化
        "cost_mode": "full",
        "roi_summary": {
            "roi_5y": 72.0,         # 变化：-14.5pp
            "payback_years": 3.5,   # 变化：+0.7年
            "capex_total": 620.0,   # 变化：+120 (+24%)
            "irr": 28.0,            # 变化：-4.1pp
            "npv": 920.0,           # 变化：+70
            "net_annual_benefit": 210.0,
        },
        "active_assumptions": [
            {"field_key": "warehouse_area", "value": 30000},
        ],
    }


# ─── Tests: diff_context_json ───────────────────────────────────────────────

def test_diff_context_json_detects_changes(diff_service, context_a, context_b):
    """验证 context 差异被正确检测"""
    diffs = diff_service.diff_context_json(context_a, context_b)

    assert isinstance(diffs, list)
    # 预期变化的字段：warehouse_area, headcount_reduction, contract_years, complexity_score, roi_summary.*
    changed_fields = {d["field"] for d in diffs}
    assert "warehouse_area" in changed_fields
    assert "headcount_reduction" in changed_fields
    assert "contract_years" in changed_fields
    assert "complexity_score" in changed_fields


def test_diff_context_json_unchanged_fields_omitted(diff_service, context_a, context_b):
    """验证未变化的字段不出现在 diffs 中"""
    diffs = diff_service.diff_context_json(context_a, context_b)
    changed_fields = {d["field"] for d in diffs}

    # 未变化字段
    assert "operation_type" not in changed_fields
    assert "region" not in changed_fields
    assert "industry" not in changed_fields
    assert "pipeline_id" not in changed_fields
    assert "cost_mode" not in changed_fields
    assert "project_name" not in changed_fields


def test_diff_numeric_fields_show_percentage(diff_service, context_a, context_b):
    """验证数值字段显示百分比变化"""
    diffs = diff_service.diff_context_json(context_a, context_b)

    # 找到 warehouse_area 的 diff
    warehouse_diff = next((d for d in diffs if d["field"] == "warehouse_area"), None)
    assert warehouse_diff is not None
    assert "diff" in warehouse_diff
    # 变化量 +5000，百分比 (5000/25000)*100 = 20%
    assert "+5000" in warehouse_diff["diff"] or "20%" in warehouse_diff["diff"]
    assert warehouse_diff["delta"] == 5000.0
    assert warehouse_diff["pct_change"] == 20.0


def test_diff_headcount_reduction_numeric(diff_service, context_a, context_b):
    """验证 headcount_reduction 变化被检测"""
    diffs = diff_service.diff_context_json(context_a, context_b)
    hc_diff = next((d for d in diffs if d["field"] == "headcount_reduction"), None)

    assert hc_diff is not None
    assert hc_diff["value_a"] == 15
    assert hc_diff["value_b"] == 20
    assert hc_diff["delta"] == 5.0


def test_diff_contract_years(diff_service, context_a, context_b):
    """验证合同年限变化"""
    diffs = diff_service.diff_context_json(context_a, context_b)
    cy_diff = next((d for d in diffs if d["field"] == "contract_years"), None)

    assert cy_diff is not None
    assert cy_diff["value_a"] == 3
    assert cy_diff["value_b"] == 5
    assert cy_diff["delta"] == 2.0


def test_diff_context_json_identical_contexts(diff_service, context_a):
    """验证完全相同的两个 context 返回空 diffs"""
    diffs = diff_service.diff_context_json(context_a, context_a.copy())
    assert diffs == []


def test_diff_context_json_extra_field_in_b(diff_service, context_a):
    """验证 context_b 多出的字段被识别为新增"""
    ctx_a = {"field_a": 1, "field_b": 2}
    ctx_b = {"field_a": 1, "field_b": 2, "field_c": 3}

    diffs = diff_service.diff_context_json(ctx_a, ctx_b)
    field_c_diff = next((d for d in diffs if d["field"] == "field_c"), None)

    assert field_c_diff is not None
    assert field_c_diff["value_a"] is None
    assert field_c_diff["value_b"] == 3


def test_diff_context_json_missing_field_in_b(diff_service, context_a):
    """验证 context_a 有但 context_b 没有的字段"""
    ctx_a = {"field_a": 1, "field_b": 2}
    ctx_b = {"field_a": 1}

    diffs = diff_service.diff_context_json(ctx_a, ctx_b)
    field_b_diff = next((d for d in diffs if d["field"] == "field_b"), None)

    assert field_b_diff is not None
    assert field_b_diff["value_a"] == 2
    assert field_b_diff["value_b"] is None


def test_diff_context_json_skips_nested_objects(diff_service, context_a, context_b):
    """验证嵌套对象（active_assumptions / roi_summary）不出现在 param_diffs"""
    diffs = diff_service.diff_context_json(context_a, context_b)
    fields = {d["field"] for d in diffs}

    # roi_summary 作为整体不应出现在 param_diffs（它有自己的 cost_diffs 逻辑）
    assert "roi_summary" not in fields
    assert "active_assumptions" not in fields


def test_diff_context_json_boolean_not_treated_as_numeric(diff_service):
    """验证 bool 值不被当作数值处理"""
    ctx_a = {"enabled": True, "count": 10}
    ctx_b = {"enabled": False, "count": 10}

    diffs = diff_service.diff_context_json(ctx_a, ctx_b)
    enabled_diff = next((d for d in diffs if d["field"] == "enabled"), None)

    assert enabled_diff is not None
    # bool 不应被当作数值
    assert "delta" not in enabled_diff
    assert "pct_change" not in enabled_diff


# ─── Tests: _diff_financial ───────────────────────────────────────────────────

def test_diff_financial_roi_5y_pp(diff_service, context_a, context_b):
    """验证 ROI 用 pp（百分点）单位"""
    cost_diffs = diff_service._diff_financial(context_a, context_b)

    assert "roi_5y" in cost_diffs
    roi_diff = cost_diffs["roi_5y"]
    assert roi_diff["a"] == 86.5
    assert roi_diff["b"] == 72.0
    assert "pp" in roi_diff["diff"] or "-14.5" in roi_diff["diff"]


def test_diff_financial_payback_years(diff_service, context_a, context_b):
    """验证 payback_years 用年为单位"""
    cost_diffs = diff_service._diff_financial(context_a, context_b)

    assert "payback_years" in cost_diffs
    pb_diff = cost_diffs["payback_years"]
    assert pb_diff["a"] == 2.8
    assert pb_diff["b"] == 3.5
    assert "年" in pb_diff["diff"]


def test_diff_financial_capex_total(diff_service, context_a, context_b):
    """验证 capex_total 金额变化带万元和百分比"""
    cost_diffs = diff_service._diff_financial(context_a, context_b)

    assert "capex_total" in cost_diffs
    capex_diff = cost_diffs["capex_total"]
    assert capex_diff["a"] == 500.0
    assert capex_diff["b"] == 620.0
    assert "万元" in capex_diff["diff"] or "120" in capex_diff["diff"]


def test_diff_financial_irr_pp(diff_service, context_a, context_b):
    """验证 IRR 用 pp 单位"""
    cost_diffs = diff_service._diff_financial(context_a, context_b)

    assert "irr" in cost_diffs
    irr_diff = cost_diffs["irr"]
    assert irr_diff["a"] == 32.1
    assert irr_diff["b"] == 28.0
    assert "pp" in irr_diff["diff"] or "-4.1" in irr_diff["diff"]


# ─── Tests: _generate_analysis ───────────────────────────────────────────────

def test_generate_analysis_key_changes(diff_service, context_a, context_b):
    """验证分析文本包含关键变化"""
    param_diffs = diff_service.diff_context_json(context_a, context_b)
    cost_diffs = diff_service._diff_financial(context_a, context_b)

    # mock workspace objects (minimal)
    class MockWorkspace:
        workspace_id = "ws-aaaa"
        snapshot_version = 1
        created_at = None
        project_name = "测试"
        industry = "TEST"

    analysis = diff_service._generate_analysis(param_diffs, cost_diffs, MockWorkspace(), MockWorkspace())

    assert isinstance(analysis, str)
    assert "方案 A" in analysis or "差异" in analysis or "diff" in analysis.lower()
    assert "主要变化" in analysis or "财务影响" in analysis or "参数差异" in analysis


# ─── Tests: format helpers ────────────────────────────────────────────────────

def test_fmt_sign_positive(diff_service):
    assert diff_service._fmt_sign(5.0) == "+5.00"
    assert diff_service._fmt_sign(1.0) == "+1.00"


def test_fmt_sign_negative(diff_service):
    assert diff_service._fmt_sign(-3.5) == "-3.50"


def test_fmt_sign_zero(diff_service):
    assert diff_service._fmt_sign(0) == "+0.00"


def test_summarize_diff_new_field(diff_service):
    result = diff_service._summarize_diff(None, "new_value")
    assert "新增" in result or "new_value" in result


def test_summarize_diff_removed_field(diff_service):
    result = diff_service._summarize_diff("old_value", None)
    assert "移除" in result or "old_value" in result


def test_summarize_diff_changed_field(diff_service):
    result = diff_service._summarize_diff("A", "B")
    assert "A → B" in result


def test_is_numeric(diff_service):
    assert diff_service._is_numeric(42) is True
    assert diff_service._is_numeric(3.14) is True
    assert diff_service._is_numeric(-1.5) is True
    assert diff_service._is_numeric(True) is False  # bool 不是 numeric
    assert diff_service._is_numeric("42") is False
    assert diff_service._is_numeric(None) is False
