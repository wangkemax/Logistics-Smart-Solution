"""backend/services/pitch_renderer.py — v1.4 Markdown to PPT via Marp"""
from __future__ import annotations

import datetime
from datetime import timezone
import textwrap
from typing import Optional

from backend.schemas.proposal_schemas import ProposalSections, SectionOutput


class PitchRenderer:
    """
    演讲稿渲染器（Marp 方案）。

    将 ProposalSections 渲染为结构化 Markdown（含 Marp 幻灯片分隔符 ---），
    可通过 Marp CLI 或 marp-cli npm 包渲染为 PPTX/PDF。

    幻灯片结构：
    1. 封面（项目名称 + 公司 + 日期）
    2. 执行摘要（1-2页）
    3. 核心方案（2-3页）
    4. 财务测算（1-2页）
    5. 实施计划（1-2页）
    6. 附录
    """

    # Marp 全局 theme 设置（可注入到每张幻灯片）
    THEME_COLORS = {
        "default": {
            "cover_bg": "#1a3a5c",
            "cover_text": "#ffffff",
            "section_bg": "#2c5282",
            "section_text": "#ffffff",
            "content_bg": "#f7fafc",
            "content_text": "#2d3748",
            "accent": "#3182ce",
            "highlight_bg": "#ebf8ff",
        },
        "minimal": {
            "cover_bg": "#2d3748",
            "cover_text": "#ffffff",
            "section_bg": "#4a5568",
            "section_text": "#ffffff",
            "content_bg": "#ffffff",
            "content_text": "#1a202c",
            "accent": "#718096",
            "highlight_bg": "#edf2f7",
        },
        "gaussian": {
            "cover_bg": "#553C9A",
            "cover_text": "#ffffff",
            "section_bg": "#6B46C1",
            "section_text": "#ffffff",
            "content_bg": "#FAF5FF",
            "content_text": "#2d3748",
            "accent": "#9F7AEA",
            "highlight_bg": "#e9d8fd",
        },
    }

    def render_marp_markdown(
        self,
        proposal: ProposalSections,
        company_name: str = "飞力达物流",
        theme: str = "default",
    ) -> str:
        """
        将 ProposalSections 渲染为 Marp Markdown。

        Marp 关键语法：
        ---  (幻灯片分隔符)
        <!-- backgroundColor: ... -->  (背景色)
        <!-- leader: ... -->  (页码)

        返回完整的 Markdown 文本，可直接传给 marp-cli 渲染为 PPTX。
        """
        colors = self.THEME_COLORS.get(theme, self.THEME_COLORS["default"])
        slides = []

        # ── 1. 封面 ──────────────────────────────────────────────────────────
        slides.append(self._render_cover_slide(proposal, company_name, colors))

        # ── 2. 执行摘要 ─────────────────────────────────────────────────────
        summary_slides = self.get_executive_summary_slides(proposal)
        for slide_data in summary_slides:
            slides.append(
                self.render_slide(
                    title=slide_data["title"],
                    content=slide_data["content"],
                    background=colors.get("content_bg"),
                )
            )

        # ── 3. 核心方案 ─────────────────────────────────────────────────────
        slides.append(
            self.render_slide(
                title=proposal.core_solution.title,
                content=proposal.core_solution.content,
                background=colors.get("content_bg"),
            )
        )
        # 如果 content 较长，自动分页（每 600 字符切一张）
        core_content = proposal.core_solution.content
        if len(core_content) > 600:
            chunks = self._chunk_content(core_content, max_chars=600)
            for chunk in chunks[1:]:
                slides.append(
                    self.render_slide(
                        title="核心方案（续）",
                        content=chunk,
                        background=colors.get("content_bg"),
                    )
                )

        # ── 4. 财务测算 ─────────────────────────────────────────────────────
        fin_slides = self.get_financial_slides(proposal)
        for slide_data in fin_slides:
            slides.append(
                self.render_slide(
                    title=slide_data["title"],
                    content=slide_data["content"],
                    background=colors.get("highlight_bg"),
                )
            )

        # ── 5. 实施计划 ─────────────────────────────────────────────────────
        impl_slides = self._render_implementation_slides(proposal)
        for slide_data in impl_slides:
            slides.append(
                self.render_slide(
                    title=slide_data["title"],
                    content=slide_data["content"],
                    background=colors.get("content_bg"),
                )
            )

        # ── 6. 附录（假设清单）──────────────────────────────────────────────
        appendix_slide = self._render_appendix_slide(proposal)
        if appendix_slide:
            slides.append(appendix_slide)

        # ── 7. 结束页 ──────────────────────────────────────────────────────
        slides.append(self._render_ending_slide(company_name, colors))

        return "\n".join(slides)

    def render_slide(
        self,
        title: str,
        content: str,
        background: Optional[str] = None,
    ) -> str:
        """
        渲染单张幻灯片（通用方法）。

        Args:
            title: 幻灯片标题
            content: 幻灯片正文内容（支持 Markdown）
            background: 背景色（如 "#f7fafc"）

        Returns:
            单张幻灯片的 Marp Markdown 文本（含 --- 分隔符）
        """
        lines = ["---"]
        if background:
            lines.append(f"<!-- backgroundColor: {background} -->")
        lines.append("")
        lines.append(f"## {title}")
        lines.append("")
        # content 本身支持 Markdown 格式，直接附加
        lines.append(content)
        lines.append("")
        return "\n".join(lines)

    def get_executive_summary_slides(self, proposal: ProposalSections) -> list[dict]:
        """
        生成执行摘要幻灯片。

        从 executive_summary.content 中提取关键点，生成多张幻灯片。
        策略：按换行符拆分 content，如果超过 400 字符则进一步分块。
        """
        slides = []
        raw = proposal.executive_summary.content

        # 按双换行拆分段落
        paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]

        current_slide_content = ""
        for para in paragraphs:
            if len(current_slide_content) + len(para) < 500:
                current_slide_content += para + "\n\n"
            else:
                if current_slide_content:
                    slides.append({
                        "title": proposal.executive_summary.title,
                        "content": current_slide_content.strip(),
                    })
                # 单独段落超长则截断
                if len(para) > 500:
                    chunks = self._chunk_content(para, max_chars=450)
                    for ch in chunks:
                        slides.append({
                            "title": proposal.executive_summary.title,
                            "content": ch,
                        })
                else:
                    current_slide_content = para + "\n\n"

        if current_slide_content.strip():
            slides.append({
                "title": proposal.executive_summary.title,
                "content": current_slide_content.strip(),
            })

        # 至少保证有一页
        if not slides:
            slides.append({
                "title": proposal.executive_summary.title,
                "content": raw or "(无内容)",
            })

        return slides

    def get_financial_slides(self, proposal: ProposalSections) -> list[dict]:
        """
        生成财务测算幻灯片。

        优先使用 financial_summary，其次 financial_kpi，
        最后回退到 core_solution 中的 ROI 相关内容。
        """
        slides = []
        source: Optional[SectionOutput] = None
        source_label = ""

        if proposal.financial_summary:
            source = proposal.financial_summary
            source_label = proposal.financial_summary.title
        elif proposal.financial_kpi:
            source = proposal.financial_kpi
            source_label = proposal.financial_kpi.title
        else:
            # 从 core_solution 中提取含 ROI/IRR/回收期 的段落
            roi_paragraphs = []
            for para in proposal.core_solution.content.split("\n"):
                if any(kw in para for kw in ["ROI", "IRR", "回收期", "投资", "收益", "NPV", "payback"]):
                    roi_paragraphs.append(para.strip())
            if roi_paragraphs:
                source = SectionOutput(
                    section_key="financial_kpi",
                    title="财务测算摘要",
                    content="\n".join(roi_paragraphs),
                )
                source_label = "财务测算摘要"

        if source:
            content = source.content
            if len(content) > 500:
                chunks = self._chunk_content(content, max_chars=500)
                for i, ch in enumerate(chunks):
                    title_suffix = f"（{i + 1}/{len(chunks)}）" if len(chunks) > 1 else ""
                    slides.append({
                        "title": f"{source_label}{title_suffix}",
                        "content": ch,
                    })
            else:
                slides.append({
                    "title": source_label,
                    "content": content,
                })

        # 保底：一页"财务测算"说明页
        if not slides:
            slides.append({
                "title": "财务测算",
                "content": (
                    "本项目已完成财务测算，详见完整提案文档。\n\n"
                    "核心指标包括：\n"
                    "- 5年 ROI\n"
                    "- 投资回收期\n"
                    "- 年运营成本节省\n"
                    "- NPV（净现值）\n\n"
                    "请联系项目经理获取详细财务报告。"
                ),
            })

        return slides

    # ─── Private helpers ───────────────────────────────────────────────────────

    def _render_cover_slide(
        self,
        proposal: ProposalSections,
        company_name: str,
        colors: dict,
    ) -> str:
        """封面幻灯片"""
        date_str = datetime.datetime.now().strftime("%Y年%m月%d日")
        project_name = getattr(proposal, "workspace_id", "")  # 暂无 project_name 字段时用 workspace_id

        # 尝试从 context_json 找 project_name（通过 workspace_id）
        # 这里直接用 workspace_id 前 8 位作为项目标识
        project_id = proposal.workspace_id[:8]

        lines = [
            "---",
            f"<!-- backgroundColor: {colors['cover_bg']} -->",
            f"<!-- color: {colors['cover_text']} -->",
            "",
            f"# {company_name}",
            "",
            "## 物流解决方案提案书",
            "",
            f"**项目编号**：{project_id}",
            f"**生成日期**：{date_str}",
            "",
            "<!-- leader: * -->",  # 封面不显示页码
            "",
        ]
        return "\n".join(lines)

    def _render_implementation_slides(self, proposal: ProposalSections) -> list[dict]:
        """将实施计划 content 拆分为多页幻灯片"""
        slides = []
        content = proposal.implementation_plan.content

        # 按 ## 标题拆分（多级章节）
        sections = []
        current_title = proposal.implementation_plan.title
        current_body = []

        for line in content.split("\n"):
            if line.startswith("## "):
                if current_body:
                    sections.append((current_title, "\n".join(current_body).strip()))
                    current_body = []
                current_title = line[3:].strip()
            else:
                current_body.append(line)

        if current_body:
            sections.append((current_title, "\n".join(current_body).strip()))

        for title, body in sections:
            if len(body) > 600:
                chunks = self._chunk_content(body, max_chars=600)
                for i, ch in enumerate(chunks):
                    suffix = f"（{i + 1}/{len(chunks)}）" if len(chunks) > 1 else ""
                    slides.append({"title": f"{title}{suffix}", "content": ch})
            else:
                slides.append({"title": title, "content": body})

        return slides

    def _render_appendix_slide(self, proposal: ProposalSections) -> Optional[str]:
        """附录幻灯片：展示假设清单摘要"""
        # 从 context_json 中提取 active_assumptions 已在其他模块处理
        # 这里只展示一个说明页
        if not proposal.executive_summary.version_id:
            return None

        lines = [
            "---",
            "<!-- backgroundColor: #f7fafc -->",
            "",
            "## 附录：本方案假设参数",
            "",
            f"- 假设版本：v{proposal.executive_summary.version_id}",
            f"- 生成时间：{proposal.generated_at or datetime.datetime.now(timezone.utc).isoformat()}",
            f"- Workspace：{proposal.workspace_id[:8]}",
            "",
            "*详细假设清单请参阅完整提案文档*",
            "",
        ]
        return "\n".join(lines)

    def _render_ending_slide(self, company_name: str, colors: dict) -> str:
        """结束页幻灯片"""
        lines = [
            "---",
            f"<!-- backgroundColor: {colors['cover_bg']} -->",
            f"<!-- color: {colors['cover_text']} -->",
            "",
            f"## 感谢各位评委",
            "",
            f"**{company_name}**",
            "",
            "期待与贵司携手共建智能化物流解决方案",
            "",
            "<!-- leader: * -->",
            "",
        ]
        return "\n".join(lines)

    def _chunk_content(self, content: str, max_chars: int = 500) -> list[str]:
        """
        将长内容按自然段落拆分为多个块，每块不超过 max_chars 字符。

        优先按段落拆分，其次按句子拆分，最后按单词截断。
        """
        if len(content) <= max_chars:
            return [content]

        chunks = []
        current = []

        for para in content.split("\n"):
            para = para.strip()
            if not para:
                continue

            # 段落级别
            if sum(len(p) for p in current) + len(para) + len(current) <= max_chars:
                current.append(para)
            else:
                if current:
                    chunks.append("\n".join(current))
                    current = []

                if len(para) > max_chars:
                    # 句子级别
                    sentences = [s.strip() for s in para.replace("。", "。\n").split("\n") if s.strip()]
                    sub_current = []
                    for sent in sentences:
                        if sum(len(p) for p in sub_current) + len(sent) <= max_chars:
                            sub_current.append(sent)
                        else:
                            if sub_current:
                                chunks.append("".join(sub_current))
                            # 单句超长则硬截断
                            chunks.append(textwrap.shorten(sent, width=max_chars, placeholder="..."))
                            sub_current = []
                    if sub_current:
                        chunks.append("".join(sub_current))
                else:
                    current.append(para)

        if current:
            chunks.append("\n".join(current))

        return chunks or [content[:max_chars]]
