# Project State Input Contract v1.0

> **版本：** v1.0  
> **日期：** 2026-03-31  
> **状态：** 正式发布  
> **用途：** Base Solution Schema 的输入边界说明书  
> **维护者：** 虾米

---

## 概述

本契约定义了 `project_state` 对象的完整输入规范，是 **Understanding Engine** 输出给所有下游模块的唯一入口。

所有下游模块（Clarification / Solution / Cost / QA / Proposal）**只能**从本契约定义的字段中读取数据，严禁绕过本契约直接从原始 tender 文档或其他路径读取字段。

---

## 字段总表

| 字段名 | 类型 | P分类 | 来源层级 | 缺失时处理 | 单位规范 |
|--------|------|-------|---------|-----------|---------|
| `project_name` | string | — | LLM | "待确认" | — |
| `client_name` | string | — | LLM | "待确认" | — |
| `industry` | enum | **P2** | regex+LLM | **"电商"**（默认值） | 见行业枚举 |
| `region` | enum | **P2** | regex+LLM | **"华东"**（默认值） | 见区域枚举 |
| `warehouse_area` | float | **P0** | regex+LLM | BLOCK | 平方米（sqm） |
| `total_warehouse_area` | float | **P0** | regex+LLM | BLOCK | 平方米（sqm） |
| `dc_count` | int | **P0** | regex+LLM | BLOCK | 个 |
| `daily_orders` | float | **P0** | regex+LLM | BLOCK | 单/天 |
| `sku_count` | float | **P0** | regex+LLM | BLOCK | SKU数 |
| `contract_years` | int | **P0** | regex+LLM | BLOCK | 年 |
| `service_scope` | object | **P0** | regex+LLM | BLOCK | 见 service_scope 规范 |
| `inventory` | float | P1 | regex+LLM | 区间估算 | 件/托盘 |
| `peak_factor` | float | P1 | regex+LLM | 区间估算（默认1.5） | 倍数 |
| `kpi_targets` | object | P1 | regex+LLM | 降级提示 | 见 KPI 规范 |
| `penalty_rules` | list | P1 | regex+LLM | 降级提示 | — |
| `labor_cost_level` | enum | **P2** | regex+LLM | **"中"**（默认值） | 低/中/高 |
| `budget_level` | enum | **P2** | regex+LLM | **"中"**（默认值） | 低/中/高 |
| `automation_expectation` | enum | P2 | regex+LLM | "中"（默认值） | 低/中/高 |
| `go_live_date` | string | P1 | regex+LLM | "待确认" | YYYY-MM |

---

## P0 字段（门禁规则）

### 定义
P0 = **BLOCKING**。缺失则 cost_model gate 强制进入 `BLOCK` 模式，不允许进入正式 ROI 测算。

### P0 字段清单
```
warehouse_area, total_warehouse_area, dc_count, daily_orders, sku_count, contract_years, service_scope
```

### 门禁规则
```python
P0_FIELDS = ["warehouse_area", "total_warehouse_area", "dc_count",
              "daily_orders", "sku_count", "contract_years", "service_scope"]

def check_gate(profile: dict) -> str:
    missing_p0 = [f for f in P0_FIELDS
                   if profile.get(f) is None or profile.get(f) == ""]
    if missing_p0:
        return "BLOCK"   # 无法正式测算
    if any_missing_p1(profile):
        return "RANGE"  # 区间估算
    return "PASS"        # 正式测算
```

### service_scope 结构规范
```json
{
  "inbound": {
    "receiving": true,
    "unloading": true,
    "quality_check": true,
    "putaway": true
  },
  "storage": {
    "pallet_storage": true,
    "bin_storage": false
  },
  "outbound": {
    "picking": true,
    "packing": true,
    "labeling": true,
    "loading": true,
    "shipping": true
  },
  "value_added": {
    "kitting": false,
    "repack": false,
    "return_handling": true
  },
  "support": {
    "inventory_reporting": true,
    "system_integration": false
  }
}
```

---

## P1 字段（影响精度）

### 定义
P1 = **QUALITY-AFFECTING**。缺失时 cost_model 进入 `RANGE` 区间估算模式，输出带 ±XX% 的范围而非精确值。

### P1 字段清单
```
inventory, peak_factor, kpi_targets, penalty_rules, automation_expectation, go_live_date
```

---

## P2 字段（默认值兜底）

### 定义
P2 = **DEFAULT-FALLBACK**。缺失时使用默认值，不触发 BLOCK 或 RANGE。

### P2 字段默认值

| 字段 | 默认值 | 默认原因 |
|------|--------|---------|
| `industry` | "电商" | 最常见场景，避免 None |
| `region` | "华东" | 最常见市场区域 |
| `labor_cost_level` | "中" | 中位数 |
| `budget_level` | "中" | 中位数 |
| `automation_expectation` | "中" | 中等期望 |

### ⚠️ P2 缺失的业务影响

> 下游模块在读取 P2 字段时，**必须**意识到这些值可能是默认值而非提取值。

| 字段 | 默认错误时的业务风险 |
|------|-------------------|
| `industry` 误为"电商" | 制造业/医药场景被推向错误的自动化方案 |
| `region` 误为"华东" | 华北/华南人工成本差 ±30%，ROI 误差显著 |
| `labor_cost_level` 误为"中" | 实际高人工成本区域 → ROI 低估自动化收益 |
| `budget_level` 误为"中" | 客户高预算项目被推低成本方案，丢单 |

**建议：** 在 UI 上对默认值字段加 ⚠️ 标注，提示用户确认。

---

## 字段来源层级（优先级）

```
原文 tender 文本
    ↓ regex 提取（精确匹配）
    ↓ LLM 推断（语义理解，上下文窗口 8000 字符）
    ↓ default fallback（P2 字段）
    ↓ manual input（Clarification 补录，最终权威）
```

**优先级规则：**
1. `manual_input` > `LLM` > `regex` > `default`
2. Clarification Workspace 补录的字段覆盖以上所有来源

---

## 枚举值规范

### industry 枚举
```
电商 | 3PL | 零售 | 制造 | 快递 | 医药 | 食品 | 生鲜
```

识别模式（regex 优先）：
- `dealer|Distributor|dealer network|分销|经销商|代理商` → **3PL**
- `电商|电子商务|天猫|京东|拼多多|抖音` → 电商
- `零售|商超|便利店|百货|超市` → 零售
- `制造|生产商|工厂` → 制造
- `医药|制药|医疗器械` → 医药
- `食品|饮料|乳制品` → 食品
- `生鲜|冷链|农产品` → 生鲜

### region 枚举
```
华东 | 华南 | 华北 | 华中 | 西部 | 东北
```

识别模式（regex 优先）：
- `华东|上海|上海市|浦东|Shanghai|Jiangsu|Zhejiang|Anhui` → **华东**
- `华南|广东|广西|海南` → 华南
- `华北|北京|天津|河北` → 华北
- `华中|湖北|湖南|河南` → 华中
- `西部|四川|重庆|陕西|新疆|甘肃` → 西部
- `东北|辽宁|吉林|黑龙江` → 东北

### labor_cost_level / budget_level / automation_expectation 枚举
```
低 | 中 | 高
```

---

## 单位规范

| 字段 | 单位 | 说明 |
|------|------|------|
| `warehouse_area` | 平方米（sqm） | 正数 |
| `total_warehouse_area` | 平方米（sqm） | ≥ warehouse_area |
| `daily_orders` | 单/天 | 正数 |
| `sku_count` | SKU数 | 正整数 |
| `inventory` | 件 或 托盘 | 需标注单位类型 |
| `peak_factor` | 倍数 | ≥ 1.0 |
| `dc_count` | 个 | 正整数 |
| `contract_years` | 年 | 正整数（1-10） |

---

## 下游契约保证

### Base Solution 的输入依赖
Base Solution Generator 需要以下字段**必须存在**（可用默认值）：

```
industry, region, warehouse_area, daily_orders, sku_count,
labor_cost_level, budget_level, service_scope
```

### Base Solution 缺失时的降级行为
- `labor_cost_level` 为默认值"中"：用华东人工成本估算，可接受
- `region` 为默认值"华东"：用华东参数库，可接受
- `industry` 为默认值"电商"：**需在 UI 提示用户确认**，误判会导致方案方向错误

### Cost Model 的输入依赖
正式测算（PASS 模式）需要全部 P0 字段；区间估算（RANGE 模式）接受 P0 完整但 P1 缺失。

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-03-31 | 初始版本，基于 extraction 诊断修复后的字段行为定义 |
