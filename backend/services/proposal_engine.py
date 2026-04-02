"""backend/services/proposal_engine.py 提案生成引擎 orchestrator"""
from __future__ import annotations

from backend.services.workspace_manager import WorkspaceManager
from backend.services.proposal_section_generator import ProposalSectionGenerator
from backend.schemas.proposal_schemas import (
    ProposalSections,
    ProposalGenerationRequest,
)


class ProposalEngine:
    """
    提案生成引擎 orchestrator。
    整合 WorkspaceManager（拉取上下文）+ ProposalSectionGenerator（生成文本）。
    """

    # 内存缓存：workspace_id -> ProposalSections
    _proposal_cache: dict[str, ProposalSections] = {}

    def __init__(self):
        self.workspace_manager = WorkspaceManager()
        self.section_generator = ProposalSectionGenerator()

    def save_proposal(self, workspace_id: str, sections: ProposalSections) -> None:
        """
        将生成的 ProposalSections 缓存到内存中。

        Args:
            workspace_id: Workspace UUID
            sections: 生成的 ProposalSections 对象
        """
        self._proposal_cache[workspace_id] = sections

    def get_latest_proposal(self, workspace_id: str) -> ProposalSections | None:
        """
        从内存缓存中获取最近一次生成的 ProposalSections。

        Args:
            workspace_id: Workspace UUID

        Returns:
            ProposalSections 对象，若不存在则返回 None
        """
        return self._proposal_cache.get(workspace_id)

    def generate_proposal(
        self,
        workspace_id: str,
        sections: list[str] | None = None,
        language: str = "cn",
        style: str = "formal",
        override_prompts: dict | None = None,
    ) -> ProposalSections:
        """
        端到端生成提案。

        流程：
        1. 从 WorkspaceManager 获取 WorkspaceContext
        2. 检查 QA 冲突（如果 assumption 有互斥警告，阻断生成）
        3. 调用 ProposalSectionGenerator.generate_all()
        4. 返回 ProposalSections

        Args:
            workspace_id: Workspace UUID
            sections: 要生成的章节列表，None 则用默认
            language: 语言，"cn" 或 "en"
            style: 风格，"formal" / "concise" / "detailed"
            override_prompts: 可选，覆盖特定 section 的 prompt

        Returns:
            ProposalSections 对象

        Raises:
            ValueError: 如果 Workspace 不存在或 Assumption 存在未解决的互斥冲突
        """
        # 1. 获取 workspace context
        workspace = self.workspace_manager.build_workspace_context(workspace_id)

        # 2. 检查 assumption_qa_warnings — 互斥冲突阻断
        if workspace.assumption_qa_warnings:
            conflict_keywords = ["互斥", "冲突", "contradiction", "conflict"]
            for warning in workspace.assumption_qa_warnings:
                if any(kw in warning for kw in conflict_keywords):
                    raise ValueError(
                        f"Assumption 冲突未解决，无法生成提案: {warning}"
                    )

        # 3. 构建 request 并生成
        request = ProposalGenerationRequest(
            workspace_id=workspace_id,
            sections=sections
            or ["executive_summary", "core_solution", "implementation_plan"],
            language=language,
            style=style,
            override_prompts=override_prompts or {},
        )

        # 4. 生成所有章节
        result = self.section_generator.generate_all(workspace, request)

        # 5. 缓存到内存
        self.save_proposal(workspace_id, result)

        return result
