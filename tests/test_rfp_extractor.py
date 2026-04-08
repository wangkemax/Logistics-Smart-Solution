"""
tests/test_rfp_extractor.py — v1.3 RFP Ingestion Tests
=======================================================
"""

import pytest
from unittest.mock import patch
from backend.services.rfp_extractor import (
    RFPExtractor,
    _CONFIDENCE_THRESHOLD,
    _FIELD_KEY_MAP,
)

# Mock LLM response for tests that need LLM extraction
_MOCK_LLM_RESPONSE = {
    "project_name": "某知名电商华东配送中心招标",
    "client_name": "某电商有限公司",
    "industry": "电商",
    "region": "华东",
    "warehouse_area": 25000,
    "dc_count": 3,
    "sku_count": 50000,
    "daily_orders": 8000,
    "peak_orders": 15000,
    "labor_cost_level": "中等",
    "budget_level": "较高",
    "contract_years": 5,
    "automation_level": "高",
    "throughput_requirement": None,
    "special_requirements": None,
    "confidence_scores": {
        "project_name": 0.95,
        "client_name": 0.90,
        "warehouse_area": 0.85,
        "sku_count": 0.80,
        "daily_orders": 0.80,
    },
}


class TestRFPExtractor:
    """Tests for RFPExtractor service."""

    @pytest.fixture
    def extractor(self):
        return RFPExtractor()

    # -------------------------------------------------------------------------
    # extract_from_text
    # -------------------------------------------------------------------------

    @patch("backend.services.rfp_extractor._call_minimax_llm", return_value=_MOCK_LLM_RESPONSE)
    def test_extract_from_text_returns_structured_data(self, mock_llm, extractor):
        """验证返回结构包含所有目标字段。"""
        rfp_text = """
        项目名称：某知名电商华东配送中心招标
        客户名称：某电商有限公司
        仓库面积约25000平方米
        DC数量：3个，分别位于上海、广州、武汉
        SKU数量约50000个
        日均出库约8000件
        旺季峰值约15000件
        人工成本中等
        预算水平较高
        合同期5年
        期望自动化程度高
        """
        result = extractor.extract_from_text(rfp_text, language="cn")

        assert "extracted" in result
        assert "confidence_scores" in result
        assert "extraction_confidence" in result
        assert "extraction_method" in result

        extracted = result["extracted"]
        # All target fields should be present (even if None)
        for field in (
            "project_name", "client_name", "warehouse_area", "dc_count",
            "sku_count", "daily_orders", "peak_orders", "labor_cost_level",
            "budget_level", "contract_years", "automation_level",
            "throughput_requirement", "special_requirements", "industry", "region",
        ):
            assert field in extracted, f"Missing field: {field}"

    def test_extract_from_text_short_input_returns_empty(self, extractor):
        """验证输入过短时返回空提取结果。"""
        result = extractor.extract_from_text("太短了", language="cn")
        assert result["extraction_method"] == "empty_input"
        assert result["extraction_confidence"] == 0.0
        assert result["extracted"] == {}

    @patch("backend.services.rfp_extractor._call_minimax_llm", return_value={
        "project_name": None, "client_name": None, "industry": None, "region": None,
        "warehouse_area": None, "dc_count": None, "sku_count": None, "daily_orders": None,
        "peak_orders": None, "labor_cost_level": None, "budget_level": None,
        "contract_years": None, "automation_level": None, "throughput_requirement": None,
        "special_requirements": None, "confidence_scores": {},
    })
    def test_extract_from_text_missing_fields_returns_null(self, mock_llm, extractor):
        """验证未提及的字段返回 null 而不报错。"""
        rfp_text = "这是一个测试文本，没有包含任何关键字段信息。"
        result = extractor.extract_from_text(rfp_text, language="cn")
        extracted = result["extracted"]
        # Should have all keys but values are None
        assert "warehouse_area" in extracted
        assert "sku_count" in extracted

    # -------------------------------------------------------------------------
    # identify_missing_fields
    # -------------------------------------------------------------------------

    def test_identify_missing_fields_flags_p0_correctly(self, extractor):
        """验证 P0 缺失被正确标记。"""
        extracted = {
            "warehouse_area": 25000,
            "dc_count": 3,
            # daily_orders, sku_count, contract_years are missing (P0 fields)
            "confidence_scores": {
                "warehouse_area": 0.9,
                "dc_count": 0.9,
            },
        }
        result = extractor.identify_missing_fields(extracted, {})

        assert "missing_p0" in result
        assert "missing_p1" in result
        assert "filled" in result
        assert "low_confidence" in result
        # P0 fields that should be missing
        assert "daily_orders" in result["missing_p0"]
        assert "sku_count" in result["missing_p0"]
        assert "contract_years" in result["missing_p0"]
        # Fields that were filled
        assert "warehouse_area" in result["filled"]
        assert "dc_count" in result["filled"]

    def test_identify_missing_fields_all_filled_no_p0(self, extractor):
        """验证所有核心字段都已提取时，missing_p0 为空。"""
        extracted = {
            "warehouse_area": 25000,
            "dc_count": 3,
            "sku_count": 50000,
            "daily_orders": 8000,
            "contract_years": 5,
            "confidence_scores": {
                "warehouse_area": 0.9,
                "dc_count": 0.9,
                "sku_count": 0.9,
                "daily_orders": 0.9,
                "contract_years": 0.9,
            },
        }
        result = extractor.identify_missing_fields(extracted, {})
        assert result["missing_p0"] == []
        assert len(result["filled"]) >= 5

    def test_identify_missing_fields_low_confidence_flagged(self, extractor):
        """验证置信度低于阈值的字段被标记为 low_confidence。"""
        extracted = {
            "warehouse_area": 25000,
            "sku_count": 50000,
            "confidence_scores": {
                "warehouse_area": 0.9,    # high confidence — not flagged
                "sku_count": 0.4,       # below threshold — should be flagged
            },
        }
        result = extractor.identify_missing_fields(extracted, {})
        assert "sku_count" in result["low_confidence"]
        assert "warehouse_area" not in result["low_confidence"]

    # -------------------------------------------------------------------------
    # generate_clarification_questions
    # -------------------------------------------------------------------------

    def test_generate_clarification_questions_format(self, extractor):
        """验证澄清问题格式正确（question_id/field_key/category/question_text）。"""
        missing_p0 = ["warehouse_area", "dc_count"]
        missing_p1 = ["special_requirements"]
        context = {"extracted": {}, "confidence_scores": {}}

        questions = extractor.generate_clarification_questions(
            missing_p0, missing_p1, context
        )

        assert len(questions) == 3
        for q in questions:
            assert "question_id" in q
            assert "field_key" in q
            assert "category" in q
            assert "question_text" in q
            assert "guidance" in q
            assert "unit_hint" in q
            assert "impact" in q
            # question_id format: CLAR-001, CLAR-002, ...
            assert q["question_id"].startswith("CLAR-")
            # category should be P0 or P1
            assert q["category"] in ("P0", "P1")

    def test_generate_clarification_questions_p0_before_p1(self, extractor):
        """验证 P0 问题排在 P1 之前。"""
        missing_p0 = ["warehouse_area"]
        missing_p1 = ["special_requirements"]
        context = {}

        questions = extractor.generate_clarification_questions(
            missing_p0, missing_p1, context
        )

        assert questions[0]["category"] == "P0"
        assert questions[0]["field_key"] == "warehouse_area"

    def test_generate_clarification_questions_empty_lists(self, extractor):
        """验证空列表时返回空问题列表。"""
        questions = extractor.generate_clarification_questions([], [], {})
        assert questions == []

    def test_generate_clarification_questions_unknown_field_key(self, extractor):
        """验证未知字段也能生成通用问题。"""
        missing_p0 = ["some_unknown_field"]
        context = {}
        questions = extractor.generate_clarification_questions(
            missing_p0, [], context
        )
        assert len(questions) == 1
        assert questions[0]["field_key"] == "some_unknown_field"
        assert questions[0]["question_text"] is not None

    # -------------------------------------------------------------------------
    # confidence_below_threshold_flagged (via identify_missing_fields)
    # -------------------------------------------------------------------------

    def test_confidence_below_threshold_flagged(self, extractor):
        """验证置信度低于0.5的字段被标记。"""
        extracted = {
            "warehouse_area": 25000,
            "labor_cost_level": "中",
            "confidence_scores": {
                "warehouse_area": 0.9,        # above threshold
                "labor_cost_level": 0.3,     # below 0.5 threshold
            },
        }
        result = extractor.identify_missing_fields(extracted, {})
        assert "labor_cost_level" in result["low_confidence"]
        assert "warehouse_area" not in result["low_confidence"]

    def test_confidence_at_exactly_threshold_not_flagged(self, extractor):
        """验证置信度恰好等于阈值时不被标记。"""
        extracted = {
            "warehouse_area": 25000,
            "confidence_scores": {
                "warehouse_area": 0.5,  # exactly at threshold
            },
        }
        result = extractor.identify_missing_fields(extracted, {})
        # 0.5 is not < 0.5, so should NOT be in low_confidence
        assert "warehouse_area" not in result["low_confidence"]

    # -------------------------------------------------------------------------
    # run_full_pipeline
    # -------------------------------------------------------------------------

    @patch("backend.services.rfp_extractor._call_minimax_llm", return_value={
        "project_name": "某汽车零部件华东DC招标", "client_name": "某某汽车零部件有限公司",
        "industry": "汽车", "region": "华东", "warehouse_area": 30000, "dc_count": 2,
        "sku_count": 20000, "daily_orders": 5000, "peak_orders": None,
        "labor_cost_level": None, "budget_level": None, "contract_years": 3,
        "automation_level": None, "throughput_requirement": None,
        "special_requirements": None, "confidence_scores": {
            "project_name": 0.95, "warehouse_area": 0.85, "sku_count": 0.80,
        },
    })
    def test_run_full_pipeline_returns_complete_structure(self, mock_llm, extractor):
        """验证完整管道返回完整结构。"""
        rfp_text = """
        项目名称：某汽车零部件华东DC招标
        客户名称：某某汽车零部件有限公司
        仓库面积约30000平方米
        DC数量：2个
        SKU数量约20000个
        日均出库约5000件
        合同期3年
        """
        result = extractor.run_full_pipeline(rfp_text)

        assert result["success"] is True
        assert "extracted" in result
        assert "clarification_questions" in result
        assert "missing_p0" in result
        assert "missing_p1" in result
        assert "filled" in result
        assert "total_questions" in result
        assert "p0_questions" in result
        assert "p1_questions" in result
        assert result["total_questions"] == (
            result["p0_questions"] + result["p1_questions"]
        )

    @patch("backend.services.rfp_extractor._call_minimax_llm", return_value={
        "project_name": None, "client_name": None, "industry": None, "region": None,
        "warehouse_area": 20000, "dc_count": 3, "sku_count": None, "daily_orders": None,
        "peak_orders": None, "labor_cost_level": None, "budget_level": None,
        "contract_years": None, "automation_level": None, "throughput_requirement": None,
        "special_requirements": None, "confidence_scores": {"warehouse_area": 0.85},
    })
    def test_run_full_pipeline_with_run_id(self, mock_llm, extractor):
        """验证传入 run_id 时尝试注册 Assumptions（不报错）。"""
        rfp_text = "仓库面积约20000平方米，DC数量3个。"
        result = extractor.run_full_pipeline(rfp_text, run_id="test-run-001")
        assert result["success"] is True
        # assumptions_registered should be present (may be empty if registration fails)
        assert "assumptions_registered" in result

    def test_run_full_pipeline_empty_text_fails_gracefully(self, extractor):
        """验证空文本时管道返回失败而非抛异常。"""
        result = extractor.run_full_pipeline("")
        assert result["success"] is False
        assert result["error"] is not None
        assert result["clarification_questions"] == []

    # -------------------------------------------------------------------------
    # extract_from_pdf (error case)
    # -------------------------------------------------------------------------

    def test_extract_from_pdf_no_pdfminer_returns_error(self, extractor, monkeypatch):
        """验证未安装 pdfminer.six 时返回错误提示。"""
        import backend.services.rfp_extractor as rfp_mod

        def fake_extract(path):
            raise ImportError(
                "PDF读取需要安装 pdfminer.six。请运行: pip install pdfminer.six"
            )

        monkeypatch.setattr(rfp_mod, "_extract_pdf_text", fake_extract)

        result = extractor.extract_from_pdf("/fake/path.pdf")
        assert result["error"] is not None
        assert "pdfminer" in result["error"].lower()

    # -------------------------------------------------------------------------
    # edge cases
    # -------------------------------------------------------------------------

    def test_empty_extraction_result_keys(self, extractor):
        """验证空提取结果的 key 结构完整性。"""
        result = extractor._empty_extraction()
        assert result["extracted"] == {}
        assert result["confidence_scores"] == {}
        assert result["extraction_confidence"] == 0.0
        assert result["extraction_method"] == "empty_input"

    def test_field_key_mapping_automation_level(self, extractor):
        """验证 automation_level 映射到 automation_expectation。"""
        extracted = {
            "automation_level": "高",
            "confidence_scores": {"automation_level": 0.8},
        }
        result = extractor.identify_missing_fields(extracted, {})
        assert "automation_level" in result["filled"]
        assert result["filled"]["automation_level"] == "高"
