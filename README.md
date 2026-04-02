# Logistics Smart Solution
### AI-Powered Logistics Presale Copilot

[![CI](https://github.com/wangkemax/Logistics-Smart-Solution/actions/workflows/ci.yml/badge.svg)](https://github.com/wangkemax/Logistics-Smart-Solution/actions)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/tests-396%20passed-brightgreen.svg)]()

> **从招标文件到完整投标方案的全流程 AI 系统** — RFP解析 → Assumption治理 → 设备匹配 → 方案生成 → 财务ROI → DOCX/PPTX导出。

**产品定位：物流售前推进系统（Presale OS）**，不是参数计算器，而是先理解项目、再生成方案、自动测算ROI、端到端交付文档的完整 copilot。

---

## 🎯 系统能力

| 能力 | 说明 | 版本 |
|------|------|------|
| **RFP 解析** | 上传 PDF 或粘贴文本，LLM 提取 16 个结构化字段，识别置信度，生成澄清问题 | v1.3 |
| **Assumption 治理** | 假设注册表 + 版本化 + 可追溯，支持 override/rollback，7条 QA 校验规则 | v0.9 |
| **参数库** | 行业默认参数 / 区域成本指数 / overhead系数，多键优先级匹配 | v0.9 |
| **设备库（Equipment DB）** | SQLAlchemy 设备库（AMR/GTP/ASRS/Shuttle/Conveyor/Sorter），支持按吞吐量匹配 | v1.1 |
| **设备-场景 DI** | Workspace 快照自动注入匹配设备，提案引用真实设备参数 | v1.1 |
| **Base Solution** | 5级行业体系（AUTOMOTIVE/ELECTRONICS/FMCG/MANUFACTURING/GENERIC_3PL），8个section结构化方案 | v0.7 |
| **Clarification** | P0/P1/Conflict/Assumption 四类澄清，自动生成问题清单，Workspace补录闭环 | v0.7 |
| **Workspace 快照** | Workspace 生命周期管理，版本快照，Dirty追踪，Context统一管理 | v1.0 |
| **提案生成** | LLM 生成执行摘要/核心方案/实施计划（MiniMax, temperature=0.3），QA冲突阻断 | v1.0 |
| **Financial ROI** | CAPEX汇总 + OPEX分解 + ROI/IRR/Payback + 现金流量表（牛顿法IRR） | v1.2 |
| **DOCX 导出** | python-docx，中文字体，附录含假设清单，支持 Microsoft Word 直接编辑 | v1.0 |
| **PPTX 导出（Marp）** | Markdown→Marp→PPTX，支持3种主题，长内容自动分页，优雅降级 | v1.4 |
| **方案对比（Diffing）** | 两 Workspace 版本参数+成本差异对比，数值字段自动计算百分比变化 | v1.4 |
| **PDF 报告** | Jinja2 + WeasyPrint，9章节专业投标建议书，中英双语 | v0.7 |
| **Pipeline 编排** | 异步非阻塞，实时状态追踪，Clarification修正后重跑，SQLite持久化 | v0.7 |

---

## 🏗 系统架构

```
用户界面（Streamlit）
    │
    ▼
FastAPI Backend
    │
    ├─ RFP Ingestion（v1.3）       → 招标文件解析 / 约束提取 / 澄清问题生成
    ├─ Assumption Service（v0.9）  → 假设注册 / 版本化 / QA校验
    ├─ Parameter Service（v0.9）     → 行业参数 / 成本指数 / overhead
    ├─ Equipment Service（v1.1）    → 设备库 / 吞吐量匹配 / CAPEX估算
    ├─ Workspace Manager（v1.0）   → 快照 / 版本控制 / Dirty追踪
    ├─ Proposal Engine（v1.0）      → LLM生成（执行摘要/方案/实施计划）
    ├─ Financial Service（v1.2）     → ROI / IRR / Payback / 现金流量表
    ├─ Pitch Renderer（v1.4）      → Marp Markdown → PPTX
    ├─ Diff Service（v1.4）        → Bid Scenario 对比
    └─ Document Renderer（v1.0）   → DOCX / Markdown 导出
```

**数据流：**
```
RFP → RFPExtractor → Assumptions → WorkspaceManager
                                    ↓
                          EquipmentService（设备匹配）
                                    ↓
                          ProposalEngine（LLM生成）
                                    ↓
                          FinancialService（ROI计算）
                                    ↓
                    DocumentRenderer（DOCX）/ PitchRenderer（PPTX）
```

---

## 📂 项目结构

```
backend/
├── api/
│   ├── workspace_api.py       # Workspace CRUD + 快照
│   ├── proposal_api.py         # 提案生成 + 预览
│   ├── document_api.py          # DOCX/PPTX 导出
│   ├── equipment_api.py         # 设备库查询 / 匹配
│   ├── financial_api.py        # 财务测算 / ROI
│   ├── rfp_api.py             # RFP 解析 / 澄清生成
│   └── diff_api.py            # Bid Scenario 对比
├── models/
│   ├── equipment_models.py      # Equipment SQLAlchemy 表
│   ├── financial_models.py     # FinancialSnapshot 表
│   └── workspace_models.py     # Workspace 表
├── schemas/
│   ├── workspace_schemas.py     # WorkspaceContext / WorkspaceCreate
│   ├── proposal_schemas.py      # SectionOutput / ProposalSections
│   ├── equipment_schemas.py    # EquipmentSchema / EquipmentMatchResult
│   └── financial_schemas.py    # FinancialInput / FinancialResult
├── services/
│   ├── workspace_manager.py     # Workspace 生命周期 + 快照 + 设备注入
│   ├── proposal_section_generator.py  # LLM Section 生成
│   ├── proposal_llm_service.py  # MiniMax API 封装
│   ├── equipment_service.py     # 设备库查询 / 匹配
│   ├── financial_service.py    # ROI / IRR / Payback 计算
│   ├── rfp_extractor.py        # RFP 解析 / 澄清问题生成
│   ├── pitch_renderer.py       # Marp Markdown → PPTX
│   ├── workspace_diff_service.py  # Bid Scenario 对比
│   └── document_renderer.py    # DOCX 渲染
data/
├── parameters/                 # assumption_defaults / cost_indices / industry_overhead CSVs
└── equipment_seed.sql        # 设备库初始数据（12条记录）
tests/                        # pytest 测试套件（396 tests）
```

---

## 🚀 快速启动

```bash
# 1. 克隆
git clone https://github.com/wangkemax/Logistics-Smart-Solution.git
cd Logistics-Smart-Solution

# 2. 安装依赖
pip install -e ".[dev]"

# 3. 初始化数据库（建表 + 设备数据）
python3 scripts/init_db.py

# 4. 启动后端
uvicorn backend.main:app --reload --port 8000

# 5. 启动前端
streamlit run frontend/dashboard/app.py --server.port 8501
```

> 访问 http://localhost:8501

---

## 📡 API 端点

### Workspace

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/workspaces` | 创建 Workspace |
| `GET` | `/api/workspaces/{id}` | 获取 Workspace |
| `POST` | `/api/workspaces/{id}/refresh` | 刷新快照 |
| `PATCH` | `/api/workspaces/{id}/fields` | 更新字段 |
| `POST` | `/api/workspaces/{id}/finalize` | 最终化 |
| `GET` | `/api/workspaces/{id}/context` | 获取 WorkspaceContext |

### Proposal

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/proposals/generate` | 生成提案文本 |
| `GET` | `/api/workspaces/{id}/preview/{section}` | 预览单个章节 |

### Document

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/documents/export` | 导出 DOCX/Markdown |
| `POST` | `/api/documents/export/pptx` | 导出 PPTX（Marp） |
| `GET` | `/api/documents/workspaces/{id}/document` | 预览文档 |

### Equipment

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/api/equipment/` | 设备列表（支持类型/吞吐量过滤） |
| `GET` | `/api/equipment/types` | 设备类型列表 |
| `GET` | `/api/equipment/match/{type}` | 按吞吐量匹配设备 |

### Financial

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/financial/calculate` | 财务测算 |
| `POST` | `/api/financial/calculate-and-save/{workspace_id}` | 测算并保存快照 |

### RFP

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/rfp/extract` | 从文本提取字段 |
| `POST` | `/api/rfp/extract/pdf` | 上传 PDF 提取 |
| `POST` | `/api/rfp/extract-and-clarify` | 完整管道：提取+澄清 |

### Diff

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/diff/workspaces` | 对比两个 Workspace |
| `GET` | `/api/diff/workspaces/{id}/versions` | 列出快照版本 |

---

## 🧪 测试

```bash
pytest tests/ -v
```

**当前：396 tests，3次连续闭环测试全部通过 ✅**

---

## 🗺️ Roadmap

| 版本 | 主题 | 状态 |
|------|------|------|
| **v0.7** | Base Solution Generator | ✅ 完成 |
| **v0.8** | Industry 5级分类 + 测试体系 | ✅ 完成 |
| **v0.9** | Assumption Governance + 参数库 | ✅ 完成 |
| **v1.0** | Proposal Studio + Workspace + DOCX | ✅ 完成 |
| **v1.1** | Equipment DB + Scenario-Equipment DI | ✅ 完成 |
| **v1.2** | Financial ROI Modeler | ✅ 完成 |
| **v1.3** | RFP Ingestion + Clarification Generator | ✅ 完成 |
| **v1.4** | Markdown→PPTX + Bid Scenario Diffing | ✅ 完成 |

---

## 📝 License

MIT
