"""
tests/test_parameter_service.py
v0.9 — Test parameter service CSV matching
"""
import pytest
from backend.services.parameter_service import (
    get_assumption_defaults,
    get_all_defaults_for_project,
    _match_score,
    PRIORITY_WEIGHT,
)


class TestParameterService:
    def test_exact_industry_region_match(self):
        result = get_assumption_defaults("sku_count", "FMCG", "华东")
        assert result is not None
        assert "15" in result.value  # FMCG 华东用 ÷15

    def test_industry_fallback_region(self):
        result = get_assumption_defaults("sku_count", "FMCG", "乌鲁木齐")
        # Should fall back to FMCG/*
        assert result is not None
        assert "15" in result.value

    def test_global_fallback(self):
        result = get_assumption_defaults("budget_level", "UNKNOWN", "UNKNOWN")
        assert result is not None
        assert "5-8%" in result.value  # Global default

    def test_automotive_sku_count(self):
        result = get_assumption_defaults("sku_count", "AUTOMOTIVE", "华东")
        assert result is not None
        assert "3" in result.value  # ÷3 for automotive

    def test_missing_field_returns_none(self):
        result = get_assumption_defaults("nonexistent_field", "FMCG", "华东")
        assert result is None

    def test_all_defaults_for_project(self):
        results = get_all_defaults_for_project("FMCG", "华东", ["sku_count", "inventory", "peak_factor"])
        field_keys = [r.field_key for r in results]
        assert "sku_count" in field_keys
        assert "inventory" in field_keys
        assert "peak_factor" in field_keys

    def test_match_score_priority(self):
        # Perfect match gets highest score
        perfect = _match_score({"industry": "FMCG", "region": "华东"}, "FMCG", "华东")
        industry_only = _match_score({"industry": "FMCG", "region": "*"}, "FMCG", "华东")
        assert perfect == PRIORITY_WEIGHT["industry_region"]
        assert industry_only == PRIORITY_WEIGHT["industry_default"]
        assert perfect > industry_only
