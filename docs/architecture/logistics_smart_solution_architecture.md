# Logistics Smart Solution — 系统架构说明

> **版本：** v0.6.6
> **更新日期：** 2026-03-29
> **状态：** 进行中

---

## 一、愿景与目标

物流解决方案 AI 平台，从招标文件到完整投标方案的全流程自动化。

**最终输出：** 自动化方案 · ROI/EBITA · 多方案对比 · 标准化 Proposal · 可复用案例库

---

## 二、系统架构（5层）

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Streamlit)                 │
│   Dashboard · Clarification Workspace · Report UI       │
└─────────────────────────┬───────────────────────────────┘
                          │ HTTP/REST
┌─────────────────────────▼───────────────────────────────┐
│                    API Layer (FastAPI)                  │
│   /api/pipeline · /api/clarification · /api/presale    │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│                 Business Services Layer                 │
│                                                         │
│  ┌─────────────────┐  ┌────────────────────────────┐    │
│  │ Tender Understanding │  Tender Clarification  │    │
│  │  (LLM + Regex extraction)   │  (Field-level  │    │
│  │  13-dimension analysis       │   manual input) │    │
│  └─────────────────┘  └────────────────────────────┘    │
│                                                         │
│  ┌─────────────────┐  ┌────────────────────────────┐    │
│  │ Operation Model │  │ Cost Model               │    │
│  │ Derivation      │  │ (ROI/IRR/NPV calculation) │    │
│  │ (service_scope  │  │                          │    │
│  │  → op_profile)  │  │                          │    │
│  └─────────────────┘  └────────────────────────────┘    │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│                  Schema & Rules Layer                   │
│                                                         │
│  tender_schema.py        — Field registry, priorities   │
│  tender_quality.py       — Quality scoring rules        │
│  downstream_input_builder — Cost model input builder   │
│  cost_model_requirements — P0/P1 field definitions     │
│  process_templates.py    — v0.6.6 Labor process flows  │
│  operation_profile_service — v0.6.5 Derivation engine   │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│              Persistence Layer (SQLite)                  │
│   PipelineRun · Scenario · PipelineStage tables         │
└───────────────────────────────────────────────────────┘
```

---

## 三、数据模型

### 3.1 PipelineRun（核心持久化记录）

每次投标文档处理生成一条记录，包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `pipeline_id` | String | 唯一标识（UUID前8位） |
| `status` | String | RUNNING / COMPLETE / FAILED |
| `tender_document` | Text | 原始招标文件全文 |
| `normalized_fields_json` | Text | LLM提取的字段（v0.2格式） |
| `readiness_json` | Text | 各下游模块就绪状态 |
| `manual_inputs_json` | Text | v0.6.1 人工补录字段 |
| `resolved_fields_json` | Text | v0.6.1 合并后最终字段 |
| `clarification_tasks_json` | Text | v0.6.1 澄清任务列表 |
| `operation_profile_json` | Text | v0.6.5 运营模型 |
| `pipeline_gate_json` | Text | 各模块 GATE 状态 |

### 3.2 核心派生对象

```
service_scope (dict)
    │
    ▼ derive_operation_profile()
operation_profile: {
    operation_type: str,           # "warehouse_distribution"
    inbound/outbound/va/support: bool,
    service_complexity: int,       # 0-20
    labor_modules: {...},         # 7 team modules
    process_modules: {...},       # v0.6.6: step sequences
    operation_narrative: str,      # Chinese description
}
    │
    ▼ downstream_input_builder
downstream_input: {
    recommended_mode: "blocked" | "range_estimate" | "full_calc",
    p0_summary: {...},
    p1_summary: {...},
    source_inputs: {...},
    assumed_inputs: {...},
    operation_profile: {...},
}
```

---

## 四、核心模块职责

### 4.1 Tender Understanding（投标理解）

**入口：** `backend/services/tender_understanding.py`
**触发：** `POST /api/pipeline/run`

**职责：**
1. LLM 13维度结构化提取（Markdown报告 + JSON）
2. 正则增强（数字、日期、面积等）
3. 质量评分（完整性 / 证据性 / 就绪度）
4. 字段归一化（normalized_fields）

**关键概念：**
- **Field Registry**：每个字段有 priority（P0/P1/P2）、impact（影响的模块）、usable_statuses
- **Readiness Score**：P0×50% + P1×35% + P2×15% 加权进度

### 4.2 Tender Clarification（澄清闭环）

**入口：** `backend/services/clarification_manager.py`
**触发：** `POST /api/clarification/recompute/{pipeline_id}`

**职责：**
1. 字段合并优先级：manual > extracted > assumed
2. 就绪度重算（考虑合并后状态）
3. 澄清任务生成（P0阻塞 / P1建议 / 冲突 / 假设审查）
4. downstream_input 重建（用于成本测算）

**关键概念：**
- **ClarificationTask**：单个字段澄清任务，含问题文本、guidance、expected_input_type
- **ResolvedField**：合并后的字段状态，含 final_value / usable / source_type

### 4.3 Operation Model Derivation（运营模型推导）

**入口：** `backend/services/operation_profile_service.py`
**触发：** recompute_service 内部 Step 8b
**输入：** `service_scope` dict（结构化服务矩阵）

**推导链：**
```
service_scope matrix
    │
    ├──→ derive_operation_type()      # 运营类型（仓配/冷链/保税等）
    ├──→ calculate_complexity()        # 复杂度评分 0-20
    ├──→ derive_labor_modules()       # 7个人员模块
    ├──→ generate_operation_narrative() # 中文运营描述
    │
    ▼ build_process_modules()         # v0.6.6
    └──→ process_modules: {
            receiving_process: {steps, kpis},
            outbound_process: {steps, kpis},
            ...
        }
```

### 4.4 Cost Model（成本模型）

**入口：** `backend/downstream/downstream_input_builder.py`
**触发：** downstream_input_builder.build_cost_model_input()

**职责：**
1. 从 analyzer_result 构建 required_inputs
2. 判断推荐模式（blocked / range_estimate / full_calc）
3. 生成澄清问题
4. 分类 source_inputs / assumed_inputs / unusable_fields

**三种计算模式：**
- `full_calc`：P0 + P1 全部 provided → 精确 ROI
- `range_estimate`：P0 完整 + P1 有缺失 → 区间估算
- `blocked`：P0 有缺失 → 禁止测算

### 4.5 Process Templates（作业流程模板）

**入口：** `backend/services/process_templates.py`
**触发：** derive_operation_profile() 内部

**7个标准流程：**
- `receiving_process` — 车辆到达→卸货→质检→上架（8步）
- `outbound_process` — 订单释放→波次→拣选→包装→装车（11步）
- `storage_management` — 巡仓→盘点→补货→FIFO（7步）
- `return_process` — 退货接收→质检→分类→处理（7步）
- `va_process` — VA订单→配套→组装→质检（7步）
- `temperature_control` — 温控监控→预警→月台门禁（6步）
- `support_process` — 报表→系统对接→数据备份（4步）

每个流程含：step_id / key / label / role / kpis

---

## 五、Clarification 闭环流程

```
用户上传 RFQ
    ↓
Pipeline.run() — Tender Understanding
    ↓
提取结果 + Readiness = BLOCKED（初始）
    ↓
用户进入 Clarification Workspace
    ↓
查看 P0/P1 缺失字段列表
    ↓
逐个补录（文本/数字/选项/服务矩阵）
    ↓
点击「提交并重新计算」
    ↓
recompute_service
    ├── validate_manual_input()
    ├── resolve_all_fields()         # manual > extracted > assumed
    ├── compute_readiness_after_inputs()
    ├── build_clarification_tasks()
    ├── build_cost_model_input()     # downstream_input
    ├── derive_operation_profile()   # v0.6.5
    └── build_process_modules()      # v0.6.6
    ↓
状态更新：
  - readiness_score 上升
  - P0 缺失数下降
  - recommended_mode 变化（blocked→range_estimate→full_calc）
  - operation_profile / process_modules 生成
    ↓
前端展示变化摘要 + 3个可解释性面板
```

---

## 六、版本演进

| 版本 | 日期 | 核心能力 |
|------|------|---------|
| v0.1 | — | 正则提取 + 正则校验 |
| v0.2 | 2026-03 | LLM理解 + Readiness门禁 + Clarification问题 |
| v0.3 | — | QA规则引擎（ROI/Constraint） |
| v0.5 | — | LLM Extractor（MiniMax API） |
| v0.6.1 | 2026-03 | Clarification Workspace UI + 重算闭环 |
| v0.6.2 | 2026-03 | Schema同步 + resolved字段映射修复 |
| v0.6.3 | 2026-03 | 前端三面板（阻塞/假设/状态总览） |
| v0.6.4 | 2026-03 | Service Scope 从字符串→结构化矩阵 |
| v0.6.5 | 2026-03 | Operation Profile 自动推导 |
| **v0.6.6** | **2026-03** | **Process Modules 作业流程自动生成** |

---

## 七、技术栈

| 层 | 技术 |
|----|------|
| 前端 | Streamlit（Python） |
| API | FastAPI + Pydantic |
| 业务逻辑 | Python 3.11（typed） |
| 持久化 | SQLite + SQLAlchemy 2.x |
| LLM | MiniMax API（M2.7-highspeed）+ OpenAI兼容接口 |
| 测试 | pytest |
| 部署 | uvicorn（本地） |

---

## 八、关键设计决策

### 8.1 双层 Schema 架构
`tender_schema.py`（理解层）和 `cost_model_requirements.py`（成本层）各有一份字段定义。**必须保持同步**，否则会出现"理解层就绪但成本层阻塞"的矛盾。

### 8.2 resolved 字段传递链
```
ResolvedField (final_value/usable/final_status)
    ↓ resolved_as_normalized[]
    ↓ (status="provided" if usable else "missing")
    ↓ analyzer_result["normalized_fields"]
    ↓ build_cost_model_input()
    ↓ required_inputs[fkey]
    ↓ (usable, usable_reason)
```
任何一环类型不匹配都会导致字段"消失"。v0.6.2 的主要工作就是修复这个链路。

### 8.3 downstream_input 是唯一入口
所有下游模块（Cost Model / Solution Design）必须从 `build_cost_model_input()` 的返回值读取字段。禁止直接从 PipelineRun 的 JSON 字段读取。

### 8.4 service_scope 升为 P0
服务范围决定成本结构（labor / equipment / OPEX），必须完整明确。v0.6.4 将其从 P1 升为 P0。

---

## 九、路线图

```
v0.6.x  ▸ Clarification 质量门禁 + 可解释性
v0.7    ▸ Solution Studio（Base/Automation/Optimization 三方案）
v0.8    ▸ Tender Writer（自动输出投标方案 PDF）
```

---

*文档版本：v0.6.6 | 最后更新：2026-03-29*
