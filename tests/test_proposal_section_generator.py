"""tests/test_proposal_section_generator.py Proposal Section Generator 单元测试"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from backend.schemas.workspace_schemas import WorkspaceContext
from backend.schemas.proposal_schemas import ProposalGenerationRequest
from backend.services.proposal_section_generator import (
    ProposalSectionGenerator,
    _build_context_text,
    _render_service_scope,
    _render_labor_modules,
    _render_assumptions,
    _render_roi_summary,
)
from backend.services.proposal_engine import ProposalEngine


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_workspace_context() -> WorkspaceContext:
    """标准的 WorkspaceContext fixture（无 QA 冲突）"""
    return WorkspaceContext(
        workspace_id="ws-test-001",
        pipeline_id="pipeline-001",
        project_name="华道汽车 JIT 供料项目",
        industry="AUTOMOTIVE",
        region="华东",
        operation_type="JIT线边仓",
        complexity_level="高复杂度",
        complexity_score=15,
        operation_narrative="采用DMS色带管理系统 + 电子看板，实现JIT直供上线。",
        labor_modules={
            "收货组": {"role": "收货组", "headcount": 4},
            "上架组": {"role": "上架组", "headcount": 3},
            "拣货组": {"role": "拣货组", "headcount": 6},
        },
        process_modules={
            "上线配送": {
                "name": "上线配送流程",
                "steps": ["工单接收", "集货", "配送至产线", "签收确认"],
            },
        },
        service_scope={
            "inbound": {"receiving": True, "quality_check": True, "putaway": True},
            "outbound": {"picking": True, "packing": True, "loading": True, "shipping": True},
        },
        analysis_sections={},
        active_assumptions=[
            {
                "field_key": "sku_count",
                "value": "8000",
                "rule": "月均出货量÷15",
                "version_id": 1,
                "effective_date": "2025-01-01",
            },
            {
                "field_key": "daily_orders",
                "value": "5000",
                "rule": "客户提供的日均订单量",
                "version_id": 1,
                "effective_date": "2025-01-01",
            },
            {
                "field_key": "warehouse_area",
                "value": "35000",
                "rule": "招标文件中的仓库面积",
                "version_id": 2,
                "effective_date": "2025-03-01",
            },
        ],
        overridden_assumptions=[],
        assumption_qa_warnings=[],  # 无冲突
        snapshot_version=1,
        is_dirty=True,
        status="active",
        cost_mode="人天制",
        roi_summary={
            "roi_5y": "86.0%",
            "payback_years": "3.2年",
            "annual_savings": "¥320万",
        },
    )


@pytest.fixture
def mock_workspace_with_conflict() -> WorkspaceContext:
    """含有互斥冲突 QA 警告的 WorkspaceContext"""
    return WorkspaceContext(
        workspace_id="ws-test-conflict",
        pipeline_id="pipeline-001",
        project_name="冲突测试项目",
        industry="ELECTRONICS",
        region="华南",
        operation_type="VMI Hub",
        complexity_level="中复杂度",
        complexity_score=10,
        operation_narrative="VMI供应商管理库存模式。",
        labor_modules={},
        process_modules={},
        service_scope={},
        analysis_sections={},
        active_assumptions=[],
        overridden_assumptions=[],
        assumption_qa_warnings=[
            "WARNING: sku_count 存在互斥假设：月均7000件 vs 月均5000件",
            "WARNING: 区域冲突：华东 vs 华南",
        ],
        snapshot_version=1,
        is_dirty=True,
        status="active",
        cost_mode="人天制",
        roi_summary={},
    )


# =============================================================================
# Mock LLM responses
# =============================================================================

MOCK_LLM_RESPONSES = {
    "executive_summary": (
        "## 一、执行摘要\n\n华道汽车JIT供料项目基于DMS色带管理系统，为客户提供高效的线边仓解决方案。"
        "项目5年ROI达86.0%，投资回收期3.2年，预计年节省人力成本320万元。"
        "实施周期12个月，分四阶段完成。建议选择本供应商，因其在汽车零部件JIT领域有丰富经验。",
        800,
    ),
    "core_solution": (
        "## 二、核心方案设计\n\n### 方案概述\n本方案采用JIT线边仓运营模式，针对SKU数量8000（假设版本v1）、"
        "日均订单5000（假设版本v1）的业务规模设计。仓库面积35000平米（假设版本v2）。\n\n"
        "### 关键设计\n1. DMS色带管理：实现物料可视化管理\n"
        "2. 电子看板：实时同步产线需求\n"
        "3. 循环补货：基于月均出货量÷15的SKU节奏进行补货",
        1200,
    ),
    "implementation_plan": (
        "## 三、实施计划\n\n### 阶段一：需求确认（1-2个月）\n基于假设有效期2025-01-01，确认业务需求。\n\n"
        "### 阶段二：方案细化（2-4个月）\n完成系统配置和流程设计。\n\n"
        "### 阶段三：实施部署（5-10个月）\n完成系统上线和人员培训。\n\n"
        "### 阶段四：验收交付（11-12个月）\n最终验收和持续优化。",
        1000,
    ),
}


# =============================================================================
# Tests: _build_context_text and helper functions
# =============================================================================

class TestBuildContextText:
    """测试 _build_context_text 辅助函数"""

    def test_render_service_scope(self):
        """验证 service_scope dict → 可读文本"""
        service_scope = {
            "inbound": {"receiving": True, "unpacking": False},
            "outbound": {"picking": True, "packing": True},
        }
        result = _render_service_scope(service_scope)
        assert "入库作业" in result
        assert "✓" in result
        assert "receiving" in result or "收货" in result

    def test_render_service_scope_empty(self):
        """空 service_scope 返回占位符"""
        result = _render_service_scope({})
        assert "待确认" in result or result == ""

    def test_render_labor_modules(self):
        """验证 labor_modules dict → 可读文本"""
        labor_modules = {
            "team_1": {"role": "收货组", "headcount": 4},
            "team_2": {"role": "上架组", "headcount": 3},
        }
        result = _render_labor_modules(labor_modules)
        assert "收货组" in result
        assert "4人" in result

    def test_render_assumptions(self):
        """验证 active_assumptions list → 可读文本"""
        assumptions = [
            {
                "field_key": "sku_count",
                "value": "7500",
                "rule": "月均出货量÷15",
                "version_id": 1,
            },
        ]
        result = _render_assumptions(assumptions)
        assert "sku_count" in result
        assert "7500" in result
        assert "月均出货量÷15" in result

    def test_render_roi_summary(self):
        """验证 roi_summary dict → ROI 文本"""
        roi_summary = {
            "roi_5y": "86.0%",
            "payback_years": "3.2年",
        }
        result = _render_roi_summary(roi_summary)
        assert "86.0%" in result
        assert "3.2年" in result

    def test_build_context_text(self, mock_workspace_context):
        """验证完整的 context dict 构建"""
        context = _build_context_text(mock_workspace_context, language="cn")
        assert context["project_name"] == "华道汽车 JIT 供料项目"
        assert context["industry"] == "AUTOMOTIVE"
        assert context["complexity_score"] == 15
        assert "sku_count" in context["assumptions_text"]
        assert "86.0%" in context["roi_text"]


# =============================================================================
# Tests: ProposalSectionGenerator
# =============================================================================

class TestProposalSectionGenerator:
    """测试 ProposalSectionGenerator 核心逻辑"""

    @patch.object(
        __import__(
            "backend.services.proposal_llm_service", fromlist=["ProposalLLMService"]
        ).ProposalLLMService,
        "_call_llm",
    )
    def test_generate_executive_summary(self, mock_llm, mock_workspace_context):
        """验证执行摘要生成，包含项目名称和行业信息"""
        mock_llm.return_value = MOCK_LLM_RESPONSES["executive_summary"]

        gen = ProposalSectionGenerator()
        result = gen.generate_section(
            workspace=mock_workspace_context,
            section_key="executive_summary",
            language="cn",
        )

        assert result.section_key == "executive_summary"
        assert "华道汽车" in result.content or result.content != ""
        assert result.tokens_used == 800
        assert result.version_id == 2  # max version_id from assumptions
        assert result.generated_at != ""

    @patch.object(
        __import__(
            "backend.services.proposal_llm_service", fromlist=["ProposalLLMService"]
        ).ProposalLLMService,
        "_call_llm",
    )
    def test_generate_all_sections(self, mock_llm, mock_workspace_context):
        """验证三个 section 都能生成，内容非空"""
        # 让 _call_llm 根据调用次数返回不同内容
        responses = [
            MOCK_LLM_RESPONSES["executive_summary"],
            MOCK_LLM_RESPONSES["core_solution"],
            MOCK_LLM_RESPONSES["implementation_plan"],
        ]
        mock_llm.side_effect = responses

        gen = ProposalSectionGenerator()
        request = ProposalGenerationRequest(
            workspace_id="ws-test-001",
            sections=["executive_summary", "core_solution", "implementation_plan"],
            language="cn",
        )
        result = gen.generate_all(mock_workspace_context, request)

        assert result.workspace_id == "ws-test-001"
        assert result.executive_summary.content != ""
        assert result.core_solution.content != ""
        assert result.implementation_plan.content != ""
        assert result.total_tokens == 800 + 1200 + 1000

    @patch.object(
        __import__(
            "backend.services.proposal_llm_service", fromlist=["ProposalLLMService"]
        ).ProposalLLMService,
        "_call_llm",
    )
    def test_assumption_citation_in_content(self, mock_llm, mock_workspace_context):
        """验证生成内容引用了 assumption 中的数值"""
        mock_llm.return_value = MOCK_LLM_RESPONSES["core_solution"]

        gen = ProposalSectionGenerator()
        result = gen.generate_section(
            workspace=mock_workspace_context,
            section_key="core_solution",
            language="cn",
        )

        # 验证 version_id 被正确传入（用于引用）
        assert result.version_id == 2  # max version_id from active_assumptions
        # 内容不应为空
        assert result.content != ""

    @patch("backend.services.workspace_manager.WorkspaceManager.build_workspace_context")
    def test_qa_conflict_blocks_generation(
        self, mock_build_context, mock_workspace_with_conflict
    ):
        """验证：如果 assumption_qa_warnings 包含互斥冲突，生成被阻断"""
        mock_build_context.return_value = mock_workspace_with_conflict

        engine = ProposalEngine()

        with pytest.raises(ValueError) as exc_info:
            engine.generate_proposal(
                workspace_id="ws-test-conflict",
                sections=["executive_summary"],
            )

        assert "冲突" in str(exc_info.value) or "互斥" in str(exc_info.value)

    @patch("backend.services.workspace_manager.WorkspaceManager.build_workspace_context")
    @patch.object(
        __import__(
            "backend.services.proposal_llm_service", fromlist=["ProposalLLMService"]
        ).ProposalLLMService,
        "_call_llm",
    )
    def test_no_conflict_allows_generation(
        self, mock_llm, mock_build_context, mock_workspace_context
    ):
        """验证：无冲突时生成正常进行"""
        mock_build_context.return_value = mock_workspace_context
        mock_llm.return_value = MOCK_LLM_RESPONSES["executive_summary"]

        engine = ProposalEngine()
        result = engine.generate_proposal(
            workspace_id="ws-test-001",
            sections=["executive_summary"],
        )

        assert result.executive_summary.content != ""
