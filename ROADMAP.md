# Roadmap — Logistics Smart Solution v1.0

> **愿景：** 物流解决方案 AI 平台，从招标文件到完整投标方案的全流程自动化。

---

## 系统目标形态（v1.0）

```
招标文件 / 客户需求
     ↓
Requirement Extraction (LLM + Rules)
     ↓
Automation Opportunity Analysis
     ↓
Solution Generation
     ↓
Cost & Financial Model
     ↓
Scenario Comparison
     ↓
QA Gate
     ↓
Proposal Generation
```

**最终输出：** 自动化方案 · ROI/EBITA · 多方案对比 · 标准化 Proposal · 可复用案例库

---

## 目标架构

```
┌─────────────────────────────────┐
│         Frontend                │
│  Dashboard / Report UI          │
└──────────────┬──────────────────┘
               │
┌──────────────▼──────────────────┐
│         API Layer               │
│  FastAPI Gateway               │
└──────────────┬──────────────────┘
               │
┌──────────────▼──────────────────┐
│       Business Services         │
│  solution / cost / qa          │
└──────────────┬──────────────────┘
               │
┌──────────────▼──────────────────┐
│       AI Agent Layer            │
│  architect / writer / QA        │
└──────────────┬──────────────────┘
               │
┌──────────────▼──────────────────┐
│        Engine Layer             │
│  recommendation / cost         │
└──────────────┬──────────────────┘
               │
┌──────────────▼──────────────────┐
│      Data & Knowledge          │
│  scenarios / cases / KB        │
└─────────────────────────────────┘
```

---

## Phase 1（当前阶段 → v0.6）— 打通完整业务闭环

### 目标：需求输入结构化 + QA Gate 升级 + Pipeline Retry

**1. LLM Requirement Extraction（最大短板）**

当前痛点：需求输入结构化能力不足。

```
Tender Document
     ↓
LLM Extractor（规则 + LLM hybrid）
     ↓
Structured Requirement
```

提取字段：`warehouse_area` · `sku_count` · `order_profile` · `labor` · `industry` · `constraints` · `automation_intent`

- 规则：稳定、可控
- LLM：理解复杂语义
- 混合：取长补短

**2. QA Gate 升级**

从简单检查升级为三级判断：

| 判断 | 行为 |
|------|------|
| `PASS` | Pipeline 继续 |
| `CONDITIONAL_PASS` | 标记风险项，继续生成报告 |
| `FAIL` | 返回修正，不生成报告 |

QA 检查项：
- [x] `missing required input` — 已有（缺失 P0 字段检测）
- [ ] `ROI unrealistic` — 数值逻辑校验
- [ ] `constraint conflict` — 约束冲突检测
- [ ] `solution mismatch` — 方案与需求不匹配

**3. Pipeline Retry**

支持：
- [x] FAIL → 修正 → 重跑（已完成）
- [x] 阶段重跑（已完成：`extract` / `recommend` / `cost` / `report` / `qa`）
- [ ] stage resume 持久化（已在 UI 实现，需后台支持）
- [ ] retry limit 计数
- [ ] retry history 日志

### v0.6 子任务

- [x] `pipeline_status == "COMPLETE"` 完成判断修复
- [x] 置信度进度条 UI（progress bar + 高/中/低标签）
- [x] PDF 报告在线预览（base64 iframe + 下载按钮并列）
- [x] 历史任务列表完整加载（全部 session 字段 + `qa_issues` API 修复）
- [x] ROI unrealistic 检查规则（7条 ROI 财务规则，规则引擎架构）
- [x] Constraint Conflict 检测（9条约束冲突矩阵）
- [x] QA v2 规则引擎（Field Rules + ROI Rules + Constraint Rules）

---

## Phase 2（v0.7）— 系统开始具备学习能力

### 新增模块：Knowledge Base + Case Reuse Engine

**Knowledge Base**

存储：
```
knowledge/
  scenarios.json    # 自动化场景库
  equipment.json    # 设备参数库
  case_library.json # 历史项目案例
```

未来升级：Vector Database（推荐 LanceDB 或 Qdrant）

**Case Reuse Engine**

- [ ] similar project detection（按行业/面积/SKU 匹配）
- [ ] solution baseline reuse（新项目借鉴历史方案）
- [ ] cost benchmark（行业参考成本对标）

---

## Phase 3（v0.8）— 真正的 Multi-Agent 系统

当前 Agent 只是 YAML 定义。未来演进为可执行的 Agent 架构：

**Agent 角色：**
- CEO Agent（任务分发与协调）
- Tender Extractor（招标文件解析）
- Solution Architect（方案架构设计）
- Tender Writer（标书撰写）
- QA Agent（质量审核）

**执行流程：**
```
CEO Agent
     ↓
Tender Extractor → Requirement Structure
     ↓
Solution Architect → Solution Design
     ↓
Tender Writer → Proposal Draft
     ↓
QA Agent → Quality Gate
```

**关键能力：**
- [ ] task delegation（任务分发）
- [ ] agent communication（Agent 间通信）
- [ ] context sharing（上下文共享）
- [ ] retry strategy（失败重试策略）

---

## Phase 4（v0.9）— 自动化解决方案设计

**Solution Architect Agent**

自动设计：
- warehouse layout（仓库布局）
- automation architecture（自动化架构）
- equipment mix（设备组合）

输出：`solution architecture` · `equipment list` · `capacity estimation`

**Equipment Database**

建立设备库，覆盖：

| 设备 | CAPEX 范围 | 吞吐量 | 空间需求 |
|------|-----------|--------|---------|
| AMR | 50-200万 | — | — |
| GTP | 200-800万 | — | — |
| AS/RS | 500-2000万 | — | — |
| Shuttle | — | — | — |
| Conveyor | — | — | — |
| Sorter | — | — | — |

字段：`capex` · `throughput` · `space_requirement` · `energy` · `maintenance`

推荐引擎会变得更真实。

---

## Phase 5（v1.0）— AI Proposal System

系统可直接生成完整投标方案：

**输出：**
- [ ] PDF Proposal
- [ ] PPT Proposal
- [ ] 完整 solution design
- [ ] financial model（财务模型）
- [ ] timeline（实施时间线）
- [ ] implementation plan（实施计划）
- [ ] risk analysis（风险分析）

---

## AI 能力升级方向

| 方向 | 说明 |
|------|------|
| **ROI Optimization AI** | AI 自动优化设备组合/人工分配/自动化程度，目标是 maximize ROI |
| **Layout Generation AI** | 输入仓库尺寸 + 自动化方案，输出 layout diagram（未来支持 CAD） |
| **Tender Strategy AI** | 辅助售前判断是否值得投标，输出 bid/no-bid recommendation |

---

## 商业价值

当系统达到 v1.0 时：

| 能力 | 价值 |
|------|------|
| 售前自动化 | 输入客户需求，输出完整解决方案 |
| 售前效率 | 提升 5-10 倍 |
| 投标自动生成 | 输入 RFP，输出 Proposal，减少大量手工工作 |
| 知识沉淀 | 企业自动化方案知识库——非常重要的长期资产 |

---

## 技术债务

- [ ] 将 `project_service.py` 拆分为 `recommendation_service.py` + `cost_service.py`
- [ ] RESTful 统一错误码规范
- [ ] API 限流（`/api/pipeline/*` 防止滥用）
- [ ] Streamlit session_state 持久化到 localStorage
- [ ] Docker 多阶段构建优化
- [ ] 单元测试覆盖率提升

---

## 已完成版本

### v0.1 — MVP ✅
- 自动化场景推荐引擎（15 种场景）
- 成本测算 + ROI 计算
- PDF 方案报告生成（Jinja2 + WeasyPrint）
- FastAPI 后端 + Streamlit 前端
- SQLite 数据库

### v0.2 — 异步 Pipeline + UI 升级 ✅
- 异步 Pipeline（后台线程，非阻塞，5 步实时状态）
- SQLite 状态存储（刷新页面不丢失）
- 三栏 Pipeline Run UI（左输入 / 中状态 / 右结果）
- 中途参数修正（低置信度时支持 PATCH）
- PDF 下载接口
- 模板 None 防护

### v0.3 — 任务持久化 ✅
- [x] Pipeline 任务写入 SQLite
- [x] 历史任务列表 API（`GET /api/pipeline/history`）
- [x] 前端历史任务列表页面
- [x] 单 Step 重试按钮
- [x] stage retry 逻辑（含 `from_stage` 选择器）

### v0.4 — 高级 UI ✅
- [x] 权重滑块拖动实时刷新
- [x] 雷达图多维对比可视化
- [x] Tender 文件预览关键字段检测
- [x] QA 修正面板（CONDITIONAL_PASS / FAIL）
- [x] ROI 对比 + 阶段重试 UI
- [ ] 置信度进度条
- [ ] PDF 报告在线预览

### v0.5 — LLM Extractor ✅
- [x] MiniMax API 调用
- [x] OpenAI-compatible API 调用（gpt-4o-mini）
- [x] 结构化 JSON 提取 Prompt
- [x] LLM + 增强正则混合方案（`use_llm` 参数控制）
- [x] 置信度评分 → `extraction_confidence` 字段
- [x] 异常字段提示 + 手动补充界面
- [x] SQLAlchemy 2.x + Pydantic 2.x 弃用警告消除

### v0.6 — QA 规则引擎 + 体验优化 ✅
- [x] QA v2 声明式规则引擎（Field / ROI / Constraint 三类）
- [x] 7条 ROI 财务规则（roi_too_high / payback_too_fast / negative_saving 等）
- [x] 9条约束冲突矩阵（FIFO↔Drive-in / 低预算↔ASRS / 高吞吐↔人工 等）
- [x] QA 三级判定：FAIL / CONDITIONAL_PASS / PASS
- [x] Dashboard QA 面板：✔/⚠/✖ 状态 + P0/P1/P2 可折叠问题列表
- [x] 置信度进度条（progress bar + 高/中/低标签）
- [x] PDF 在线预览（base64 iframe + 下载按钮）
- [x] 历史任务完整加载（全部 session 字段）
- [x] `get_pipeline_run` 修复：`qa_issues` 顶层返回

### v0.6.x — Clarification & Quality Gate

#### v0.6.1 — Clarification UX ✅
- [x] Clarification Workspace tab in dashboard
- [x] Per-field task cards with guidance text
- [x] Submit and recompute pipeline
- [x] QA verdict card

#### v0.6.2 — Quality Gate Stability ✅
- [x] Fix schema/CostModel field priority sync (contract_years, service_scope)
- [x] Fix resolved field → downstream status mapping
- [x] Fix downstream_input not returned in API response
- [x] Schema field fixes: contract_years P0, service_scope P0
- [x] 保时捷PDC真实项目闭环验证

#### v0.6.3 — Downstream Explainability Patch ✅
- [x] Blocking Reasons Panel (mode=blocked)
- [x] Assumptions Used Panel (mode=range_estimate)
- [x] Resolved Inputs Summary (provided/assumed/missing/unusable 4格)
- [x] Expand to show provided fields with source section

#### v0.6.4 — Service Scope Structuring ✅
- [x] SERVICE_MATRIX constant (5 categories, 22 service items)
- [x] service_scope type: string → dict matrix
- [x] Frontend: checkbox matrix UI for service scope
- [x] downstream_input: _derived_labor flags from matrix
- [x] Backward compat: legacy flat format also supported

#### v0.6.5 — Operation Model Derivation ✅
- [x] OperationProfile + LaborModules pydantic schemas
- [x] operation_profile_service: 5 derivation functions
- [x] calculate_service_complexity() — score 0-20, low/medium/high
- [x] derive_labor_modules() — 7 team modules from service_scope
- [x] derive_operation_type() — warehouse/cold_chain/bonded/distribution
- [x] generate_operation_narrative() — Chinese business description
- [x] Frontend: ⚙️ Operation Model panel (type/complexity/labor/capabilities)
- [x] Integrated into recompute_service (Step 8b), written to DB
- [x] RecomputeResponse: operation_profile + labor_modules + narrative fields
- [x] 31/31 tests pass

#### v0.6.6 — Labor & Process Modeling ✅
- [x] process_templates.py: 7个标准仓库作业流程模板（50+步骤）
  - receiving_process / outbound_process / storage_management
  - return_process / va_process / temperature_control / support_process
- [x] build_process_modules() — 基于labor_modules激活流程
- [x] OperationProfile.process_modules 字段
- [x] Frontend: 📋作业流程模型面板（双列+步骤+角色+KPI）
- [x] 10 new tests (process_modules coverage)
- [x] docs/architecture/logistics_smart_solution_architecture.md

### v0.6.7 — Integration Validation Patch ✅
- [x] DB migration: operation_profile_json + base_solution_json columns added
- [x] Fix: manual_inputs字符串覆盖structured service_scope导致op推导失败
- [x] Fix: narrative重复文字（服务范围覆盖、服务类型标签）
- [x] Fix: full_calc模式下cost narrative错误提示"补录后可进入full_calc"
- [x] Fix: KPI narrative结尾重复句子

---

## v0.7 — Base Solution Generator ✅
### v0.7.0 — Base Solution Core ✅
- [x] solution_schema.py: BaseSolution + 8个section Pydantic模型
- [x] solution_context_builder.py: 统一context构建器
- [x] solution_section_builders.py: 8个section结构化生成器
- [x] solution_narrative_builder.py: 中文业务表述生成器
- [x] base_solution_generator.py: 总orchestrator
- [x] solution_api.py: POST/GET /api/solution/base/{pipeline_id}
- [x] Frontend: 🧩 Base Solution Studio页面（8大section完整展示）
- [x] DB: PipelineRun.base_solution_json持久化

### v0.7.1 — Integration Validation ✅
- [x] 完整链路验证: API → DB → 前端渲染
- [x] 保时捷PDC真实数据完整集成测试通过
- [x] 12项服务 / 6个团队模块 / 5个流程 / 14项KPI / 3阶段实施
- [x] Narrative边界质量验证（无凭空新增事实）

## v0.8 — Automation & Optimization Solutions（规划中）
- [ ] Automation Solution Generator
- [ ] Optimization Solution Generator
- [ ] Solution comparison matrix

## v0.9 — Tender Writer（规划中）
- [ ] Automated proposal PDF generation
- [ ] Multi-scenario tender document output
