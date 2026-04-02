"""backend/models/workspace_models.py Workspace SQLAlchemy model for v1.0 Proposal Studio"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean

from backend.models.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(String(40), unique=True, index=True, nullable=False)  # UUID
    pipeline_id = Column(String(40), index=True, nullable=False)  # 关联的 pipeline run
    project_name = Column(String(200), default="")
    industry = Column(String(50), default="")
    region = Column(String(50), default="")

    # 快照状态
    base_solution_snapshot = Column(Text, default="{}")   # JSON: v0.7 BaseSolution 快照
    assumption_snapshot = Column(Text, default="[]")       # JSON: v0.9 假设列表快照
    context_json = Column(Text, default="{}")              # JSON: WorkspaceContext 合并结果

    # 版本控制
    snapshot_version = Column(Integer, default=1)  # 快照版本号，每次更新+1
    is_dirty = Column(Boolean, default=True)     # 是否有未发布的修改

    # 生命周期
    status = Column(String(20), default="active")  # active / finalized / archived
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    finalized_at = Column(DateTime, nullable=True)
