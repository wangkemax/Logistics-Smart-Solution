# Base Solution Architecture — Three-Layer Solution Design

> **版本：** v0.8  
> **日期：** 2026-03-31  
> **状态：** 设计文档（未实现）  
> **用途：** `recommend_solutions` 重构路线图  
> **维护者：** 虾米

---

## 1. 背景与目标

### 1.1 当前状态

`recommend_solutions(profile)` 当前是一个**扁平评分模型**：

```
输入: project_state dict
输出: 15 个自动化场景评分（JSON + narrative）
       ↑ 这是 flat automation scoring，不是 solution design
```

存在的问题：
- 没有 operation mode / process design / labor model 等基础运营要素
- 评分只针对 Layer-3（自动化），无法支撑 Layer-1（基础运营）和 Layer-2（优化）
- 下游成本模型（CAPEX + ROI）缺乏基础运营参数输入
- 无法向客户呈现完整的端到端投标方案

### 1.2 目标架构

```
Layer 1: Base Solution    ← NEW (本设计文档)
  operation_mode + process_design + labor_model + KPI + system_boundary

Layer 2: Improvement      ← FUTURE
  process_optimisation + efficiency gains + lean analysis

Layer 3: Automation       ← EXISTING (evolve from flat scorer)
  AMR/AGV/AS/RS fit judgment + CAPEX + ROI
```

三层是**递进关系**，不是并行关系：
- Layer-1 是 Layer-2 和 Layer-3 的输入基础
- Layer-2 依赖 Layer-1 的 process_design 和 labor_model
- Layer-3 依赖 Layer-1 的 system_boundary 和 KPI targets

---

## 2. 三层方案的关系

### 2.1 Layer 1 → Layer 2 (Base → Improvement)

```
BaseSolution.operation_mode     → 确定哪些流程段有优化空间
BaseSolution.process_design     → 识别瓶颈环节（e.g. 拣选效率低）
BaseSolution.labor_model       → 确定人工成本基准（优化收益对比基准）
BaseSolution.kpi_framework      → 找到 KPI 差距（当前值 vs 目标值）
```

Improvement Solution 输出：
- 瓶颈分析报告
- 效率提升建议（layout 优化 / SOP 调整 / 排班优化）
- 预期人工节省（人天/月）

### 2.2 Layer 1 → Layer 3 (Base → Automation)

```
BaseSolution.system_boundary    → 自动化设备的系统接入点
BaseSolution.operation_mode     → 适合的自动化类型（AMR vs AS/RS vs AGV）
BaseSolution.labor_model        → 人工替代量计算（CAPEX → ROI）
BaseSolution.kpi_framework      → 自动化后的 KPI 提升目标
BaseSolution.confidence         → ROI 计算精度（HIGH/MEDIUM/LOW）
```

Automation Solution 输出：
- 设备选型（AMR/AGV/AS/RS 哪个适合）
- CAPEX 投资额
- 年化人工节省
- ROI / 回本周期

### 2.3 数据流总图

```
project_state (Input Contract v1)
    │
    ▼
┌─────────────────────────────────────────────┐
│  Layer 1: Base Solution Generator           │
│  adapter: base_solution_input_adapter.py     │
│  generator: base_solution_generator.py (LLM)│
│                                             │
│  输出: BaseSolution {                        │
│    operation_mode, process_design,           │
│    labor_model, kpi_framework,              │
│    system_boundary, risk_profile,            │
│    implementation_strategy                   │
│  }                                           │
└─────────────────┬───────────────────────────┘
                  │
        ┌─────────┴──────────┐
        ▼                    ▼
┌───────────────────┐  ┌───────────────────────────┐
│  Layer 2:         │  │  Layer 3:                 │
│  Improvement      │  │  Automation Engine        │
│  (future)         │  │  (evolve existing scorer) │
│                   │  │                            │
│  - 瓶颈分析        │  │  - 设备选型                │
│  - 效率提升        │  │  - CAPEX + ROI            │
│  - 人工节省估算    │  │  - 15 scenario scores     │
└───────────────────┘  └───────────────────────────┘
        │                            │
        └────────────┬───────────────┘
                     ▼
         Combined Solution Report
         (Base + Improvement + Automation)
```

---

## 3. recommend_solutions 重构设计

### 3.1 当前签名

```python
# backend/engines/automation_engine.py
def recommend_automation(project_profile: Dict) -> List[Dict[str, Any]]:
    """Returns top-5 scenario recommendations sorted by score."""
    ...
```

### 3.2 重构后签名（新增入口函数）

```python
# backend/engines/solution_recommender.py  (new file)

from backend.schemas.base_solution_schema import BaseSolution

def recommend_solutions(
    project_state: dict[str, Any],
    *,
    project_id: Optional[str] = None,
    include_layers: list[int] = [1, 2, 3],
) -> SolutionBundle:
    """
    Three-layer solution recommendation entry point.

    Parameters
    ----------
    project_state : dict
        Must conform to project_state_input_contract_v1.md.
    include_layers : list[int]
        Which layers to generate:
          [1] → Base Solution only
          [1, 3] → Base + Automation (skip Improvement)
          [1, 2, 3] → All layers (full bundle)
    project_id : str, optional
        Pipeline ID for linkage.

    Returns
    -------
    SolutionBundle
        Named tuple with .base, .improvement, .automation fields.

    Raises
    ------
    InputError
        If P0 fields missing.
    """
    ...


# Stub implementations (DO NOT implement — stub only):

def _generate_base_solution(
    project_state: dict[str, Any],
    project_id: Optional[str],
) -> BaseSolution:
    """
    Step 1: Pure adapter transform (no LLM).
    Step 2: LLM narrative generation.

    Implementation:
      1. adapter.adapt_project_state(project_state, project_id)
         → BaseSolution with narrative="" and all structural fields filled
      2. base_solution_generator.generate_narrative(bs)
         → fills BaseSolution.narrative using LLM
    """
    raise NotImplementedError("v0.8: stub only")


def _generate_improvement_solution(
    base_solution: BaseSolution,
) -> ImprovementSolution:
    """
    Step 1: Identify process bottlenecks from base_solution.process_design
    Step 2: LLM generates optimisation recommendations per bottleneck

    Implementation:
      1. bottleneck_detector.analyse(base_solution.process_design)
         → list of {stage_key, bottleneck_type, severity}
      2. improvement_generator.generate(
            bottlenecks=bottlenecks,
            labor_model=base_solution.labor_model,
         )
         → ImprovementSolution with narrative and efficiency gains
    """
    raise NotImplementedError("v0.8: stub only")


def _generate_automation_solution(
    base_solution: BaseSolution,
    improvement_solution: Optional[ImprovementSolution] = None,
) -> AutomationSolution:
    """
    Step 1: Use existing automation_engine.recommend_automation()
    Step 2: Enrich with base_solution.labor_model (CAPEX basis)
    Step 3: Adjust scenario scores using base_solution.confidence

    Implementation:
      1. scenarios = automation_engine.recommend_automation(
            project_profile=build_automation_profile(base_solution)
         )
      2. capex_calc.calculate(scenarios, base_solution.labor_model)
         → adds annual_saving, roi, payback_months to each scenario
      3. confidence_adjuster.apply(base_solution.confidence, scenarios)
         → widens ROI range if confidence=LOW
    """
    raise NotImplementedError("v0.8: stub only")


@dataclass
class SolutionBundle:
    """Container for all three solution layers."""
    base:           BaseSolution
    improvement:     Optional[ImprovementSolution] = None
    automation:     Optional[AutomationSolution] = None
    confidence:     ConfidenceLevel
    layer_results:  dict[int, str]  # layer → "complete" | "skipped" | "error"
```

### 3.3 推荐的代码重构步骤

**阶段 1（v0.8）：Adapter + Schema（已完成）**
- `backend/schemas/base_solution_schema.py` ← 本设计文档 Deliverable A
- `backend/solution/base_solution_input_adapter.py` ← 本设计文档 Deliverable B
- `backend/engines/solution_recommender.py` ← stub (框架骨架)

**阶段 2（v0.9）：Base Solution Generator（LLM）**
- Implement `_generate_base_solution()`
- LLM generates narrative from structured fields
- `BaseSolution.narrative` field gets filled

**阶段 3（v1.0）：Layer 2 Improvement Solution**
- Implement `_generate_improvement_solution()`
- `backend/engines/improvement_engine.py` (new)

**阶段 4（v1.1）：Layer 3 Automation Refactor**
- Refactor existing `recommend_automation()` to accept `BaseSolution`
- Add CAPEX calculation using `base_solution.labor_model`
- Add ROI with confidence-aware ranges

---

## 4. operation_mode 和 process_design 的下游使用

### 4.1 operation_mode 下游消费者

| 消费者 | 使用方式 |
|--------|---------|
| Cost Model | `operation_mode.region_cost_index` × 人工成本 |
| Improvement Engine | 判断哪些 core_activities 有优化空间 |
| Automation Engine | 判断适合的设备类型（冷链→AGV，电商→AMR） |
| UI (Report) | 在方案封面显示运营模式标签 |

### 4.2 process_design 下游消费者

| 消费者 | 使用方式 |
|--------|---------|
| Improvement Engine | 分析每个 ProcessStage 的 SLA 是否达标 |
| Automation Engine | 判断哪个 stage 需要自动化介入 |
| Cost Model | 为每个 stage 估算 OPEX |
| QA Gate | 验证 SLA 一致性（proposal 承诺 vs KPI framework） |
| UI (Report) | 渲染流程图（使用 `flow_diagram_label`） |

---

## 5. 关键决策问题（需人工评审）

### 5.1 方案粒度

**Q1: Base Solution 是否需要多方案（类似 Layer-3 的 top-5）？**

当前设计是每个项目生成 **1 个** Base Solution。
如果需要多方案对比（如"低成本方案 vs 高自动化方案"），
则需要将 `recommend_solutions` 改为返回 `list[BaseSolution]`，
每个方案有独立的 `operation_mode` 变体。

**建议：** v0.8 保持单方案，后续根据用户反馈扩展。

---

### 5.2 Confidence 对下游的影响链

**Q2: Confidence=LOW 时，Layer-3 是否应该禁止 ROI 输出？**

当前设计中 `Confidence=LOW` 意味着 P2 字段有默认值，
ROI 误差可能高达 ±30%（尤其 region 误为华东时）。

**选项 A：** Confidence=LOW → Layer-3 输出带 ±50% 范围的 ROI，UI 加警告
**选项 B：** Confidence=LOW → Layer-3 输出 BLOCKED，提示用户补全 P2 字段
**选项 C：** Confidence=LOW → Layer-3 输出 ROI 但加显著标注

**建议：** 选项 A（range estimate + warning），与 Cost Model 的 RANGE 模式保持一致。

---

### 5.3 Layer-2 的必要性

**Q3: 是否在 v0.8 同步设计 Layer-2 Improvement？**

Improvement Solution 是 Base 和 Automation 之间的优化层。
如果仅需要"基础运营方案 + 自动化方案"（无优化层），则：
- Layer-2 可以降为 Improvement Engine 中的**内部步骤**
- 不需要独立的 schema 和生成器

**建议：** v0.8 只实现 Layer-1 + Layer-3，Layer-2 作为 stub 保留。
如果投标场景中客户明确要求"效率优化"诉求，再实现 Layer-2。

---

### 5.4 自动化场景评分 vs 方案选择

**Q4: 现有 15 场景评分（recommend_automation）如何与三层架构共存？**

当前 `recommend_automation` 输出 15 个场景 + 评分。
重构后，这 15 个场景成为 Layer-3 的输出之一。
但 Layer-3 还需要额外的设备选型逻辑和 ROI 计算。

**建议：** `recommend_automation()` 保持独立接口不变（向后兼容），
在 `SolutionBundle.automation` 中嵌入 `recommend_automation` 的输出，
并在上面叠加 CAPEX 计算和 ROI 估算。

---

### 5.5 Implementation Strategy 的 SLA 来源

**Q5: ImplementationPhase.gate_criteria 中的 SLA 值从哪来？**

当前设计中 gate_criteria 是静态文本。
如果需要根据 `service_scope` 动态生成，
则需要 LLM 根据 process_design 中的 SLA 值来推导。

**建议：** v0.8 adapter 阶段用硬编码的门禁标准（见 adapter 代码）。
v0.9 的 Base Solution Generator 阶段由 LLM 细化。

---

### 5.6 Labor Model 的精确度

**Q6: 人工成本估算误差如何控制在可接受范围？**

当前 adapter 的 headcount 估算使用固定乘数（scale tier based），
对于日均 50,000 单的电商场景误差可能很大。

**建议：** Labor Model 的 headcount 是**第一轮估算**（adapter），
Base Solution Generator 阶段由 LLM 根据行业特点精细化。
Cost Model 使用最终的 refined labor model 做 ROI。

---

## 6. Schema 版本管理

### 6.1 三个 Schema 的演进策略

```
Layer 1: BaseSolution        → backend/schemas/base_solution_schema.py
Layer 2: ImprovementSolution → backend/schemas/improvement_solution_schema.py (future)
Layer 3: AutomationSolution → backend/schemas/automation_solution_schema.py (future)
```

每个 schema 文件必须包含：
- `version: str` 字段（语义化版本）
- `generator_version: str` 字段（生成器版本）
- Schema 变更时：大版本号 + migration guide

### 6.2 Schema 兼容性规则

- 新字段只能添加到末尾
- 已有字段不能删除，只能标记为 deprecated
- 枚举值只能添加，不能移除或重命名

---

## 7. 文件清单

| 文件路径 | 状态 | 说明 |
|---------|------|------|
| `backend/schemas/base_solution_schema.py` | **完成（设计）** | Layer-1 Schema |
| `backend/solution/base_solution_input_adapter.py` | **完成（设计）** | Pure transform, no LLM |
| `backend/engines/solution_recommender.py` | **待实现** | Entry point stub |
| `backend/engines/base_solution_generator.py` | 已存在（部分） | 需要适配新 schema |
| `backend/schemas/improvement_solution_schema.py` | **待设计** | Layer-2 Schema |
| `backend/schemas/automation_solution_schema.py` | **待设计** | Layer-3 Schema（扩展现有） |
| `docs/architecture/base_solution_architecture.md` | **本文件** | 架构设计文档 |

---

## 8. 测试策略

### 8.1 单元测试（adapter 层）

```python
# tests/unit/test_base_solution_input_adapter.py

def test_p0_missing_raises_input_error():
    """Missing P0 field must raise InputError."""
    with pytest.raises(InputError):
        adapt_project_state({"warehouse_area": 5000})  # missing other P0s

def test_p2_default_applied_and_tracked():
    """Missing P2 fields get defaults and are flagged."""
    result = adapt_project_state({
        "warehouse_area": 5000, ..., "service_scope": {...},  # all P0s present
        # industry, region, labor_cost_level all missing
    })
    assert result.defaulted_p2_fields == ["industry", "region", "labor_cost_level"]
    assert result.confidence == ConfidenceLevel.LOW

def test_scale_tier_xs():
    assert _derive_scale_tier(500) == ScaleTier.XS

def test_scale_tier_xl():
    assert _derive_scale_tier(80_000) == ScaleTier.XL

def test_operation_mode_ecommerce():
    resolved = {"industry": "电商", "warehouse_area": 5000, "dc_count": 1, "service_scope": {}}
    tier = _derive_scale_tier(5000)
    op_mode = _derive_operation_mode(resolved, tier)
    assert op_mode.mode_name == OperationModeEnum.ECOMMERCE_FULFILLMENT
```

### 8.2 集成测试（Schema → JSON）

```python
def test_base_solution_serializable():
    """BaseSolution must round-trip through JSON."""
    bs = adapt_project_state(FULL_VALID_PROJECT_STATE)
    json_str = bs.model_dump_json()
    restored = BaseSolution.model_validate_json(json_str)
    assert restored.solution_id == bs.solution_id
    assert restored.operation_mode.mode_name == bs.operation_mode.mode_name
```

---

*文档版本：v0.8-draft | 待实现评审后更新为正式版本*
