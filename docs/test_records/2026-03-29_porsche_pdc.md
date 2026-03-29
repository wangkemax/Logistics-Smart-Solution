# 测试记录 #1 — 保时捷上海PDC项目

> **日期：** 2026-03-29
> **测试人：** 虾米（AI Agent）
> **项目：** 保时捷上海PDC（保时捷（中国）PCN）
> **标书：** `202603_Porsche Shanghai PDC 2nd Round_FEILIKS After Presentation Updates.pdf`（FEILIKS投标方案）

---

## 一、初始状态（Pipeline ID: 13223d2c）

| 指标 | 值 |
|------|-----|
| recommended_mode | blocked |
| readiness_score | 0.0% |
| P0 缺失数量 | 6（初筛）/ 1（经schema同步后） |
| P1 缺失数量 | 3 |
| 冲突字段数量 | 0 |
| clarification_questions 数量 | 1（仅泛泛的"招标文件内容缺失"） |

**RFQ已知数据（从PDF文本提取）：**

| 字段 | 值 | 来源 |
|------|-----|------|
| DC数量 | 1（上海PDC） | PDF正文 |
| 仓库面积 | 32,723 sqm（C3:26,523+C2:5,200+C5:1,000） | Warehouse Layout章节 |
| 合同年限 | 3+2年（初始3年+续约选项） | 正文多处提及 |
| 日均出库 | 2,438 单/天（2026年） | RFQ Input表格 |
| 服务范围 | 仓储运营+出库配送+进口运输 | Service Scope章节 |
| 行业 | 汽车零部件 | PDF正文 |
| 区域 | 华东（上海临港） | PDF正文 |

---

## 二、补录过程

### 补录字段 #1
- **字段：** daily_orders
- **补录值：** 2438 orders/day
- **补录方式：** 直接输入（RFQ Input表格数据）
- **是否遇到问题：** 否

### 补录字段 #2
- **字段：** dc_count
- **补录值：** 1
- **补录方式：** 直接输入（PDF明确）
- **是否遇到问题：** 否

### 补录字段 #3
- **字段：** warehouse_area
- **补录值：** 32,723 sqm
- **补录方式：** 直接输入（Warehouse Layout章节）
- **是否遇到问题：** 否

### 补录字段 #4
- **字段：** contract_years
- **补录值：** 3 years
- **补录方式：** 直接输入（正文3+2结构）
- **是否遇到问题：** 否

### 补录字段 #5
- **字段：** service_scope
- **补录值：** 仓储运营+出库配送+进口运输+增值服务
- **补录方式：** 直接输入（Service Scope章节）
- **是否遇到问题：** 否

### 补录字段 #6
- **字段：** sku_count
- **补录值：** 1,976,652 lines/year
- **补录方式：** 直接输入（RFQ表格数据换算）
- **是否遇到问题：** 否

### 补录字段 #7
- **字段：** total_warehouse_area
- **补录值：** 32,723 sqm
- **补录方式：** 直接输入
- **是否遇到问题：** 否

---

## 三、重算结果

| 指标 | 补录前 | 补录后 |
|------|--------|--------|
| recommended_mode | blocked | **range_estimate** ✅ |
| readiness_score | 0.0% | 60% |
| P0 缺失数量 | 1+ | **0** ✅ |
| P1 缺失数量 | 3 | 3（仍开放） |

**变化摘要（后端返回）：**
```
old_mode: partial_ready
new_mode: range_estimate
mode_changed: True
resolved_p0_count: 8
remaining_p0_count: 0
for_cost_model: True ✅
fields_updated: [service_scope, sku_count, total_warehouse_area]
```

---

## 四、发现的问题

#### 🔴 P0 — 逻辑/功能问题

| # | 问题描述 | 严重程度 | 出现位置 | 状态 |
|---|---------|---------|---------|------|
| 1 | `contract_years` 在 FIELD_REGISTRY 里是 P1，实际应为 P0（影响ROI分摊年限） | P0 | tender_schema.py | ✅ 已修复 |
| 2 | `resolve_all_fields` 未传 `field_priorities` 参数，所有字段默认 P0 | P0 | recompute_service.py | ✅ 已修复 |
| 3 | `total_warehouse_area` 未加入人工补录白名单 | P0 | input_capture_service.py | ✅ 已修复 |
| 4 | resolved字段传 downstream 时 `final_status` 与 cost_model 检查的 `status` 不兼容 | P0 | recompute_service.py | ✅ 已修复 |
| 5 | `service_scope` 在 cost_model_requirements 是 P0，但在 schema 是 P1，schema不同步 | P0 | tender_schema.py | ✅ 已修复 |

#### 🟡 P1 — 交互体验问题

| # | 问题描述 | 出现位置 | 状态 |
|---|---------|---------|------|
| 1 | `service_scope` 原文提取时经常为空字符串，recomputed 后 downstream 显示"缺失" | downstream_input_builder | ✅ 已修复 |
| 2 | `resolved_count` 跨所有优先级累加，导致 summary 显示数字不可比 | clarification_manager.py | ✅ 已修复 |
| 3 | 前端 session_state 缓存导致显示旧状态 | app.py | ✅ 移除缓存逻辑 |

#### 🟢 P2 — 文案/提示问题

| # | 问题描述 | 出现位置 | 状态 |
|---|---------|---------|------|
| 1 | `service_scope` 的 `acceptable_units` 未定义 | input_capture_service.py | ✅ 已添加 |
| 2 | 待解决计数公式错误 `must_total - resolved` 未考虑未解决的 P0 数量 | app.py | ✅ 已修复 |

---

## 五、逐项问题详细记录

### 问题 #1：contract_years 被错误归为 P1
**类型：** 逻辑 / 严重程度：P0
**问题描述：** `FIELD_REGISTRY` 中 `contract_years` 的 priority 为 "P1"，导致 readiness 计算时未计入阻塞项，但 cost model 实际需要此字段。
**预期行为：** `contract_years` 应为 P0，因为合同年限决定 ROI 分摊年限。
**实际行为：** 被归为 P1，不影响 readiness 计算但影响 downstream 阻塞判断。
**修复：** `tender_schema.py` — `"contract_years": "P0"`（两处：FIELD_PRIORITY + FieldDef）

### 问题 #2：resolve_all_fields 未传 field_priorities
**类型：** 逻辑 / 严重程度：P0
**问题描述：** `resolve_all_fields` 调用时未传 `field_priorities` 参数，所有字段默认 P0，导致 `inventory`、`peak_factor` 等实际 P1 字段被错误标记为 P0。
**预期行为：** P1 字段不应被当作 P0 阻塞项。
**实际行为：** 所有 P1 字段被标记为 P0，导致 `remaining_p0_count` 虚高。
**修复：** `recompute_service.py` — 传入完整的 `field_priorities` 字典

### 问题 #3：total_warehouse_area 不在人工补录白名单
**类型：** 逻辑 / 严重程度：P0
**问题描述：** 用户无法通过前端补录 `total_warehouse_area`，因为它不在 `MANUAL_INPUT_DEFINITIONS` 中，校验直接返回"不支持人工补录"。
**预期行为：** 用户应能补录该字段。
**实际行为：** 补录时报错。
**修复：** `input_capture_service.py` — 添加 `total_warehouse_area` InputDefinition

### 问题 #4：resolved 字段与 downstream status 不兼容
**类型：** 逻辑 / 严重程度：P0
**问题描述：** resolved 字段的 `final_status="resolved"`，但 downstream 的 `build_cost_model_input` 检查 `"status":"provided"` 判断可用性，导致所有字段被判定为"缺失"。
**预期行为：** usable=True 的字段应被识别为 provided。
**实际行为：** downstream 仍显示 P0 字段缺失。
**修复：** `recompute_service.py` — resolved_as_normalized 构建时，usable 字段写 `"status":"provided"`，非 usable 写 `"status":"missing"`

### 问题 #5：schema 与 cost_model P0 字段不同步
**类型：** 架构 / 严重程度：P0
**问题描述：** `FIELD_REGISTRY` 中 `service_scope` 为 P1，但 `COST_MODEL_REQUIREMENTS` 中为 P0，导致字段理解与成本测算的门禁判断不一致。
**预期行为：** 两层 P0 字段应保持同步。
**实际行为：** 补录 `service_scope` 后 readiness 通过，但 downstream 仍显示阻塞。
**修复：** `tender_schema.py` — `"service_scope": "P0"`

---

## 六、整体评价

**可用性：** ⬛⬛⬛⬛⬜ **4/5**
**文案清晰度：** ⬛⬛⬛⬜⬜ **3/5**（clarification question 文案仍较机械）
**交互顺畅度：** ⬛⬛⬛⬜⬜ **3/5**（需要知道 RFQ 原文才能正确补录）
**状态反馈明确度：** ⬛⬛⬛⬜⬜ **3/5**（downstream mode 显示 None，需补充展示）

**最大优点：**
- 字段合并逻辑清晰（manual > extracted > assumed）
- 4格变化摘要卡片直观
- 重算后 readiness 实时更新

**最需要改进的地方：**
1. downstream_input 的 recommended_mode 未正确传递回 API 返回值
2. clarification question 文案需更业务化（避免"请提供xxx的具体数据"这种泛泛说法）
3. 自动化提交（浏览器session state）不稳定

---

## 七、后续跟进

- [x] 问题 #1 已修复（版本：v0.6.2）
- [x] 问题 #2 已修复（版本：v0.6.2）
- [x] 问题 #3 已修复（版本：v0.6.2）
- [x] 问题 #4 已修复（版本：v0.6.2）
- [x] 问题 #5 已修复（版本：v0.6.2）
- [x] 问题 #6 已修复（版本：v0.6.2）
- [ ] clarification 文案优化（v0.6.2 后续）
- [ ] 自动化提交session state（v0.6.2 后续）

---

*记录人：虾米 | 日期：2026-03-29*
