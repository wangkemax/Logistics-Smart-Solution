# Changelog — Logistics Smart Solution

所有版本的详细变更记录。格式参考 [Keep a Changelog](https://keepachangelog.com/)。

---

## v1.4 — Pitch & Presentation（2026-04-02）

**Markdown→PPTX（Marp 方案）**
- Marp Markdown 渲染器，支持 3 种主题（default / minimal / corporate）
- 幻灯片结构：封面 → 执行摘要 → 核心方案 → 财务测算 → 实施计划 → 附录
- 长内容自动分页，优雅降级

**Bid Scenario Diffing**
- 两 Workspace 版本参数 + 成本差异对比
- 数值字段自动计算百分比变化
- 财务关键字段高亮（ROI / CAPEX / Payback / IRR）

---

## v1.3 — RFP Ingestion（2026-04-02）

- RFP 文本 / PDF 上传解析，LLM 提取 16 个结构化字段
- 置信度识别 + 缺失字段检测
- Clarification Generator：自动生成 P0/P1/Conflict/Assumption 四类澄清问题清单
- 与 Assumption Defaults 对比，识别异常值

---

## v1.2 — Financial ROI Modeler（2026-04-02）

- CAPEX 汇总：设备 + 10% 工程 + 5% 软件
- OPEX 分解：人力节省 / 仓储 / 水电 / 维保
- ROI / IRR / Payback Period 计算（牛顿法 IRR）
- 5 年现金流量表
- FinancialSnapshot SQLAlchemy 表，快照持久化

---

## v1.1 — Equipment Database（2026-04-02）

- SQLAlchemy 设备库：AMR / GTP / ASRS / Shuttle / Conveyor / Sorter（12 条种子数据）
- 字段：CAPEX / 吞吐量 / 载重 / 速度 / 能耗 / MTBF / 维保成本 / 占地面积
- 按吞吐量匹配设备 API
- Scenario-Equipment DI：Workspace 快照自动注入匹配设备，提案引用真实设备参数

---

## v1.0 — Proposal Studio（2026-04-02）

- **Workspace Context API** — WorkspaceManager + SQLAlchemy model + REST endpoints
- **Workspace 生命周期**：创建 → 刷新快照 → 更新字段 → 最终化
- **Proposal Section Generator** — LLM 生成执行摘要 / 核心方案 / 实施计划（MiniMax, temperature=0.3）
- **QA 冲突阻断**：QA 未通过时阻止生成
- **DOCX Export** — python-docx，中文字体支持，附录含假设清单
- Dirty 追踪 + 版本快照

---

## v0.9 — Assumption Governance + 参数库（2026-04-01）

- 假设注册表（Assumption Registry）— 版本化 / context_tags / source_type
- 假设 override / rollback 支持
- 参数库（Parameter Library）：
  - assumption_defaults.csv（行业默认参数）
  - cost_indices.csv（区域成本指数）
  - industry_overhead.csv（行业 overhead 系数）
- 多键优先级匹配
- 7 条 QA 校验规则（互斥 / 时间效力 / 离群检测）

---

## v0.8 — Industry Classification（2026-04-01）

- 5 级行业体系：AUTOMOTIVE / ELECTRONICS / FMCG / MANUFACTURING / GENERIC_3PL
- 行业回归测试框架
- 行业参数联动（不同行业自动加载对应默认参数）

---

## v0.7 — Base Solution Generator（2026-03-31）

### v0.7.0 — Base Solution Core
- solution_schema.py: BaseSolution + 8 个 section Pydantic 模型
- solution_context_builder.py: 统一 context 构建器
- solution_section_builders.py: 8 个 section 结构化生成器
- solution_narrative_builder.py: 中文业务表述生成器
- base_solution_generator.py: 总 orchestrator
- solution_api.py: POST/GET /api/solution/base/{pipeline_id}
- Frontend: Base Solution Studio 页面（8 大 section 完整展示）
- DB: PipelineRun.base_solution_json 持久化

### v0.7.1 — Base Solution Quality Patch
- Markdown 导出端点: GET /api/solution/base/{pipeline_id}/markdown
- 修复 complexity score 封顶 20 分（temperature_control 双重计数 bug）
- 样板案例: 保时捷 PDC（仓配一体化）+ 医药冷链仓配中心
- Clarification Workspace: UTC→CST 时间戳转换

---

## v0.6 — QA 规则引擎 + 体验优化（2026-03-29）

### v0.6.0 — QA Engine Core
- QA v2 声明式规则引擎（Field / ROI / Constraint 三类）
- 7 条 ROI 财务规则（roi_too_high / payback_too_fast / negative_saving 等）
- 9 条约束冲突矩阵（FIFO↔Drive-in / 低预算↔ASRS / 高吞吐↔人工 等）
- QA 三级判定：FAIL / CONDITIONAL_PASS / PASS
- Dashboard QA 面板：✔/⚠/✖ 状态 + P0/P1/P2 可折叠问题列表
- 置信度进度条 + PDF 在线预览 + 历史任务完整加载

### v0.6.1 — Clarification UX
- Clarification Workspace tab
- Per-field task cards with guidance text
- Submit and recompute pipeline

### v0.6.2 — Quality Gate Stability
- Schema/CostModel field priority sync 修复
- 保时捷 PDC 真实项目闭环验证

### v0.6.3 — Downstream Explainability
- Blocking Reasons Panel / Assumptions Used Panel
- Resolved Inputs Summary（provided / assumed / missing / unusable）

### v0.6.4 — Service Scope Structuring
- SERVICE_MATRIX constant（5 categories, 22 service items）
- service_scope type: string → dict matrix
- Frontend checkbox matrix UI

### v0.6.5 — Operation Model Derivation
- OperationProfile + LaborModules pydantic schemas
- 5 derivation functions（complexity / labor / operation_type / narrative）
- Frontend ⚙️ Operation Model panel

### v0.6.6 — Labor & Process Modeling
- 7 个标准仓库作业流程模板（50+ 步骤）
- build_process_modules() 基于 labor_modules 激活流程

### v0.6.7 — Integration Validation Patch
- DB migration: operation_profile_json + base_solution_json columns
- 修复 manual_inputs 覆盖 / narrative 重复 / cost narrative 错误提示

---

## v0.5 — LLM Extractor（2026-03-28）

- MiniMax API 调用 + OpenAI-compatible API（gpt-4o-mini）
- 结构化 JSON 提取 Prompt
- LLM + 增强正则混合方案（`use_llm` 参数控制）
- 置信度评分 → `extraction_confidence` 字段
- 异常字段提示 + 手动补充界面
- SQLAlchemy 2.x + Pydantic 2.x 弃用警告消除

---

## v0.4 — Advanced UI（2026-03-28）

- 权重滑块拖动实时刷新
- 雷达图多维对比可视化
- Tender 文件预览关键字段检测
- QA 修正面板（CONDITIONAL_PASS / FAIL）
- ROI 对比 + 阶段重试 UI

---

## v0.3 — Task Persistence（2026-03-28）

- Pipeline 任务写入 SQLite
- 历史任务列表 API（GET /api/pipeline/history）
- 前端历史任务列表页面
- 单 Step 重试按钮 + stage retry 逻辑

---

## v0.2 — Async Pipeline + UI 升级（2026-03-28）

- 异步 Pipeline（后台线程，非阻塞，5 步实时状态）
- SQLite 状态存储（刷新页面不丢失）
- 三栏 Pipeline Run UI（左输入 / 中状态 / 右结果）
- 中途参数修正（低置信度时支持 PATCH）
- PDF 下载接口

---

## v0.1 — MVP（2026-03-28）

- 自动化场景推荐引擎（15 种场景）
- 成本测算 + ROI 计算
- PDF 方案报告生成（Jinja2 + WeasyPrint）
- FastAPI 后端 + Streamlit 前端
- SQLite 数据库
