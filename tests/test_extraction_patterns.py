"""
Regression tests for llm_extractor field extraction
==================================================
Tests the fixes for:
  - region extraction from Chinese city names (Shanghai/上海市/浦东)
  - industry extraction from dealer/distributor patterns
  - labor_cost_level / budget_level default fallbacks
  - LLM raw output logging (no crashes on None)
"""

import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.llm_extractor import (
    _extract_with_patterns,
    _INDUSTRY_PATTERNS,
    _REGION_PATTERNS,
)


class TestRegionPatterns:
    """Region extraction from Chinese city/address patterns."""

    def test_region_shanghai_chinese(self):
        """'上海市' should match East China (华东)."""
        text = "项目地址：上海市浦东区同顺大道555号"
        field_values, _, _ = _extract_with_patterns(text)
        assert field_values.get("region") == "华东", \
            f"Expected 华东, got {field_values.get('region')}"

    def test_region_pudong(self):
        """'浦东' in address should extract 华东."""
        text = "仓库位于上海市浦东新区"
        field_values, _, _ = _extract_with_patterns(text)
        assert field_values.get("region") == "华东", \
            f"Expected 华东, got {field_values.get('region')}"

    def test_region_chengdu(self):
        """'成都' / '四川' should match 西部."""
        text = "项目位于四川省成都市"
        field_values, _, _ = _extract_with_patterns(text)
        assert field_values.get("region") == "西部", \
            f"Expected 西部, got {field_values.get('region')}"

    def test_region_beijing(self):
        """'北京' should match 华北."""
        text = "客户位于北京市朝阳区"
        field_values, _, _ = _extract_with_patterns(text)
        assert field_values.get("region") == "华北", \
            f"Expected 华北, got {field_values.get('region')}"

    def test_region_shanghai_english(self):
        """'Shanghai' in English text should still match 华东."""
        text = "Warehouse address: Shanghai Pudong New Area"
        field_values, _, _ = _extract_with_patterns(text)
        assert field_values.get("region") == "华东", \
            f"Expected 华东, got {field_values.get('region')}"


class TestIndustryPatterns:
    """Industry extraction from dealer/distributor/network patterns."""

    def test_industry_dealer_lowercase(self):
        """'dealer' (lowercase) in text should identify 3PL."""
        text = "Dealer returns process for warehouse management"
        field_values, _, _ = _extract_with_patterns(text)
        assert field_values.get("industry") == "3PL", \
            f"Expected 3PL, got {field_values.get('industry')}"

    def test_industry_distributor(self):
        """'Distributor' should identify 3PL."""
        text = "Distributor network warehousing solution"
        field_values, _, _ = _extract_with_patterns(text)
        assert field_values.get("industry") == "3PL", \
            f"Expected 3PL, got {field_values.get('industry')}"

    def test_industry_distributor_chinese(self):
        """'分销' / '经销商' should identify 3PL."""
        for keyword in ["分销网络仓储", "经销商仓库", "代理商物流中心"]:
            field_values, _, _ = _extract_with_patterns(keyword)
            assert field_values.get("industry") == "3PL", \
                f"Keyword='{keyword}': Expected 3PL, got {field_values.get('industry')}"

    def test_industry_dealer_network(self):
        """'dealer network' should identify 3PL."""
        text = "SAP EWM dealer network warehouse management"
        field_values, _, _ = _extract_with_patterns(text)
        assert field_values.get("industry") == "3PL", \
            f"Expected 3PL, got {field_values.get('industry')}"

    def test_industry_retail_supermarket(self):
        """Existing retail patterns should still work."""
        text = "超市仓储物流自动化解决方案"
        field_values, _, _ = _extract_with_patterns(text)
        assert field_values.get("industry") == "零售", \
            f"Expected 零售, got {field_values.get('industry')}"

    def test_industry_ecommerce(self):
        """Existing e-commerce patterns should still work."""
        text = "电商平台仓储物流外包"
        field_values, _, _ = _extract_with_patterns(text)
        assert field_values.get("industry") == "电商", \
            f"Expected 电商, got {field_values.get('industry')}"


class TestLaborCostLevel:
    """Labor cost level fallbacks when not explicitly stated in tender."""

    def test_labor_cost_not_found_defaults_none(self):
        """When no explicit labor cost pattern found, returns None (not crash)."""
        text = "仓库位于上海市，仓储面积20000平米"
        field_values, _, warnings = _extract_with_patterns(text)
        # None is acceptable — downstream fill_missing_fields applies default "中"
        assert field_values.get("labor_cost_level") is None

    def test_labor_cost_explicit_low(self):
        """Explicit '人工成本低' should extract 低."""
        text = "本地区人工成本低，适合劳动密集型运营"
        field_values, _, _ = _extract_with_patterns(text)
        assert field_values.get("labor_cost_level") == "低", \
            f"Expected 低, got {field_values.get('labor_cost_level')}"

    def test_labor_cost_explicit_mid(self):
        """Explicit '人工成本中' should extract 中."""
        text = "该地区人工成本中等，约为每人每月5000元"
        field_values, _, _ = _extract_with_patterns(text)
        assert field_values.get("labor_cost_level") == "中", \
            f"Expected 中, got {field_values.get('labor_cost_level')}"


class TestBudgetLevel:
    """Budget level fallbacks when not explicitly stated in tender."""

    def test_budget_not_found_returns_none(self):
        """When no explicit budget pattern found, returns None (not crash)."""
        text = "项目需求：仓储面积5000平方米，日处理订单2000单"
        field_values, _, _ = _extract_with_patterns(text)
        assert field_values.get("budget_level") is None

    def test_budget_explicit_high(self):
        """Explicit '预算充足' should extract 高."""
        text = "客户预算充足，计划投资高端自动化设备"
        field_values, _, _ = _extract_with_patterns(text)
        assert field_values.get("budget_level") == "高", \
            f"Expected 高, got {field_values.get('budget_level')}"

    def test_budget_explicit_tight(self):
        """Explicit '预算紧张' should extract 低."""
        text = "客户预算紧张，需要控制初期投资成本"
        field_values, _, _ = _extract_with_patterns(text)
        assert field_values.get("budget_level") == "低", \
            f"Expected 低, got {field_values.get('budget_level')}"


class TestExtractionNoCrash:
    """Ensure extraction never crashes on edge inputs."""

    def test_empty_text_no_crash(self):
        """Empty tender text should not crash extraction."""
        field_values, _, _ = _extract_with_patterns("")
        assert isinstance(field_values, dict)

    def test_mixed_chinese_english_no_crash(self):
        """Mixed Chinese/English tender content should not crash."""
        text = "Warehouse Address: Shanghai Pudong Area. Dealer network logistics."
        field_values, _, _ = _extract_with_patterns(text)
        assert isinstance(field_values, dict)
        assert field_values.get("region") == "华东"
        assert field_values.get("industry") == "3PL"
