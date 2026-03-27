# 物流预售AI系统 (Logistics Presale AI)

A web-based system that recommends warehouse automation scenarios, calculates costs, and generates solution summaries for logistics presales.

## Features

- **智能推荐**: AI-powered automation scenario recommendations based on project profile
- **成本测算**: Accurate cost calculation with ROI analysis
- **方案报告**: Comprehensive solution summary generation
- **15种自动化场景**: AMR, GTP, 输送分拣, 立体仓库, 跨带分拣, 等

## Tech Stack

- **Backend**: FastAPI + SQLite + SQLAlchemy
- **Frontend**: Streamlit + Plotly
- **Testing**: pytest

## Quick Start

### Prerequisites
- Python 3.11+

### Installation

```bash
cd logistics-presale-ai
pip install -e ".[dev]"
```

### Initialize Database
```bash
python scripts/init_db.py
```

### Run Backend
```bash
uvicorn backend.main:app --reload --port 8000
```

### Run Frontend (in another terminal)
```bash
streamlit run frontend/dashboard/app.py
```

Open http://localhost:8501 in your browser.

## API Documentation

Once running, visit http://localhost:8000/docs for interactive API docs.

### Key Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/project | Create project |
| POST | /api/recommend | Get recommendations |
| POST | /api/cost | Calculate costs |
| GET | /api/health | Health check |

## Docker Deployment

```bash
docker-compose up --build
```

- Frontend: http://localhost:8501
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Running Tests

```bash
pytest tests/ -v
```

## Automation Scenarios

| Scenario | Category | Industry | Labor Saving |
|----------|----------|----------|--------------|
| AMR拣选辅助 | 移动机器人 | 电商/3PL/零售 | 30% |
| GTP货到人系统 | 货到人 | 电商/3PL | 50% |
| 输送分拣线 | 输送分拣 | 电商/快递/零售 | 40% |
| 自动贴标系统 | 自动化辅助 | 制造/零售/3PL | 20% |
| 立体仓库AS/RS | 立体仓库 | 制造/3PL/医药 | 60% |
| 自动化输送线 | 输送系统 | 制造/电商/3PL | 30% |
| 视觉识别质检 | 视觉检测 | 制造/医药/电商 | 25% |
| 拆码垛机器人 | 搬运机器人 | 制造/3PL/零售 | 45% |
| WMS仓储管理系统 | 软件系统 | 通用 | 15% |
| AGV搬运系统 | 移动机器人 | 制造/3PL | 40% |
| 自动包装线 | 包装自动化 | 电商/零售/3PL | 35% |
| 冷链自动化仓储 | 冷链系统 | 食品/医药/生鲜 | 50% |
| 跨带分拣机 | 高速分拣 | 快递/电商 | 55% |
| 货架式密集存储 | 密集存储 | 3PL/零售/制造 | 20% |
| 自动化退货处理 | 逆向物流 | 电商/零售 | 30% |

## Project Structure

```
logistics-presale-ai/
├── backend/
│   ├── api/routes.py          # FastAPI route handlers
│   ├── engines/
│   │   ├── automation_engine.py  # Recommendation engine
│   │   └── cost_engine.py        # Cost calculation engine
│   ├── models/database.py     # SQLAlchemy models
│   ├── schemas/schemas.py     # Pydantic schemas
│   ├── services/project_service.py
│   └── main.py
├── frontend/dashboard/app.py  # Streamlit dashboard
├── data/                      # CSV seed data
├── tests/                     # pytest test suite
├── scripts/                   # DB init scripts
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml
└── pyproject.toml
```
