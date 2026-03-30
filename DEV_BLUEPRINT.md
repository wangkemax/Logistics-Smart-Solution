# Logistics Smart Solution — 未来开发蓝图

> 基于 v0.6（Quality-Gated Foundation）架构，面向 AI Logistics Presale OS 的演进蓝图

---

## 核心理念升级

**从：** 提取工具 + 成本计算器
**到：** 完整售前推进系统

**目标链路：** 标书理解 → 缺失澄清 → 补录确认 → 多方案生成 → 成本测算 → 风险审查 → 文档输出

**核心原则：** 所有下游模块只能读 Understanding Engine 输出，任何模块不能绕过 schema / readiness / gate，所有关键计算都必须经过 downstream_input。

---

## 开发优先级（Max，2026-03-30）

> 不做更多功能，优先做更可信的中间层。

### 第一优先级：ProjectState 统一数据模型（阶段一，2~3周）

**目标：** 把 Understanding Engine 打造成"唯一事实层"，所有下游只读这个标准对象。

禁止任何模块直接读原始文本或各自"猜"字段。

**统一数据模型包含：**
- `project_state` — 项目总状态
- `field_traces` — 所有字段带状态（extracted / assumed / manual_confirmed / conflicted / missing）+ 来源（原文/规则/LLM/人工/默认假设）
- `analysis_sections` — 13维度分析文本
- `readiness` — 就绪度评估
- `clarification_log` — 澄清记录
- `downstream_input` — 下游标准输入

**强制架构约束：**
1. 定义统一的 ProjectState 数据模型
2. 所有字段都带状态和来源
3. 所有下游服务只接收 ProjectState 或 DownstreamInput
4. 严禁任何模块绕过这一层读取原始文本

### 第二优先级：Clarification 工作台标准化（阶段一）

**目标：** 做成真正的"售前推进工具"，而不是补丁页。

四类问题：
- **P0 必答** — 不答不能正式测算
- **P1 推荐补充** — 不答只能区间估算
- **Conflict 冲突确认** — 多处矛盾，必须选定口径
- **Assumption 假设确认** — 系统给默认值，用户接受或覆盖

每个问题都带：编号 / 字段名 / 为什么问 / 不回答影响什么 / 建议填写格式 / 单位口径提示 / 时间维度提示 / 是否影响 ROI

### 第三优先级：Solution Studio 三层化（阶段二，3~6周）

把"15种自动化场景评分"升级为完整解决方案体系：

- **BaseSolutionGenerator** — 仓网规划、流程、人力配置、KPI、系统边界
- **ImprovementSolutionGenerator** — 波次策略、拣选优化、库存精度、流程标准化
- **AutomationSolutionGenerator** — AMR、AGV、AS/RS 等（允许输出"当前不建议自动化"）

统一输出结构：方案名称 / 适用条件 / 核心设计 / 人力思路 / 系统设备需求 / 风险点 / 实施复杂度 / 成本级别 / ROI适配性 / 不适用原因

### 第四优先级：Assumption Governance（阶段三）

五类参数库：
1. 行业默认参数库（订单结构/峰值系数/退货率）
2. 区域成本参数库（人工/租金/水电/设备维护）
3. 自动化适配规则库（SKU数/订单量/峰值波动）
4. 方案假设模板库
5. 版本化参数来源库（每条参数带版本/生效时间/适用边界）

### 第五优先级：Proposal Studio 证据链文档（阶段三）

四类输出：投标分析报告 / 客户交流版方案书 / 正式投标正文草稿 / PPT大纲

每段文字可追溯：字段来源 / 假设来源 / 方案对象 / 成本结果 / 澄清记录

### 阶段一：未来2~3周（稳）

目标：把"能跑"变成"跑得稳"

重点任务：
- 统一 ProjectState / DownstreamInput
- Clarification Questions 标准结构
- 手工补录写回
- 冲突字段确认
- readiness 重算
- 文档版本漂移修复
- 补齐核心测试（字段解析/gate判定/clarification回写/range/block/pass切换）

### 阶段二：未来3~6周（方案）

目标：自动化推荐器 → 方案系统

重点任务：
- 三类方案生成器落地
- 多方案对比从设备扩展到运营/优化/自动化
- 成本模型按方案类型适配
- 引入"不建议自动化"结论路径
- 加入风险、复杂度、实施阶段建议

### 阶段三：未来6~10周（平台）

目标：方案系统 → 可沉淀的售前工作平台

重点任务：
- 假设治理
- 区域/行业参数库
- 案例库结构化
- 文档输出矩阵化
- 项目工作区/版本管理/审计日志

### 暂时不做

1. 不优先继续扩 UI 花样（图表已够，中间层还需更稳）
2. 不优先扩更多 Agent（先把单体业务内核打稳）
3. 不优先做大而全知识库检索（先做参数库+假设库+案例结构化库）

---

## 四层架构

### 第 1 层：Understanding Engine（已实现 v0.2/v0.6）

把原始标书转成可信的、可治理的项目状态。是系统的"真相层"。

包含：标书解析 · 字段对象化 · 13维分析结构 · Readiness判定 · 澄清问题生成 · downstream_input生成 · Cost Model Gate · Benchmark

### 第 2 层：Clarification & Input Layer（→ v0.6.1）

把缺失项、歧义项、冲突项推进成"已补齐、已确认、可继续工作"的状态。

模块：
- **Clarification Manager** — 把问题转成可回答的澄清问题
- **Input Capture Manager** — 把用户补录写回系统，重新触发 readiness 计算

### 第 3 层：Solution Layer（→ v0.7）

从"分析系统"变成"售前系统"的关键层。输出完整物流解决方案，不是单一自动化方案。

三个子模块：
- **Base Solution Generator** — 基础方案（运营模式/流程/人力模型/KPI）
- **Improvement Solution Generator** — 优化方案（精益改善/流程优化/效率提升）
- **Automation Solution Generator** — 自动化方案（适配判断/设备组合/ROI/分阶段实施）

真实售前逻辑：先有基础方案 → 再谈优化 → 再判断自动化。

### 第 4 层：Proposal & Delivery Layer（→ v0.8）

把分析和方案变成可交付成果。

四类输出：
- 投标分析报告
- 客户交流版方案建议书
- 正式投标正文草稿
- PPT大纲 / 汇报稿

**文档生成原则：** 不能重新推理业务事实，只能基于已确认的结构化结果。

---

## 六产品模块

| 模块 | 定位 |
|------|------|
| **Tender Understanding Engine** | 真相层：解析/分析/schema/readiness/gate |
| **Clarification Studio** | 澄清工作流：问答/补录/冲突确认/假设确认/重算 |
| **Solution Studio** | 方案生成：基础/优化/自动化三类方案+多方案对比 |
| **Cost Modeling Studio** | 成本测算：正式测算/区间估算/敏感性分析 |
| **Proposal Studio** | 文档输出：报告/方案书/PPT大纲/摘要页 |
| **Benchmark & QA Center** | 质量保障：benchmark/误放行率/输出质量评分/模块回归 |

---

## 历史版本路线图（参考）

### v0.6 — ✅ 已完成（Quality-Gated Foundation）

- 结构化理解（tender_understanding）
- Readiness 门禁
- downstream_input 三模式
- Cost Model Gate
- Benchmark 系统
- Readiness Card UI
- UI Clarity Patch

---

### v0.6.1 — Clarification Workflow（下一步）

**目标：** 从"发现问题"升级到"推动问题解决"。

**核心能力：**
- Clarification Questions 结构标准化（Q-001编号，severity/why/impact/suggested_format）
- 按 P0 / P1 / P2 分类展示
- 支持手工逐项补录
- 支持冲突字段选择确认
- 支持单位/口径/时间维度提示
- 补录后自动重算 readiness
- 更新 downstream_input
- 记录"原文值/假设值/人工确认值"

**优先级规则（写死）：**
```
manual_confirmed > extracted_provided > assumed
```

**新增模块：**
- `clarification_manager.py`
- `input_capture_service.py`
- `manual_input_schema.py`
- `field_resolution_service.py` — 合并多来源字段为最终值
- `recompute_project_state()` — 统一重算入口

**前端页面：Clarification Workspace**

区域：
- A. 当前状态（Mode / Readiness条 / P0/P1/P2统计）
- B. 必填问题区（只显示P0和blocked项）
- C. 冲突确认区（合同年限/DC数量等冲突项）
- D. 可选补录区（显示P1项）
- E. 提交并重新计算（刷新项目状态）

---

### v0.7 — Solution Studio

**目标：** 基于结构化理解结果，自动生成完整物流解决方案。

**核心能力：**
- 基础物流方案生成
- 优化型方案生成
- 自动化方案生成
- 多方案并排对比
- 每个方案的：适用条件/关键假设/主要风险/实施复杂度/成本级别/是否适合ROI测算

**方案输出结构（每类方案统一）：**
- 方案名称
- 适用场景
- 前提条件
- 核心设计
- 人员配置思路
- 系统/设备需求
- 风险点
- 实施复杂度
- 成本级别
- ROI适配性

**新增模块：**
- `solution_orchestrator.py`
- `base_solution_generator.py`
- `improvement_solution_generator.py`
- `automation_solution_generator.py`
- `solution_compare.py`

---

### v0.7.5 — Assumption Governance

**目标：** 所有区间估算和方案推理中的假设，都有规则来源。

**核心能力：**
- 假设模板库
- 行业默认参数库
- 区域人工成本库
- 峰值系数规则库
- 自动化适配条件库
- 假设来源与版本记录

**每个假设必须带：**
- 假设值
- 来源
- 适用行业
- 适用区域
- 适用场景
- 是否允许覆盖
- 最后更新时间

**新增模块：**
- `assumption_registry.py`
- `industry_defaults.py`
- `regional_parameters.py`
- `automation_rules.py`

---

### v0.8 — Proposal Studio

**目标：** 把分析/方案/成本/风险整合成可直接用于售前的文档输出。

**核心能力：**
- 投标分析报告生成
- 方案建议书生成
- 自动化ROI报告生成
- PPT大纲生成
- 一页式项目摘要生成

**文档生成原则：** 所有文本必须引用已确认结构（analysis_sections / downstream_input / selected_solution / cost_result / clarification_log），不能自己重新发明事实。

**新增模块：**
- `proposal_composer.py`
- `report_builder.py`
- `ppt_outline_builder.py`
- `executive_summary_builder.py`

---

### v0.9 — Project Workspace

**目标：** 支持按项目维度持续迭代，团队协作、反复打磨、长期沉淀。

**核心能力：**
- 项目主页
- 原始文件管理
- 分析结果版本历史
- 澄清记录历史
- 假设变更记录
- 方案版本管理
- 成本测算版本管理
- 文档草稿管理

**新增模块：**
- `project_workspace.py`
- `version_manager.py`
- `artifact_registry.py`
- `audit_log_service.py`

---

## 目标代码目录结构

```
backend/
  core/
    tender_understanding.py    # orchestrator
    tender_schema.py           # FieldDef注册表/STATUS/P0-P2映射
    tender_readiness.py        # readiness门禁
    tender_clarification.py    # 澄清问题生成

  downstream/
    downstream_input_builder.py      # 唯一入口
    cost_model_requirements.py       # P0/P1/P2分层+假设模板
    field_resolution_service.py      # 多来源字段合并

  clarification/
    clarification_manager.py         # 澄清问题→可回答问题
    input_capture_service.py          # 用户补录写回
    manual_input_schema.py            # 人工输入结构
    recompute_pipeline.py             # 重新计算入口

  solution/
    solution_orchestrator.py          # 方案编排
    base_solution_generator.py         # 基础方案
    improvement_solution_generator.py  # 优化方案
    automation_solution_generator.py  # 自动化方案
    solution_compare.py               # 多方案对比

  cost/
    cost_service.py                   # 三模式计算
    assumption_registry.py            # 假设治理

  proposal/
    proposal_composer.py              # 文档编排
    report_builder.py                 # 报告生成
    ppt_outline_builder.py            # PPT大纲
    executive_summary_builder.py      # 摘要页

  workspace/
    project_workspace.py              # 项目空间
    version_manager.py                # 版本管理
    artifact_registry.py              # 产出物注册
    audit_log_service.py              # 审计日志

  benchmarks/
    compare_extractors.py              # v0.2 vs Legacy
    compare_downstream_modes.py        # 下游模式对比
```

---

## 立即可执行的 v0.6.1 清单

### 第一步：确定范围（只做这6件事）
1. Clarification Questions 结构标准化
2. 支持前端逐项补录
3. 支持冲突字段选择确认
4. 支持人工输入值写回项目状态
5. 自动重算 readiness / downstream_input
6. 前端标记 manual_confirmed

### 第二步：新增数据结构
```python
{
  "manual_inputs": {
    "daily_orders": {
      "value": 1200,
      "unit": "orders/day",
      "source": "user_input",
      "status": "manual_confirmed",
      "updated_at": "2026-03-29T20:00:00"
    }
  }
}
```

### 第三步：字段合并器
`field_resolution_service.py` — 合并多来源（原文提取/系统假设/人工补录/冲突确认）为统一结果

### 第四步：重算统一入口
`recompute_project_state(project_id)` — 读取原始解析→合并manual inputs→更新required_inputs→重算readiness→重建downstream_input→触发cost mode判断

### 第五步：Clarification Workspace 前端
5块：当前状态 / 必填问题区 / 冲突确认区 / 可选补录区 / 提交并重新计算

---

## 版本演进总结

| 版本 | 主题 | 核心价值 |
|------|------|---------|
| v0.2 | Quality-Gated Foundation | 可信理解底座 |
| v0.6 | QA规则引擎+UI | 质量门禁可视化 |
| **v0.6.1** | **Clarification Workflow** | **从拦截到推动** |
| v0.7 | Solution Studio | 从分析到打法 |
| v0.7.5 | Assumption Governance | 假设可信度 |
| v0.8 | Proposal Studio | 从能力到交付 |
| v0.9 | Project Workspace | 从工具到系统 |

---

*此蓝图由 Max 王珂 于 2026-03-29 主持制定*
