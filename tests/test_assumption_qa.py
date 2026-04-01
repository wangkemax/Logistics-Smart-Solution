"""
tests/test_assumption_qa.py
v0.9 — Test assumption QA rules
"""
import pytest
from backend.services.assumption_qa import validate_assumption_list


class TestAssumptionQA:
    def test_low_confidence_warning(self):
        assumptions = [
            {"field_key": "sku_count", "value": "1000", "confidence": 0.3, "rule": "行业均值"}
        ]
        result = validate_assumption_list(assumptions, "FMCG")
        assert any(i.rule == "low_confidence" for i in result.issues)

    def test_high_confidence_pass(self):
        assumptions = [
            {"field_key": "sku_count", "value": "1000", "confidence": 0.8, "rule": "招标文件"}
        ]
        result = validate_assumption_list(assumptions, "FMCG")
        assert result.passed

    def test_cross_industry_error(self):
        assumptions = [
            {"field_key": "sku_count", "value": "1000", "confidence": 0.6, "rule": "汽车行业均值"}
        ]
        result = validate_assumption_list(assumptions, "FMCG")
        assert any(i.severity == "error" and i.rule == "cross_industry_benchmark" for i in result.issues)

    def test_mutual_exclusion_error(self):
        assumptions = [
            {"field_key": "automation_expectation", "value": "全自动化分拣", "confidence": 0.7, "rule": "高自动化"},
            {"field_key": "labor_cost_level", "value": "低", "confidence": 0.7, "rule": "低成本"},
        ]
        result = validate_assumption_list(assumptions, "MANUFACTURING")
        assert any(i.rule == "mutual_exclusion" and i.severity == "error" for i in result.issues)

    def test_no_issues_when_clean(self):
        assumptions = [
            {"field_key": "sku_count", "value": "5000", "confidence": 0.9, "rule": "招标文件P12"},
            {"field_key": "region", "value": "华东", "confidence": 0.9, "rule": "招标文件P1"},
        ]
        result = validate_assumption_list(assumptions, "FMCG")
        assert result.passed
        assert result.overall_confidence >= 0.9

    def test_multiple_p1_note(self):
        """NOTE: too_many_p1_assumptions rule not yet implemented; expected to fail until Phase 1补充."""
        assumptions = [
            {"field_key": "sku_count", "value": "1000", "confidence": 0.5, "rule": "行业均值"},
            {"field_key": "daily_orders", "value": "500", "confidence": 0.5, "rule": "行业均值"},
            {"field_key": "inventory", "value": "5000", "confidence": 0.5, "rule": "行业均值"},
        ]
        result = validate_assumption_list(assumptions, "FMCG")
        assert any(i.rule == "too_many_p1_assumptions" for i in result.issues)

    def test_same_industry_no_error(self):
        assumptions = [
            {"field_key": "sku_count", "value": "1000", "confidence": 0.6, "rule": "快消行业均值"},
        ]
        result = validate_assumption_list(assumptions, "FMCG")
        # Should NOT trigger cross-industry error since industry matches
        assert not any(i.severity == "error" for i in result.issues)
