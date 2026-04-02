"""tests/test_pitch_renderer.py — v1.4 Pitch Renderer (Marp) Tests"""
from __future__ import annotations

import pytest

from backend.schemas.proposal_schemas import SectionOutput, ProposalSections
from backend.services.pitch_renderer import PitchRenderer


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def pitch_renderer() -> PitchRenderer:
    return PitchRenderer()


@pytest.fixture
def sample_proposal() -> ProposalSections:
    """标准 ProposalSections（含所有核心 sections）"""
    return ProposalSections(
        workspace_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        pipeline_id="pipeline-001",
        executive_summary=SectionOutput(
            section_key="executive_summary",
            title="执行摘要",
            content=(
                "本项目旨在为华道汽车零部件提供 JIT 供料解决方案。\n\n"
                "通过部署自动化立体仓库与智能输送系统，预计可将物流效率提升 35%，"
                "年度运营成本节省约 280 万元，投资回收期 2.8 年。"
            ),
            version_id=3,
            tokens_used=512,
            generated_at="2025-01-15T10:00:00Z",
        ),
        core_solution=SectionOutput(
            section_key="core_solution",
            title="核心方案设计",
            content=(
                "## 方案概述\n\n本方案采用「自动化立体仓库 + JIT 分拣线」组合模式。\n\n"
                "## 关键设计\n\n"
                "- 仓库面积：35,000 sqm\n"
                "- 日均订单：5,000 单\n"
                "- 人力配置：28 人/班次\n"
                "- 自动化设备：堆垛机 × 4 台、输送线 × 12 套"
            ),
            version_id=3,
            tokens_used=1024,
            generated_at="2025-01-15T10:00:05Z",
        ),
        implementation_plan=SectionOutput(
            section_key="implementation_plan",
            title="实施计划",
            content=(
                "## 阶段划分\n\n"
                "1. **需求确认**（第1-2周）\n"
                "2. **方案细化**（第3-6周）\n"
                "3. **实施部署**（第7-20周）\n"
                "4. **验收交付**（第21-24周）"
            ),
            version_id=3,
            tokens_used=768,
            generated_at="2025-01-15T10:00:10Z",
        ),
        financial_kpi=SectionOutput(
            section_key="financial_kpi",
            title="财务 KPI",
            content=(
                "## 财务指标摘要\n\n"
                "- 5年 ROI：185%\n"
                "- 投资回收期：2.8 年\n"
                "- 年节省成本：280 万元\n"
                "- NPV（10%折现率）：1,020 万元"
            ),
            version_id=3,
            tokens_used=384,
            generated_at="2025-01-15T10:00:15Z",
        ),
        total_tokens=2304,
        generated_at="2025-01-15T10:00:10Z",
    )


@pytest.fixture
def minimal_proposal() -> ProposalSections:
    """最小化 ProposalSections（只有核心三个 section）"""
    return ProposalSections(
        workspace_id="minws-0000-0001-0002-0003",
        pipeline_id="pipeline-002",
        executive_summary=SectionOutput(
            section_key="executive_summary",
            title="执行摘要",
            content="这是一个最小化的测试提案。",
            version_id=1,
        ),
        core_solution=SectionOutput(
            section_key="core_solution",
            title="核心方案",
            content="核心方案内容。",
            version_id=1,
        ),
        implementation_plan=SectionOutput(
            section_key="implementation_plan",
            title="实施计划",
            content="实施计划内容。",
            version_id=1,
        ),
        total_tokens=100,
        generated_at="2025-01-01T00:00:00Z",
    )


# ─── Tests: render_marp_markdown ───────────────────────────────────────────────

def test_render_marp_markdown_includes_all_sections(pitch_renderer, sample_proposal):
    """验证所有核心 section 都被渲染"""
    md = pitch_renderer.render_marp_markdown(sample_proposal)

    assert "飞力达物流" in md
    assert "执行摘要" in md
    assert "核心方案设计" in md
    assert "阶段划分" in md  # 实施计划内容的子章节标题
    assert "财务 KPI" in md
    assert "感谢各位评委" in md  # 结束页


def test_slide_separator_present(pitch_renderer, minimal_proposal):
    """验证 Marp 分隔符 --- 存在"""
    md = pitch_renderer.render_marp_markdown(minimal_proposal)

    # 每个幻灯片应该以 --- 分隔符开始
    count = md.count("---")
    assert count >= 4, f"Expected at least 4 slide separators, got {count}"


def test_executive_summary_slides_generated(pitch_renderer, sample_proposal):
    """验证生成封面 + 执行摘要幻灯片"""
    md = pitch_renderer.render_marp_markdown(sample_proposal)

    # 封面
    assert "## 物流解决方案提案书" in md
    assert "项目编号" in md
    assert "生成日期" in md

    # 执行摘要内容
    assert "JIT" in md or "供料" in md
    assert "35%" in md or "280 万元" in md


def test_render_marp_markdown_themes(pitch_renderer, minimal_proposal):
    """验证不同 theme 参数产生不同的背景色"""
    md_default = pitch_renderer.render_marp_markdown(minimal_proposal, theme="default")
    md_minimal = pitch_renderer.render_marp_markdown(minimal_proposal, theme="minimal")
    md_gaussian = pitch_renderer.render_marp_markdown(minimal_proposal, theme="gaussian")

    # 三种 theme 的背景色不同
    assert "#1a3a5c" in md_default
    assert "#2d3748" in md_minimal
    assert "#553C9A" in md_gaussian


def test_render_marp_markdown_company_name(pitch_renderer, minimal_proposal):
    """验证自定义公司名称"""
    md = pitch_renderer.render_marp_markdown(minimal_proposal, company_name="测试物流公司")
    assert "测试物流公司" in md


# ─── Tests: render_slide ──────────────────────────────────────────────────────

def test_render_slide_basic(pitch_renderer):
    """验证单张幻灯片渲染"""
    slide = pitch_renderer.render_slide(
        title="测试标题",
        content="这是测试内容。",
    )
    assert "---" in slide
    assert "## 测试标题" in slide
    assert "这是测试内容" in slide


def test_render_slide_with_background(pitch_renderer):
    """验证带背景色的幻灯片"""
    slide = pitch_renderer.render_slide(
        title="带背景的幻灯片",
        content="内容",
        background="#f0f0f0",
    )
    assert "<!-- backgroundColor: #f0f0f0 -->" in slide
    assert "## 带背景的幻灯片" in slide


def test_render_slide_without_background(pitch_renderer):
    """验证无背景色时不输出 backgroundColor 注释"""
    slide = pitch_renderer.render_slide(
        title="无背景",
        content="内容",
    )
    assert "backgroundColor" not in slide
    assert "## 无背景" in slide


# ─── Tests: get_executive_summary_slides ─────────────────────────────────────

def test_executive_summary_slides_generated(pitch_renderer, sample_proposal):
    """验证执行摘要幻灯片生成"""
    slides = pitch_renderer.get_executive_summary_slides(sample_proposal)

    assert isinstance(slides, list)
    assert len(slides) >= 1
    assert all("title" in s and "content" in s for s in slides)
    assert slides[0]["title"] == "执行摘要"


def test_executive_summary_splits_long_content(pitch_renderer):
    """验证长内容被正确分页"""
    long_content = "\n\n".join([f"这是第{i}段内容。" * 20 for i in range(10)])
    proposal = ProposalSections(
        workspace_id="long-ws-0001",
        pipeline_id="p1",
        executive_summary=SectionOutput(
            section_key="executive_summary",
            title="长摘要",
            content=long_content,
            version_id=1,
        ),
        core_solution=SectionOutput(
            section_key="core_solution",
            title="核心",
            content="内容",
            version_id=1,
        ),
        implementation_plan=SectionOutput(
            section_key="implementation_plan",
            title="实施",
            content="内容",
            version_id=1,
        ),
    )

    slides = pitch_renderer.get_executive_summary_slides(proposal)
    # 长内容应被拆分为多页
    assert len(slides) >= 2


# ─── Tests: get_financial_slides ─────────────────────────────────────────────

def test_financial_slides_from_financial_kpi(pitch_renderer, sample_proposal):
    """验证 financial_kpi 作为财务数据来源"""
    slides = pitch_renderer.get_financial_slides(sample_proposal)

    assert isinstance(slides, list)
    assert len(slides) >= 1
    # 财务内容应包含 ROI 等关键词
    full_content = " ".join(s["content"] for s in slides)
    assert any(kw in full_content for kw in ["ROI", "回收期", "NPV", "280"])


def test_financial_slides_fallback_to_core_solution(pitch_renderer, minimal_proposal):
    """验证 financial_kpi 缺失时从 core_solution 提取"""
    # minimal_proposal 没有 financial_kpi
    slides = pitch_renderer.get_financial_slides(minimal_proposal)

    # 应返回保底页
    assert isinstance(slides, list)
    assert len(slides) >= 1


def test_financial_slides_with_financial_summary(pitch_renderer):
    """验证 financial_summary 优先级高于 financial_kpi"""
    proposal = ProposalSections(
        workspace_id="fin-ws-0001",
        pipeline_id="p1",
        executive_summary=SectionOutput(
            section_key="executive_summary",
            title="摘要",
            content="内容",
            version_id=1,
        ),
        core_solution=SectionOutput(
            section_key="core_solution",
            title="核心",
            content="内容",
            version_id=1,
        ),
        implementation_plan=SectionOutput(
            section_key="implementation_plan",
            title="实施",
            content="内容",
            version_id=1,
        ),
        financial_summary=SectionOutput(
            section_key="financial_summary",
            title="财务摘要",
            content="财务摘要内容。",
            version_id=1,
        ),
        financial_kpi=SectionOutput(
            section_key="financial_kpi",
            title="财务 KPI",
            content="KPI内容。",
            version_id=1,
        ),
    )

    slides = pitch_renderer.get_financial_slides(proposal)
    # financial_summary 优先
    full_content = " ".join(s["content"] for s in slides)
    assert "财务摘要" in full_content or "摘要" in full_content


# ─── Tests: Edge cases ────────────────────────────────────────────────────────

def test_render_marp_markdown_empty_optional_fields(pitch_renderer):
    """验证 optional fields 为 None 时不崩溃"""
    proposal = ProposalSections(
        workspace_id="empty-ws-0001",
        pipeline_id="p1",
        executive_summary=SectionOutput(
            section_key="executive_summary",
            title="摘要",
            content="内容",
            version_id=1,
        ),
        core_solution=SectionOutput(
            section_key="core_solution",
            title="核心",
            content="内容",
            version_id=1,
        ),
        implementation_plan=SectionOutput(
            section_key="implementation_plan",
            title="实施",
            content="内容",
            version_id=1,
        ),
        # financial_kpi / financial_summary 保持 None
    )

    md = pitch_renderer.render_marp_markdown(proposal)
    assert "飞力达物流" in md
    assert "---" in md


def test_render_slide_content_supports_markdown(pitch_renderer):
    """验证 slide content 支持 Markdown 格式"""
    slide = pitch_renderer.render_slide(
        title="Markdown 测试",
        content="- 项目一\n- 项目二\n- 项目三\n\n**粗体** 和 *斜体*",
    )
    assert "- 项目一" in slide
    assert "**粗体**" in slide


def test_render_marp_markdown_custom_theme(pitch_renderer, minimal_proposal):
    """验证无效 theme 降级为 default"""
    md = pitch_renderer.render_marp_markdown(minimal_proposal, theme="nonexistent")
    assert "#1a3a5c" in md  # default 主题色


def test_chunk_content_exact_fit(pitch_renderer):
    """验证恰好等于 max_chars 的内容不拆分"""
    content = "A" * 500
    chunks = pitch_renderer._chunk_content(content, max_chars=500)
    assert len(chunks) == 1
    assert chunks[0] == content


def test_chunk_content_hard_truncate(pitch_renderer):
    """验证超长单词/无空格的段落会被截断"""
    content = "A" * 1000  # 无空格的超长字符串
    chunks = pitch_renderer._chunk_content(content, max_chars=500)
    assert len(chunks) >= 1
    assert all(len(c) <= 550 for c in chunks)  # 有一点容差
