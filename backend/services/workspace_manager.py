"""backend/services/workspace_manager.py Workspace lifecycle manager for v1.0 Proposal Studio"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Any

from backend.models.database import SessionLocal
from backend.models.workspace_models import Workspace
from backend.schemas.workspace_schemas import (
    WorkspaceContext,
    WorkspaceSchema,
)
from backend.services.equipment_service import EquipmentService


class WorkspaceManager:
    """Workspace 生命周期管理器"""

    def __init__(self):
        self.equipment_service = EquipmentService()

    def _to_schema(self, workspace: Workspace) -> WorkspaceSchema:
        """Convert SQLAlchemy model to Pydantic schema."""
        return WorkspaceSchema(
            workspace_id=workspace.workspace_id,
            pipeline_id=workspace.pipeline_id,
            project_name=workspace.project_name,
            industry=workspace.industry,
            region=workspace.region,
            base_solution_snapshot=json.loads(workspace.base_solution_snapshot or "{}"),
            assumption_snapshot=json.loads(workspace.assumption_snapshot or "[]"),
            context_json=json.loads(workspace.context_json or "{}"),
            snapshot_version=workspace.snapshot_version,
            is_dirty=workspace.is_dirty,
            status=workspace.status,
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
            finalized_at=workspace.finalized_at,
        )

    def create_workspace(
        self,
        pipeline_id: str,
        project_name: str = "",
        industry: str = "",
        region: str = "",
    ) -> Workspace:
        """
        创建新 Workspace 并做首次快照。

        Args:
            pipeline_id: 关联的 pipeline run ID
            project_name: 项目名称
            industry: 行业
            region: 区域

        Returns:
            新建的 Workspace SQLAlchemy 模型实例
        """
        workspace_id = str(uuid.uuid4())
        with SessionLocal() as db:
            workspace = Workspace(
                workspace_id=workspace_id,
                pipeline_id=pipeline_id,
                project_name=project_name,
                industry=industry,
                region=region,
                base_solution_snapshot="{}",
                assumption_snapshot="[]",
                context_json="{}",
                snapshot_version=1,
                is_dirty=True,
                status="active",
            )
            db.add(workspace)
            db.commit()
            db.refresh(workspace)
            return workspace

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        """
        根据 workspace_id 获取 Workspace。

        Args:
            workspace_id: Workspace 的 UUID

        Returns:
            Workspace 模型实例或 None
        """
        with SessionLocal() as db:
            return db.query(Workspace).filter(
                Workspace.workspace_id == workspace_id
            ).first()

    def _inject_equipment_snapshot(self, workspace: Workspace, base_solution_json: dict) -> dict:
        """
        根据 base_solution 中的 operation_type，从 Equipment Database 匹配设备。
        将匹配结果注入 context_json。
        """
        selected_equipment = []
        capex_ranges = {}

        operation_type = base_solution_json.get("operation_type", "")

        # 简化策略：基于运营类型推断设备类型
        # 实际生产中应该从 downstream_input 或 assumption 中取吞吐量目标
        equipment_map = {
            "warehouse_distribution": [("AMR", 60), ("Conveyor", 150)],
            "cold_chain": [("Conveyor", 100), ("Sorter", 2000)],
            "bonded": [("Conveyor", 80), ("AS/RS", 50)],
            "3PL": [("AMR", 60), ("Conveyor", 100)],
            "JIT": [("Conveyor", 80), ("AS/RS", 50)],
            "JIT线边仓": [("AMR", 60), ("Conveyor", 80)],
            "VMI Hub": [("AMR", 50), ("Conveyor", 100)],
        }

        equipment_types = equipment_map.get(operation_type, [("AMR", 60), ("Conveyor", 100)])

        for eq_type, throughput_target in equipment_types:
            matches = self.equipment_service.match_equipment_for_scenario(
                equipment_type=eq_type,
                throughput_target=float(throughput_target),
                payload_min=None,
            )
            if matches:
                best = matches[0]
                eq_dict = best.equipment.model_dump(mode="json")
                eq_dict["_match_score"] = best.match_score
                eq_dict["_capex_estimate"] = best.capex_estimate
                selected_equipment.append(eq_dict)

                capex_ranges[eq_type.lower()] = {
                    "min": best.equipment.capex_min,
                    "max": best.equipment.capex_max,
                }

        # 生成 rationale
        rationale_parts = []
        for eq in selected_equipment:
            rationale_parts.append(
                f"{eq['equipment_type']}-{eq['model_name']}："
                f"吞吐量{eq['throughput_value']}{eq['throughput_unit']}，"
                f"估算单价{eq['capex_max']}万元"
            )
        equipment_rationale = "；".join(rationale_parts)

        return {
            "selected_equipment": selected_equipment,
            "equipment_capex_range": capex_ranges,
            "equipment_rationale": equipment_rationale,
        }

    def refresh_snapshot(
        self,
        workspace_id: str,
        base_solution_json: dict,
        assumption_list: list[dict],
        downstream_input: dict,
    ) -> Workspace:
        """
        重新拉取 v0.7 Base Solution + v0.9 Assumptions，生成新的 context_json。
        snapshot_version += 1，is_dirty = True。

        Args:
            workspace_id: Workspace UUID
            base_solution_json: v0.7 BaseSolution JSON 输出
            assumption_list: v0.9 假设列表 (AssumptionSchema dicts)
            downstream_input: 下游输入，包含 cost_mode / roi_summary

        Returns:
            更新后的 Workspace 模型
        """
        with SessionLocal() as db:
            workspace = db.query(Workspace).filter(
                Workspace.workspace_id == workspace_id
            ).first()
            if not workspace:
                raise ValueError(f"Workspace not found: {workspace_id}")

            # 更新快照字段
            workspace.base_solution_snapshot = json.dumps(base_solution_json, ensure_ascii=False)
            workspace.assumption_snapshot = json.dumps(assumption_list, ensure_ascii=False)

            # 构建 WorkspaceContext
            active_assumptions = []
            overridden_assumptions = []
            for a in assumption_list:
                if a.get("is_overridden", False):
                    overridden_assumptions.append(a)
                else:
                    active_assumptions.append(a)

            # 从 base_solution_json 提取字段
            context_dict = {
                "workspace_id": workspace.workspace_id,
                "pipeline_id": workspace.pipeline_id,
                "project_name": workspace.project_name,
                "industry": workspace.industry,
                "region": workspace.region,
                "operation_type": base_solution_json.get("operation_type", ""),
                "complexity_level": base_solution_json.get("complexity_level", ""),
                "complexity_score": base_solution_json.get("complexity_score", 0),
                "operation_narrative": base_solution_json.get("operation_narrative", ""),
                "labor_modules": base_solution_json.get("labor_modules", {}),
                "process_modules": base_solution_json.get("process_modules", {}),
                "service_scope": base_solution_json.get("service_scope", {}),
                "analysis_sections": base_solution_json.get("analysis_sections", {}),
                "active_assumptions": active_assumptions,
                "overridden_assumptions": overridden_assumptions,
                "assumption_qa_warnings": downstream_input.get("assumption_qa_warnings", []),
                "snapshot_version": workspace.snapshot_version + 1,
                "is_dirty": True,
                "status": workspace.status,
                "cost_mode": downstream_input.get("cost_mode", ""),
                "roi_summary": downstream_input.get("roi_summary", {}),
            }

            # v1.1 Scenario-Equipment DI：注入匹配设备
            equipment_data = self._inject_equipment_snapshot(workspace, base_solution_json)
            context_dict.update({
                "selected_equipment": equipment_data["selected_equipment"],
                "equipment_capex_range": equipment_data["equipment_capex_range"],
                "equipment_rationale": equipment_data["equipment_rationale"],
            })

            workspace.context_json = json.dumps(context_dict, ensure_ascii=False)

            # 版本控制
            workspace.snapshot_version += 1
            workspace.is_dirty = True

            db.commit()
            db.refresh(workspace)
            return workspace

    def update_context_field(
        self,
        workspace_id: str,
        field_path: str,
        value: Any,
    ) -> Workspace:
        """
        用户在 Workspace UI 中直接修改某个字段，标记为 dirty。

        Args:
            workspace_id: Workspace UUID
            field_path: 字段路径，如 "project_name" 或 "cost_mode"
            value: 新值

        Returns:
            更新后的 Workspace 模型
        """
        with SessionLocal() as db:
            workspace = db.query(Workspace).filter(
                Workspace.workspace_id == workspace_id
            ).first()
            if not workspace:
                raise ValueError(f"Workspace not found: {workspace_id}")

            # 更新 context_json 中的字段
            context = json.loads(workspace.context_json or "{}")
            context[field_path] = value
            context["is_dirty"] = True
            workspace.context_json = json.dumps(context, ensure_ascii=False)

            # 更新 Workspace 表字段（如果字段在 Workspace 模型上有对应列）
            if field_path == "project_name":
                workspace.project_name = value
            elif field_path == "industry":
                workspace.industry = value
            elif field_path == "region":
                workspace.region = value

            workspace.is_dirty = True
            db.commit()
            db.refresh(workspace)
            return workspace

    def finalize_workspace(self, workspace_id: str) -> Workspace:
        """
        最终化 Workspace，锁定快照，is_dirty = False，status = finalized。

        Args:
            workspace_id: Workspace UUID

        Returns:
            更新后的 Workspace 模型
        """
        with SessionLocal() as db:
            workspace = db.query(Workspace).filter(
                Workspace.workspace_id == workspace_id
            ).first()
            if not workspace:
                raise ValueError(f"Workspace not found: {workspace_id}")

            workspace.is_dirty = False
            workspace.status = "finalized"
            workspace.finalized_at = datetime.now(timezone.utc)

            # context_json 中也标记
            context = json.loads(workspace.context_json or "{}")
            context["is_dirty"] = False
            context["status"] = "finalized"
            workspace.context_json = json.dumps(context, ensure_ascii=False)

            db.commit()
            db.refresh(workspace)
            return workspace

    def build_workspace_context(self, workspace_id: str) -> WorkspaceContext:
        """
        将 Workspace 的 context_json 解析为 WorkspaceContext Pydantic 模型。
        这是 proposal_engine.py 的核心输入。

        Args:
            workspace_id: Workspace UUID

        Returns:
            WorkspaceContext Pydantic 模型
        """
        with SessionLocal() as db:
            workspace = db.query(Workspace).filter(
                Workspace.workspace_id == workspace_id
            ).first()
            if not workspace:
                raise ValueError(f"Workspace not found: {workspace_id}")

            context_dict = json.loads(workspace.context_json or "{}")
            return WorkspaceContext(**context_dict)

    def list_workspaces(
        self,
        pipeline_id: str | None = None,
        status: str | None = None,
    ) -> list[Workspace]:
        """
        列出 Workspace，支持按 pipeline_id 和 status 过滤。

        Args:
            pipeline_id: 可选，按 pipeline_id 过滤
            status: 可选，按 status 过滤 (active / finalized / archived)

        Returns:
            Workspace 列表
        """
        with SessionLocal() as db:
            query = db.query(Workspace)
            if pipeline_id is not None:
                query = query.filter(Workspace.pipeline_id == pipeline_id)
            if status is not None:
                query = query.filter(Workspace.status == status)
            return query.order_by(Workspace.updated_at.desc()).all()
