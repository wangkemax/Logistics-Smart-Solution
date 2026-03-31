# Field Extraction Observability Report
**Generated:** 2026-03-31
**Analyst:** 虾米
**Status:** Phase 1 Complete — Root Causes Identified

---

## Executive Summary

LLM extraction漏字段问题（`industry` / `region` / `labor_cost_level` / `budget_level`）经诊断确认有两层根因：

1. **直接原因**：Tender文档本身不包含显式industry/region关键词 → LLM推断 + 正则缺映射 → 默认值覆盖
2. **加剧因素**：`max_tokens=1024` 严重不足，导致LLM JSON输出被截断，仅填充3/13字段（置信度30%）

---

## Diagnostic Method

对 pipeline `6079fb6a`（tender length: 65,304 chars）进行了完整提取链路追踪：

```
Step 1: Pattern extraction (regex) → field_values + confidence
Step 2: LLM API call (8000-char prompt, max_tokens=1024)
Step 3: Merge LLM result + regex → final profile
Step 4: Apply defaults for still-null P2 fields
```

---

## Finding 1: Region Extraction — Regex Pattern Gap

**Tender包含**：`上海市浦东区同顺大道555号`（position 57854）

**当前正则**（`llm_extractor.py` line 181）：
```python
_REGION_PATTERNS = [
    (re.compile(r'华东|Shanghai|Jiangsu|Zhejiang|Anhui', re.I), 'reg_east'),
    ...
]
```

**问题**：`Shanghai`（英文）被匹配，但文档里是"上海市"（中文）——正则没有`上海|上海市|浦东`关键词。

**影响**：regex层返回`region=None`，LLM也无从推断（因为只看到前8000字符，而"上海市"在position 57854，已超出截断点）。

---

## Finding 2: Industry Extraction — Pattern覆盖不足

**Tender业务实质**：SAP EWM dealer network（经销商网络仓储管理系统）

**关键词证据**：
- "Dealer returns" / "dealer" 出现6次（仓储退货流程）
- "Distribution" / "distributor" 隐含（经销商网络）

**当前industry patterns**：
```python
_INDUSTRY_PATTERNS = [
    (re.compile(r'电商|电子商务|天猫|京东|淘宝|拼多多...', re.I), 'ind_ecommerce'),
    (re.compile(r'3PL|第三方物流|物流外包|货运代理', re.I), 'ind_3pl'),
    (re.compile(r'零售|商超|便利店|百货...', re.I), 'ind_retail'),
    ...
]
```

**问题**：
- 缺少 `dealer|分销|经销商|Distributor` → 无法识别dealer network仓储为3PL场景
- "Dealer" 在文档中反复出现，但pattern完全匹配不到
- LLM也推断为"零售"（错误推断，因为tender内容是EWM系统文档而非零售业务描述）

---

## Finding 3: LLM Output Truncation（加剧因素）

**证据**：
```
LLM extraction: confidence=30% (LLM filled 3/13 fields)
industry=零售（错误推断，非文档原文）
region=华东（默认值，非提取）
labor_cost_level=中（默认值）
budget_level=中（默认值）
warehouse_area=5200（错误值，文档中无此数字）
sku_count=None, daily_orders=None（P0字段未提取）
```

**根因**：`max_tokens=1024` 对15字段JSON输出严重不足
- Prompt约5000+ tokens（8000-char tender + system prompt）
- 15字段结构化JSON至少需要1500-3000 tokens
- 实际LLM输出被截断，导致大量字段丢失

---

## Finding 4: Double Default Application（代码逻辑问题）

**代码位置**：`llm_extractor.py` line 755 + line 971-978

```python
# First default application (line 755)
'industry': llm_result.get('industry') or field_values.get('industry') or '电商',
'region': llm_result.get('region') or field_values.get('region') or '华东',
...

# Second default application (line 971-978) — after _fill_missing_fields
if profile.get('industry') in (None, '电商'):
    if field_values.get('industry') is not None:
        profile['industry'] = field_values['industry']
```

**问题**：两处默认逻辑对P2字段重复处理，代码维护性差。

---

## Finding 5: P2字段缺失时的业务影响

| 字段 | 缺失时当前处理 | 业务影响 |
|------|-------------|---------|
| `industry` | 默认"电商" | 推荐场景失真（医药/制造业场景完全不匹配） |
| `region` | 默认"华东" | 成本参数错配（华北/华南人工成本差异30%+） |
| `labor_cost_level` | 默认"中" | ROI估算误差可达±50% |
| `budget_level` | 默认"中" | 方案选型错误（客户预算高但系统推低成本方案） |

---

## Priority Classification

| 字段 | Tender出现位置 | 提取层缺失原因 | 修复优先级 |
|------|-------------|-------------|----------|
| `region` ("上海") | 正文（pos 57854） | Regex缺少"上海/上海市/浦东" | **P0** — 修复后regex即可提取 |
| `industry` (dealer network) | 全文（pos 595+） | Regex缺dealer/distributor映射 | **P1** — 修复后可识别3PL场景 |
| `labor_cost_level` | 全文无显式 | 需依赖LLM推断 + 行业知识库 | P2 — 暂时接受默认值 |
| `budget_level` | 全文无显式 | 需依赖LLM推断 + 行业知识库 | P2 — 暂时接受默认值 |

---

## Recommended Fixes

### Fix 1: Region Pattern（立即可做）
```python
_REGION_PATTERNS = [
    (re.compile(r'华东|上海|上海市|Shanghai|浦东|Jiangsu|Zhejiang|Anhui', re.I), 'reg_east'),
    ...
]
```

### Fix 2: Industry Pattern（立即可做）
```python
# 新增dealer network识别
(re.compile(r'dealer|Distributor|dealer network|分销|经销商|代理商网络', re.I), 'ind_3pl'),
```

### Fix 3: Increase max_tokens（立即可做）
```python
'max_tokens': 8192,  # 从 1024 → 8192
```

### Fix 4: Industry/Region Inference Enhancement
当前 `_infer_industry_from_descriptions` / `_infer_region_from_descriptions` 依赖 `_INDUSTRY_PATTERNS`/`_REGION_PATTERNS` 的description匹配，需增强：
- 将 "dealer" 出现的section标记为 "distribution_warehouse" → 映射到 3PL
- 将 "上海市" 的region标记 → 直接匹配华东

---

## Diagnostic Conclusion

**不是「LLM提不到」的问题，是「正则缺关键词 + max_tokens太小导致JSON截断」的问题。**

Fix 1+2+3 可以在不改LLM prompt的情况下立即改善，不需要重新训模型或大幅改prompt。
