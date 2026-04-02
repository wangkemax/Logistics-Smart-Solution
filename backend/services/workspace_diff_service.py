"""backend/services/workspace_diff_service.py — v1.4 Bid Scenario Diffing"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from backend.models.database import SessionLocal
from backend.models.workspace_models import Workspace


class WorkspaceDiffService:
    """
    Workspace 版本对比服务。

    对比两个 Workspace 版本的参数差异和成本差异。
    """

    # 财务关键字段（用于 cost_diffs 展示）
    FINANCIAL_KEYS = (
        "roi_5y",
        "roi_summary",
        "capex_total",
        "capex_total_min",
        "capex_total_max",
        "opex_total",
        "payback_years",
        "irr",
        "net_annual_benefit",
        "npv",
    )

    # 需要展示百分比的数值字段
    PERCENTAGE_NUMERIC_KEYS = (
        "warehouse_area",
        "headcount_reduction",
        "throughput_target",
        "daily_orders",
        "sku_count",
    )

    def diff(
        self,
        workspace_a_id: str,
        workspace_b_id: str,
    ) -> dict:
        """
        对比两个 Workspace 的差异。

        Returns:
            {
                "workspace_a": {...},
                "workspace_b": {...},
                "param_diffs": [...],
                "cost_diffs": {...},
                "llm_analysis": "...",
            }
        """
        # 获取两个 Workspace
        ws_a = self._get_workspace(workspace_a_id)
        ws_b = self._get_workspace(workspace_b_id)

        if not ws_a or not ws_b:
            missing = []
            if not ws_a:
                missing.append(workspace_a_id)
            if not ws_b:
                missing.append(workspace_b_id)
            raise ValueError(f"Workspace not found: {', '.join(missing)}")

        # 解析 context_json
        ctx_a = self._parse_context(ws_a)
        ctx_b = self._parse_context(ws_b)

        # 比对参数差异
        param_diffs = self.diff_context_json(ctx_a, ctx_b)

        # 比对财务差异
        cost_diffs = self._diff_financial(ctx_a, ctx_b)

        # 生成 LLM 分析文本（简单模板，后续可接入 LLM 增强）
        llm_analysis = self._generate_analysis(param_diffs, cost_diffs, ws_a, ws_b)

        return {
            "workspace_a": {
                "workspace_id": ws_a.workspace_id,
                "snapshot_version": ws_a.snapshot_version,
                "created_at": self._format_datetime(ws_a.created_at),
                "status": ws_a.status,
                "project_name": ws_a.project_name,
                "industry": ws_a.industry,
            },
            "workspace_b": {
                "workspace_id": ws_b.workspace_id,
                "snapshot_version": ws_b.snapshot_version,
                "created_at": self._format_datetime(ws_b.created_at),
                "status": ws_b.status,
                "project_name": ws_b.project_name,
                "industry": ws_b.industry,
            },
            "param_diffs": param_diffs,
            "cost_diffs": cost_diffs,
            "llm_analysis": llm_analysis,
        }

    def diff_context_json(
        self,
        context_a: dict,
        context_b: dict,
    ) -> list[dict]:
        """
        对比两个 context_json 的差异。

        找出所有不同的字段，并对数值字段额外计算百分比变化。
        """
        diffs = []
        all_keys = set(context_a.keys()) | set(context_b.keys())

        # 排除嵌套对象（完整对比）
        skip_keys = {
            "active_assumptions",
            "overridden_assumptions",
            "selected_equipment",
            "assumption_qa_warnings",
            "roi_summary",
            "equipment_capex_range",
            "labor_modules",
            "process_modules",
            "service_scope",
            "analysis_sections",
        }

        for key in sorted(all_keys):
            if key in skip_keys:
                continue

            val_a = context_a.get(key)
            val_b = context_b.get(key)

            if val_a == val_b:
                continue

            diff_entry: dict[str, Any] = {
                "field": key,
                "value_a": val_a,
                "value_b": val_b,
            }

            # 数值字段：计算变化量和百分比
            if self._is_numeric(val_a) and self._is_numeric(val_b):
                num_a = float(val_a)
                num_b = float(val_b)
                delta = num_b - num_a

                if num_a != 0:
                    pct = (delta / abs(num_a)) * 100
                    diff_entry["diff"] = f"{self._fmt_sign(delta)} ({pct:+.1f}%)"
                else:
                    diff_entry["diff"] = f"{self._fmt_sign(delta)}"

                diff_entry["delta"] = delta
                diff_entry["pct_change"] = round((delta / abs(num_a)) * 100, 2) if num_a != 0 else None
            else:
                diff_entry["diff"] = self._summarize_diff(val_a, val_b)

            diffs.append(diff_entry)

        return diffs

    def get_workspace_versions(self, workspace_id: str) -> list[dict]:
        """
        获取某 Workspace 的快照历史。

        目前 Workspace 模型只有 snapshot_version 整数，
        未存储完整版本历史。若需历史快照，需扩展 WorkspaceHistory 表。
        这里返回当前版本信息作为"快照点"。
        """
        ws = self._get_workspace(workspace_id)
        if not ws:
            raise ValueError(f"Workspace not found: {workspace_id}")

        return [{
            "workspace_id": ws.workspace_id,
            "snapshot_version": ws.snapshot_version,
            "created_at": self._format_datetime(ws.created_at),
            "updated_at": self._format_datetime(ws.updated_at),
            "status": ws.status,
            "is_dirty": ws.is_dirty,
        }]

    # ─── Private helpers ────────────────────────────────────────────────────

    def _get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """从数据库读取 Workspace"""
        with SessionLocal() as db:
            return db.query(Workspace).filter(
                Workspace.workspace_id == workspace_id
            ).first()

    def _parse_context(self, workspace: Workspace) -> dict:
        """解析 context_json 为 dict"""
        if not workspace.context_json:
            return {}
        if isinstance(workspace.context_json, str):
            return json.loads(workspace.context_json)
        return workspace.context_json

    def _diff_financial(self, ctx_a: dict, ctx_b: dict) -> dict:
        """对比两个上下文的财务指标差异"""
        cost_diffs = {}

        # ROI summary 字段
        roi_a = ctx_a.get("roi_summary", {})
        roi_b = ctx_b.get("roi_summary", {})

        for key in self.FINANCIAL_KEYS:
            val_a = roi_a.get(key) if isinstance(roi_a, dict) else ctx_a.get(key)
            val_b = roi_b.get(key) if isinstance(roi_b, dict) else ctx_b.get(key)

            if val_a is None and val_b is None:
                continue

            diff_entry: dict[str, Any] = {
                "a": val_a,
                "b": val_b,
            }

            if self._is_numeric(val_a) and self._is_numeric(val_b):
                num_a = float(val_a)
                num_b = float(val_b)
                delta = num_b - num_a

                if key in ("roi_5y", "irr"):
                    # 百分比指标，单位是 pp
                    diff_entry["diff"] = f"{delta:+.1f}pp"
                    diff_entry["delta"] = round(delta, 2)
                elif key in ("payback_years",):
                    # 时间指标
                    diff_entry["diff"] = f"{delta:+.2f}年"
                    diff_entry["delta"] = round(delta, 2)
                else:
                    # 金额指标（万元）
                    if num_a != 0:
                        pct = (delta / abs(num_a)) * 100
                        diff_entry["diff"] = f"{delta:+.1f}万元 ({pct:+.1f}%)"
                    else:
                        diff_entry["diff"] = f"{delta:+.1f}万元"
                    diff_entry["delta"] = round(delta, 2)
                    diff_entry["pct_change"] = round((delta / abs(num_a)) * 100, 2) if num_a != 0 else None

            cost_diffs[key] = diff_entry

        return cost_diffs

    def _generate_analysis(
        self,
        param_diffs: list[dict],
        cost_diffs: dict,
        ws_a: Workspace,
        ws_b: Workspace,
    ) -> str:
        """生成简要的影响分析文本（模板 + 关键差异摘要）"""
        diff_count = len(param_diffs)
        changed_fields = [d["field"] for d in param_diffs]

        # 找出最重要的变化
        key_changes = []
        for d in param_diffs:
            if d["field"] in ("warehouse_area", "operation_type", "complexity_level",
                              "headcount_reduction", "contract_years"):
                key_changes.append(f"{d['field']}: {d.get('diff', '')}")

        analysis_parts = [
            f"方案 A（v{ws_a.snapshot_version}）与方案 B（v{ws_b.snapshot_version}）共发现 {diff_count} 项参数差异。",
        ]

        if key_changes:
            analysis_parts.append("主要变化：")
            for change in key_changes:
                analysis_parts.append(f"  - {change}")

        # 财务摘要
        fin_keys = ["roi_5y", "payback_years", "capex_total", "irr"]
        fin_lines = []
        for k in fin_keys:
            if k in cost_diffs and cost_diffs[k].get("diff"):
                fin_lines.append(f"  - {k}: {cost_diffs[k]['diff']}")

        if fin_lines:
            analysis_parts.append("财务影响：")
            analysis_parts.extend(fin_lines)

        analysis_parts.append(
            "\n建议：对比两个方案的核心差异，结合客户需求和预算约束，选择最优方案。"
        )

        return "\n".join(analysis_parts)

    def _is_numeric(self, val: Any) -> bool:
        """判断值是否为数值（int/float 且非 bool）"""
        return isinstance(val, (int, float)) and not isinstance(val, bool)

    def _fmt_sign(self, val: float) -> str:
        """格式化带符号数字（统一用 .2f，避免 format code d 用于 float 的问题）"""
        return f"{val:+.2f}"

    def _summarize_diff(self, val_a: Any, val_b: Any) -> str:
        """生成两值差异的字符串描述"""
        if val_a is None:
            return f"新增: {val_b}"
        if val_b is None:
            return f"移除: {val_a}"
        return f"{val_a} → {val_b}"

    def _format_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        """格式化 datetime 为 ISO 字符串"""
        if dt is None:
            return None
        if isinstance(dt, datetime):
            return dt.isoformat()
        return str(dt)
