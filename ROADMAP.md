# Roadmap — Logistics Smart Solution

> **愿景：** 物流售前推进系统（Presale OS）— 从招标文件到完整投标方案的全流程 AI 自动化平台。

---

## 当前状态：v1.4 ✅

系统已实现端到端闭环：**RFP 解析 → Assumption 治理 → 设备匹配 → 方案生成 → 财务 ROI → DOCX/PPTX 导出 → 方案对比**。

199 commits · 396 tests · 47 API 端点 · 19 个服务类 · 真实项目验证（保时捷 PDC 仓配一体化）。

---

## 系统架构

```
招标文件 / 客户需求
     ↓
RFP Ingestion（LLM + Rules 混合提取）
     ↓
Assumption Governance（假设注册 / 版本化 / QA 校验）
     ↓
Equipment Matching（设备库按吞吐量匹配）
     ↓
Proposal Generation（LLM 分章节生成）
     ↓
Financial ROI（CAPEX + OPEX + IRR + 现金流量表）
     ↓
Document Export（DOCX / PPTX / PDF / Markdown）
     ↓
Bid Scenario Diffing（A/B 方案对比）
```

---

## 未来规划

### v1.5 — 数据闭环与知识沉淀（Data Flywheel）

> **核心目标：** 让系统从"一次性生成器"变成"有记忆的售前伙伴"。

**Win/Loss Tracking**
- [ ] 投标项目结果录入（中标/未中标/弃标）+ 结构化原因标签
- [ ] 项目全生命周期记录：RFP → 方案 → 投标 → 结果 → 复盘

**Case Reuse Engine**
- [ ] 相似项目检测（按行业 / 面积 / SKU / 自动化程度匹配）
- [ ] 方案 Baseline 复用（新项目自动借鉴历史最佳方案）
- [ ] 成本 Benchmark（行业参考成本对标，标记偏离历史均值的异常值）

**参数自动校准**
- [ ] 用实际项目数据反向修正 assumption_defaults 和 cost_indices
- [ ] 参数偏差报告（实际值 vs 假设值的偏差分析）

**退出标准：** 新建项目时，系统能自动推荐 Top-3 相似历史案例及其中标方案。

---

### v1.6 — 多方案优化（Multi-Scenario Optimization）

> **核心目标：** 从"生成一个方案"升级为"自动生成多个差异化方案并优选"。

**Scenario Generator**
- [ ] 自动生成 2~3 个差异化方案（保守 / 推荐 / 激进）
- [ ] 每个方案有不同自动化程度、设备组合、投资规模

**ROI Optimization AI**
- [ ] 给定预算约束，搜索设备组合最优解（maximize ROI 或 minimize Payback）
- [ ] 约束优化算法（线性规划 / 遗传算法 / 贝叶斯优化）

**Sensitivity Analysis**
- [ ] 关键参数灵敏度分析（人工成本 ±20%、货量波动 ±30%、设备利用率）
- [ ] 一键生成龙卷风图（Tornado Chart），展示参数变化对 ROI 的影响排序

**Scenario Comparison Dashboard**
- [ ] 前端 3 方案并排对比（财务 / 设备 / 实施计划 / 风险）
- [ ] 交互式方案调参（拖动滑块实时刷新 ROI）

**退出标准：** 输入一份 RFP，系统 5 分钟内输出 3 个差异化方案 + 灵敏度分析。

---

### v1.7 — 智能交互与协作（Conversational Copilot）

> **核心目标：** 从"填表驱动"升级为"对话驱动"的售前协作体验。

**Conversational Interface**
- [ ] 自然语言追问与调参（"把 AMR 减半看看 ROI"、"换成 Shuttle 方案"）
- [ ] 上下文记忆：跨轮次保持项目状态

**Multi-Agent Architecture**
- [ ] 将各服务封装为可协作的 Agent（Extractor / Architect / Financial / Writer / QA）
- [ ] Agent 间上下文传递与任务协调（替代当前 1075 行单体 orchestrator.py）
- [ ] 失败重试策略与 Agent 级别的错误恢复

**Collaboration Features**
- [ ] 多人协作编辑 Workspace（评论 / 审批 / @提及）
- [ ] 版本对比 + 变更通知

**Tender Strategy AI**
- [ ] Bid/No-bid 智能推荐（基于历史胜率 + 资源投入 + 竞争格局）
- [ ] 项目评分卡（自动评估胜率和投入产出比）

**退出标准：** 售前顾问通过对话完成方案调整，无需手动修改参数表。

---

### v2.0 — 平台化（Platform）

> **核心目标：** 从"单机工具"进化为"多团队 SaaS 平台"。

**Layout Generation AI**
- [ ] 输入仓库尺寸 + 自动化方案，AI 生成仓库布局示意图
- [ ] 未来支持 CAD / DWG 导出

**Multi-tenant SaaS**
- [ ] 多团队 / 多客户独立运作
- [ ] 权限管理（Admin / 售前经理 / 售前顾问）

**Plugin System**
- [ ] 多 LLM 支持（当前仅 MiniMax，需支持 Claude / GPT / DeepSeek 等）
- [ ] 设备供应商数据库插件（不同供应商接入各自的设备参数）

**Knowledge Graph**
- [ ] 项目案例 + 设备参数 + 行业 know-how 构建知识图谱
- [ ] 语义检索（替代当前的关键词匹配）

---

## 技术债务

### 高优先级
- [ ] **RFP 测试 Mock 化** — 4 个 `test_rfp_extractor` 用例依赖外部 LLM API，无 key 时直接 fail，需加 mock/fixture
- [ ] **orchestrator.py 拆分** — 1075 行单体文件，需拆为 pipeline_runner / stage_executor / state_manager
- [ ] **Deprecation Warnings 清理** — `datetime.utcnow()` → `datetime.now(UTC)`；Pydantic class-based config → `ConfigDict`（当前 175 warnings）

### 中优先级
- [ ] `project_service.py`（120 行）拆分为 `recommendation_service.py` + `cost_service.py`
- [ ] RESTful 统一错误码规范（当前各 API 错误格式不一致）
- [ ] API 限流（`/api/pipeline/*` 防止滥用）

### 低优先级
- [ ] Docker 多阶段构建优化（当前镜像偏大）
- [ ] Streamlit session_state 持久化到 localStorage
- [ ] 单元测试覆盖率提升（当前 368 个 test function，未覆盖 document_renderer 边界 case）

---

## 已完成版本

> 每版本详细 changelog 见 [CHANGELOG.md](./CHANGELOG.md)。

| 版本 | 主题 | 日期 | 关键交付 |
|------|------|------|----------|
| **v1.4** | Pitch & Presentation | 2026-04-02 | Marp Markdown→PPTX（3种主题）· Bid Scenario Diffing |
| **v1.3** | RFP Ingestion | 2026-04-02 | RFP 文本/PDF 解析（16字段）· Clarification Generator |
| **v1.2** | Financial ROI Modeler | 2026-04-02 | CAPEX/OPEX · ROI/IRR/Payback · 现金流量表 |
| **v1.1** | Equipment Database | 2026-04-02 | SQLAlchemy 设备库（6类12条）· 吞吐量匹配 · DI |
| **v1.0** | Proposal Studio | 2026-04-02 | Workspace 生命周期 · LLM 分章节 · DOCX 导出 |
| **v0.9** | Assumption Governance | 2026-04-01 | 假设注册表 · 版本化/rollback · 参数库 |
| **v0.8** | Industry Classification | 2026-04-01 | 5级行业体系 · 回归测试框架 |
| **v0.7** | Base Solution Generator | 2026-03-31 | 8 section 结构化方案 · Markdown 导出 |
| **v0.6** | QA Engine + UX | 2026-03-29 | 声明式规则引擎 · Clarification · Operation Model |
| **v0.5** | LLM Extractor | 2026-03-28 | MiniMax/OpenAI 双接口 · 混合提取 |
| **v0.4** | Advanced UI | 2026-03-28 | 雷达图 · QA 修正面板 · ROI 对比 |
| **v0.3** | Task Persistence | 2026-03-28 | SQLite 任务存储 · 历史列表 · 阶段重试 |
| **v0.2** | Async Pipeline | 2026-03-28 | 非阻塞执行 · 5步实时状态 · 三栏UI |
| **v0.1** | MVP | 2026-03-28 | 15种场景推荐 · 成本ROI · PDF报告 |

---

## 验证报告（2026-04-08）

基于代码库完整审计的验证结果：

**✅ 通过项：**
- 199 commits · 396 tests（392 passed + 4 LLM-dependent）· 47 API 端点
- 所有 v0.1~v1.4 声明功能均有对应实现代码和测试覆盖
- 真实项目数据验证通过（保时捷 PDC、医药冷链）

**⚠️ 待修复：**
- 4 个 RFP 测试因无 LLM API Key 失败（测试隔离问题）
- 175 个 deprecation warnings（datetime.utcnow + Pydantic V2）
- orchestrator.py 1075 行未拆分
- project_service.py 120 行技术债未清理

**📋 原规划未实现（已归入后续版本）：**
- Knowledge Base + Case Reuse Engine（原 Phase 2）→ 归入 v1.5
- Multi-Agent Architecture（原 Phase 3）→ 归入 v1.7

---

## 商业价值

| 能力 | 当前状态 | 目标状态（v2.0） |
|------|----------|------------------|
| 售前效率 | 单方案生成 5-10x 提速 | 多方案 + 优选 + 对话调参 |
| 知识沉淀 | 参数库 + 设备库 | 案例库 + 知识图谱 + 自动校准 |
| 投标质量 | LLM 生成 + QA 校验 | 历史中标方案学习 + 策略推荐 |
| 团队协作 | 单用户 Streamlit | 多人协作 + 审批流程 |

---

## License

MIT
