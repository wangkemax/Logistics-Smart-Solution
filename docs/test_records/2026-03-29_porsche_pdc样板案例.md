# 样板案例 #1 — 保时捷上海PDC投标项目完整闭环

> **整理日期：** 2026-03-29
> **项目：** 保时捷（中国）PCN — PDC Shanghai
> **招标方：** Porsche Motors
> **投标方：** FEILIKS
> **文档：** `202603_Porsche Shanghai PDC 2nd Round_FEILIKS After Presentation Updates.pdf`
> **意义：** 系统第一次完整打通"投标理解→字段提取→Clarification补录→downstream门禁→模式判定"全链路

---

## 一、项目背景

| 项目 | 内容 |
|------|------|
| 客户 | 保时捷（中国）PCN |
| 服务内容 | 进口运输 + 仓储运营 + 出库配送 + DG仓库 |
| 仓库 | PDC Shanghai（上海临港） |
| 合同期 | 3+2年（初始3年，自动续约2年） |
| Go-Live | 2026/8/1 |
| 仓库面积 | 32,723 sqm（C3:26,523 / C2:5,200 / C5:1,000） |
| 峰值日均出库 | 2,438单/天 |

---

## 二、初始状态（Pipeline ID: `13223d2c`）

### 2.1 正向路径（Extraction）

Pipeline 提取到的字段（来自PDF文本）：

| 字段 | 提取值 | 状态 | 问题 |
|------|--------|------|------|
| warehouse_area | 32,723 sqm | explicit | ✅ |
| daily_orders | 2,438 orders/day | explicit | ✅ |
| dc_count | 1 | explicit | ✅ |
| contract_years | 3 | explicit | ⚠️ 实际应为3+2 |
| service_scope | "仓储运营+出库配送+进口运输" | explicit | ⚠️ 缺"增值服务" |
| sku_count | null | missing | ❌ |
| industry | 汽车零部件 | explicit | ✅ |
| region | 华东 | explicit | ✅ |

**关键发现：** 文本提取器能从正文提取数字字段（如面积、出库量），但：
- 合同年限的"3+2"结构无法识别（只提取到"3"）
- 增值服务项目未在 service_scope 原文体现
- SKU数据用中文标签（lines/year），容易被误识别

### 2.2 初始 Readiness

| 指标 | 值 | 说明 |
|------|-----|------|
| readiness_score | 0.0% | LLM调用超时 |
| recommended_mode | blocked | — |
| P0 缺失 | 6个 | 初始state |
| clarification_questions | 1条 | 仅泛泛的"招标文件内容缺失" |

---

## 三、Clarification 补录过程

### 3.1 第一次补录（字段修复后）

补录了以下 RFQ 原文数据：

| 字段 | 补录值 | 来源 | 性质 |
|------|--------|------|------|
| daily_orders | 2,438 orders/day | RFQ Input表格（工作日均值） | P0 |
| dc_count | 1 | PDF正文"PDC Shanghai" | P0 |
| warehouse_area | 32,723 sqm | Warehouse Layout章节 | P0 |
| contract_years | 3 | 正文3+2结构，取3 | P0 |
| service_scope | 仓储运营+出库配送+进口运输+增值服务 | Service Scope章节 | P0 |

### 3.2 发现并修复的 Bug

补录后仍 mode=`blocked`，进一步诊断发现6个 P0 级 bug：

| # | Bug | 根因 | 修复 |
|---|------|------|------|
| 1 | contract_years 被归为 P1 | FIELD_REGISTRY 写错 | 升为 P0 |
| 2 | resolve_all_fields 未传 field_priorities | 参数漏传 | 补传 |
| 3 | total_warehouse_area 无法补录 | 不在白名单 | 加入白名单 |
| 4 | resolved 字段 status 不被 downstream 识别 | "resolved" vs "provided" | 映射转换 |
| 5 | service_scope schema vs cost_model P0 不同步 | 两处定义不一致 | 同步为 P0 |
| 6 | downstream_input 未暴露到 API | RecomputeResponse 漏字段 | 添加字段 |

---

## 四、状态变化全流程

```
Pipeline 启动
  ↓
Extraction（文本提取）
  → 正则提取: warehouse_area, daily_orders, dc_count, region, industry
  → LLM 提取: 超时（API问题）
  → 初始 readiness: 0.0% | mode: blocked
  → P0缺失: 6个（sku_count, contract_years等）
  ↓ [人工补录]
Clarification 补录（6字段）
  → daily_orders: 2438 ✅
  → dc_count: 1 ✅
  → warehouse_area: 32723 ✅
  → contract_years: 3 ✅
  → service_scope: 完整服务范围 ✅
  → sku_count: 1976652 ✅
  ↓ [重算]
Bug 修复后重算
  → readiness: 47.4% → 60%
  → P0缺失: 1个（peak_factor）
  → mode: blocked → partial_ready
  ↓ [schema 同步 + resolved字段修复]
最终重算
  → P0缺失: 0个
  → readiness: 60%
  → mode: partial_ready → range_estimate ✅
  → for_cost_model: True ✅
```

---

## 五、最终 downstream_input 状态

```
recommended_mode: range_estimate
mode_reason: "P0字段完整但P1字段有缺失，仅允许区间估算"

source_inputs (9个已确认字段):
  dc_count        = 1        [P0] ✅
  warehouse_area  = 32,723   [P0] ✅
  daily_orders    = 2,438     [P0] ✅
  contract_years  = 3         [P0] ✅
  service_scope   = "仓储运营+出库配送+进口运输+增值服务" [P0] ✅
  sku_count       = 1,976,652 [P1] ✅
  labor_cost_level= 高       [P1] ✅
  industry        = 汽车零部件 [P2] ✅
  region          = 华东     [P2] ✅

P1 缺失 (区间估算模式，允许假设):
  inventory       = 缺失
  peak_factor     = 缺失 ← 主要影响峰值产能设计
  penalty_rules   = 缺失
  kpi_targets     = 缺失
  automation_expectation = 缺失

blocking_reasons: [] ✅
```

---

## 六、为什么是 range_estimate 而不是 full_calc

**不是 full_calc 的原因：**
- P1 字段有5个缺失（peak_factor、inventory、penalty_rules、kpi_targets、automation_expectation）
- 这些字段影响 ROI 精确度，但不影响测算可行性
- downstream_input_builder 的判断逻辑：
  - 有 P0 不可用 → blocked
  - P0 全部 provided，但 P1 有缺失 → **range_estimate**（正确）
  - P0 + P1 全部 provided → full_calc

**这对投标的实际意义：**
- 可以输出 ROI 方向性判断（区间范围）
- 不能输出精确IRR/NPV（需要P1字段补充）
- 适用于竞标初期方案评估

---

## 七、系统演进关键节点回顾

| 阶段 | 版本 | 能力 |
|------|------|------|
| 初始 | v0.1 | 正则提取 + 正则校验 |
| 质量门禁 | v0.2 | LLM理解 + Readiness门禁 + Clarification问题生成 |
| 闭环补录 | v0.6 | Clarification Workspace + 字段级补录 + 重算 |
| 可解释性 | **v0.6.3** | **三面板展示（阻塞/假设/状态总览）** ← 当前 |

---

## 八、经验与教训

### 8.1 提取器的局限性
文本提取器（正则）对于结构化数据（表格）提取率低。RFQ 的关键数据（SKU数量、面积、日均出库）多在表格中，正则难以准确提取。这是保时捷案例中初始 blocked 的主要原因。

### 8.2 双层 schema 的同步问题
`tender_schema.py`（理解层）和 `cost_model_requirements.py`（成本层）各有一份字段优先级定义。service_scope 在理解层是 P1，在成本层是 P0，导致补录后仍阻塞。这个问题在保时捷案例中被发现并修复。

### 8.3 resolved 字段传递链断裂
ResolvedField 对象 → normalized_fields 格式 → downstream_input 的三级转换中，任何一个环节的类型不匹配都会导致字段"消失"。特别是 `final_status="resolved"` 与 downstream 检查的 `status="provided"` 不兼容。

### 8.4 Clarification 问题的文案质量
初始只有1条泛泛的"招标文件内容缺失"，无法指导用户补录。改进方向是从字段级机械提示升级为业务场景化表单（如 service_scope 应展示服务项清单让用户勾选）。

---

*整理人：虾米 | 项目：Logistics Smart Solution v0.6.3*
