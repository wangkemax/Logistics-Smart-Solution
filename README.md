# Logistics Smart Solution
### AI-Powered Logistics Presale Copilot

[![CI](https://github.com/wangkemax/Logistics-Smart-Solution/actions/workflows/ci.yml/badge.svg)](https://github.com/wangkemax/Logistics-Smart-Solution/actions)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.55+-red.svg)](https://streamlit.io/)

> AI-powered logistics presale copilot for **tender analysis**, **warehouse automation recommendation**, **ROI comparison**, and **professional proposal generation**.

一个可以演示的物流售前 AI 系统：从招标文件解析 → 自动化场景推荐 → 多方案 ROI 对比 → PDF 方案建议书，**全流程可演示、端到端可操作**。

---

## 🎯 系统能力

| 能力 | 说明 |
|------|------|
| **Tender 解析** | 上传招标文件（PDF/DOCX/TXT），提取面积/SKU/订单量/行业/痛点 |
| **智能推荐** | 基于 15 种自动化场景的 AI 推荐，覆盖电商/3PL/制造/零售/快递/医药等 |
| **成本测算** | 自动化 CAPEX + 年维护 + 节省人力 → 5 年 ROI + 回本周期 |
| **多方案对比** | 横向对比 2-5 个方案的 ROI、投资、回本、省人数字 |
| **PDF 报告** | 一键生成专业投标方案建议书（Jinja2 + WeasyPrint，中英双语） |
| **Pipeline 编排** | 异步非阻塞执行，5 步实时状态（✅/⏳），支持中途参数修正 |

---

## 🏗 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      用户界面 (Streamlit)                    │
│   ┌──────────┐  ┌────────────────────┐  ┌──────────────┐  │
│   │ 📋 方案生成 │  │  ⚖️ 多方案对比     │  │ 🚀 Pipeline Run │  │
│   └──────────┘  └────────────────────┘  └──────────────┘  │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP / JSON
┌────────────────────────────▼────────────────────────────────┐
│                   FastAPI Backend (异步线程)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │ /api/recommend│  │ /api/compare │  │ /api/pipeline/* │   │
│  │ /api/cost    │  │ /api/report  │  │ /api/pipeline/run│   │
│  └──────────────┘  └──────────────┘  └─────────────────┘   │
└────────────────────────────┬────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
  │  SQLite     │    │   Redis     │    │  WeasyPrint  │
  │  (状态持久化) │    │ (Pipeline   │    │ (PDF 生成)   │
  │             │    │  实时状态)   │    │             │
  └─────────────┘    └─────────────┘    └─────────────┘
```

---

## 📂 项目结构

```
logistics-presale-ai/
├── backend/
│   ├── api/
│   │   ├── routes.py         # FastAPI 路由（recommend/cost/compare/report）
│   │   └── report_api.py      # PDF 报告接口
│   ├── engines/
│   │   ├── automation_engine.py  # 推荐引擎（15 种场景评分）
│   │   └── cost_engine.py        # 成本引擎
│   ├── models/
│   │   └── database.py       # SQLAlchemy 模型
│   ├── schemas/
│   │   └── schemas.py        # Pydantic 请求/响应模型
│   ├── services/
│   │   └── project_service.py # 业务逻辑层
│   ├── workers/
│   │   └── pipeline_tasks.py  # 异步 Pipeline 任务（线程执行）
│   └── main.py
├── frontend/
│   └── dashboard/
│       └── app.py            # Streamlit 三模式界面
├── report/
│   ├── generator.py          # PDF 生成引擎
│   ├── templates/
│   │   └── report_template.html  # Jinja2 报告模板
│   └── styles/
│       └── report.css        # 报告样式
├── agents/
│   ├── orchestrator.py       # Pipeline 编排 + API 路由
│   └── *.yaml               # Agent 职责定义
├── scripts/
│   └── init_db.py           # 数据库初始化
├── data/                     # SQLite 数据库 + PDF 存储
├── tests/                    # pytest 测试套件
└── docker-compose.yml
```

---

## 🚀 快速启动

### 环境要求
- Python 3.11+
- Redis（本地开发可省略，使用线程模式）

### 方式一：本地启动

```bash
# 1. 克隆
git clone https://github.com/wangkemax/Logistics-Smart-Solution.git
cd Logistics-Smart-Solution

# 2. 安装依赖
pip install -e ".[dev]"
pip install weasyprint jinja2  # PDF 生成

# 3. 初始化数据库
python3 scripts/init_db.py

# 4. 启动后端（终端 1）
uvicorn backend.main:app --reload --port 8000

# 5. 启动前端（终端 2）
streamlit run frontend/dashboard/app.py --server.port 8501
```

> 访问 http://localhost:8501

### 方式二：Docker 一键启动

```bash
docker compose up --build
```

> - 前端：http://localhost:8501
> - 后端：http://localhost:8000
> - API 文档：http://localhost:8000/docs

---

## 📡 API 端点

### 核心业务

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/project` | 创建项目 |
| `POST` | `/api/recommend` | 获取自动化方案推荐 |
| `POST` | `/api/cost` | 单方案成本测算 |
| `POST` | `/api/compare` | 多方案 ROI 对比 |
| `POST` | `/api/report` | 生成 PDF 方案报告 |
| `POST` | `/api/report/compare` | 生成 PDF 对比报告 |
| `GET` | `/api/health` | 健康检查 |

### Pipeline（异步，非阻塞）

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/pipeline/run` | 启动完整 Pipeline（立即返回 pipeline_id）|
| `GET` | `/api/pipeline/status/{id}` | 查询 5 步实时进度 |
| `PATCH` | `/api/pipeline/{id}` | 中途修正参数（如低置信度修正）|
| `GET` | `/api/pipeline/{id}/download` | 下载生成的 PDF |
| `GET` | `/api/pipeline/{id}/compare-scenarios` | 对比指定方案列表 |

### Pipeline 执行流程

```
① 招标文件解析  →  ② 推荐引擎  →  ③ ROI 计算  →  ④ QA 审核  →  ⑤ PDF 报告
   (PDF/DOCX)       (15场景)      (对比)       (质量门禁)     (可下载)
```

每个步骤完成即写入 Redis，前端每 2 秒轮询刷新状态。

---

## 🖥 三种使用模式

### 1️⃣ 方案生成
单方案推荐：输入项目参数 → 获取 TOP 5 自动化方案 → 查看成本拆解 → 一键 PDF。

### 2️⃣ 多方案对比
横向 ROI 对比：输入参数 + 选择 2-5 个方案 → 生成对比表、柱状图、雷达图 → 高亮最优方案。

### 3️⃣ Pipeline Run（异步）
端到端投标流程：
1. 上传招标文件（PDF/DOCX/TXT）或粘贴摘要
2. 填写项目参数（支持自动从文件中提取）
3. 点击"🚀 开始运行 Pipeline"
4. 实时查看 5 步执行状态（✅/⏳/❌）
5. 低置信度时弹出参数修正表单
6. Pipeline 完成后在右侧结果区显示：画像 / ROI / 图表 / TOP5 / PDF 下载

---

## 📄 PDF 报告

生成的 PDF 包含 9 个章节：

| 章节 | 内容 |
|------|------|
| 封面 | 项目名称、行业、面积、日期 |
| 项目背景 | 仓库面积、SKU、日均订单、库存量 |
| 客户需求分析 | 行业特征、痛点识别 |
| 自动化场景推荐 | TOP 3 方案（含评分、投资范围、人工节省） |
| 投资成本分析 | CAPEX + 年维护 + 年节省 |
| ROI 分析 | 5 年 ROI、回本周期、加权评分 |
| 项目实施规划 | 实施阶段建议 |
| 风险分析 | 风险识别与应对策略 |
| 多方案对比 | 横向表格（含条件渲染） |

**支持语言**：中文（默认）/ 英文，切换方式：后端 `language` 参数。

---

## 🧪 测试

```bash
pytest tests/ -v
```

当前覆盖：自动化引擎推荐、成本引擎计算、API 端点。

---

## 🗺️ Roadmap

| 版本 | 目标 | 状态 |
|------|------|------|
| **v0.1** | MVP — 推荐 + 成本 + PDF | ✅ 完成 |
| **v0.2** | 异步 Pipeline + 3 栏 UI | ✅ 完成 |
| **v0.3** | 任务状态持久化（SQLite）| 进行中 |
| **v0.4** | 高级 UI（权重滑块实时刷新、雷达图）| 待开始 |
| **v0.5** | OpenClaw sessions_spawn LLM Extractor | 待开始 |
| **v0.6** | 知识库 + 历史案例学习 | 待开始 |

---

## 📦 15 种自动化场景

| 方案 | 类别 | 适用行业 | 人工节省 |
|------|------|---------|---------|
| AMR 拣选辅助 | 移动机器人 | 电商/3PL/零售 | 30% |
| GTP 货到人系统 | 货到人 | 电商/3PL | 50% |
| 输送分拣线 | 输送分拣 | 电商/快递/零售 | 40% |
| 立体仓库 AS/RS | 立体仓库 | 制造/3PL/医药 | 60% |
| 跨带分拣机 | 高速分拣 | 快递/电商 | 55% |
| 拆码垛机器人 | 搬运机器人 | 制造/3PL/零售 | 45% |
| AGV 搬运系统 | 移动机器人 | 制造/3PL | 40% |
| 自动包装线 | 包装自动化 | 电商/零售/3PL | 35% |
| WMS 仓储管理系统 | 软件系统 | 通用 | 15% |
| 自动化退货处理 | 逆向物流 | 电商/零售 | 30% |
| 冷链自动化仓储 | 冷链系统 | 食品/医药/生鲜 | 50% |
| 视觉识别质检 | 视觉检测 | 制造/医药/电商 | 25% |
| 货架式密集存储 | 密集存储 | 3PL/零售/制造 | 20% |
| 自动贴标系统 | 自动化辅助 | 制造/零售/3PL | 20% |
| 自动化输送线 | 输送系统 | 制造/电商/3PL | 30% |

---

## 📝 License

MIT
