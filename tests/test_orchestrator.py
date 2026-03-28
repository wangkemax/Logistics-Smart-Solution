"""
Tests for the pipeline orchestrator (CEO Agent).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.orchestrator import extract_requirements


SAMPLE_TENDER = """
招标文件摘要：

客户名称：某某电商有限公司
项目名称：华东地区自动化仓储项目
行业类型：电商
仓库面积：25000平方米
日均订单量：8000单/天
SKU数量：50000
库存量：1000000
预算：中等预算，希望控制在500万以内
合同期限：3+2年
预计上线：2026年8月1日
"""

PARTIAL_TENDER = """
某制造企业仓库运营外包招标：
仓库面积约15000平米，SKU数量约20000，日均订单约3000单。
"""


class TestExtractRequirements:
    def test_extract_full_tender(self):
        profile, missing = extract_requirements(SAMPLE_TENDER)
        assert profile["industry"] == "电商"
        assert profile["warehouse_area"] == 25000
        assert profile["daily_orders"] == 8000
        assert profile["sku_count"] == 50000
        assert profile["inventory"] == 1000000
        assert profile["region"] == "华东"
        assert missing == []  # All key fields found

    def test_extract_partial_tender(self):
        profile, missing = extract_requirements(PARTIAL_TENDER)
        assert profile["industry"] == "制造"
        assert profile["warehouse_area"] == 15000
        assert profile["daily_orders"] == 3000
        assert profile["sku_count"] == 20000
        assert "warehouse_area" not in missing
        assert "daily_orders" not in missing

    def test_extract_defaults_for_missing_fields(self):
        profile, missing = extract_requirements("这是一段没有任何数值的文本")
        assert profile["industry"] == "电商"  # default
        assert profile["region"] == "华东"     # default
        assert profile["labor_cost_level"] == "中"
        assert profile["budget_level"] == "中"
        assert "warehouse_area" in missing
        assert "sku_count" in missing
        assert "daily_orders" in missing

    def test_extract_contract_years(self):
        tender_with_years = "合同期限5年，3+2结构"
        profile, _ = extract_requirements(tender_with_years)
        assert profile["contract_years"] == 5

    def test_extract_region_shanghai(self):
        tender_sh = "上海仓库自动化项目，5000平米"
        profile, _ = extract_requirements(tender_sh)
        assert profile["region"] == "华东"

    def test_budget_detection(self):
        tender_budget = "项目预算有限，约100万元，请报方案"
        profile, _ = extract_requirements(tender_budget)
        assert profile["budget_level"] == "低"

    def test_sku_and_orders_from_text(self):
        tender = "SKU数量30000，日均订单量5000单，库存量800000件"
        profile, _ = extract_requirements(tender)
        assert profile["sku_count"] == 30000
        assert profile["daily_orders"] == 5000
        assert profile["inventory"] == 800000

    def test_no_false_positives(self):
        """Don't extract phone numbers or small numbers as warehouse area."""
        tender = "报价有效期30天，请于联系020-12345678"
        profile, _ = extract_requirements(tender)
        # Should not extract phone numbers or day counts as area
        assert profile["warehouse_area"] is None
        assert profile["daily_orders"] is None
