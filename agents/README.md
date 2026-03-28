# Agents Directory

This directory contains the Agent definitions for the Logistics Smart Solution system.

## Architecture Overview

```
User Input (Tender Document / Project Profile)
         │
         ▼
   ┌─────────────┐
   │ CEO Agent   │ ← Orchestration brain (this system)
   └──────┬──────┘
          │ spawns
   ┌──────┴──────┬────────────────┐
   │             │                │
   ▼             ▼                ▼
Tender        Solution        Tender Writer
Extractor     Architect        Agent
Agent                         Agent
   │             │                │
   └──────┬──────┴────────┬───────┘
          │ calls          │ calls
          ▼                ▼
   ┌──────────────────────────────┐
   │   Smart Solution API Layer  │
   │  (this repo's FastAPI)      │
   │                              │
   │  POST /api/recommend        │
   │  POST /api/cost             │
   │  POST /api/compare          │
   │  POST /api/report           │
   └──────────────────────────────┘
```

## Agent Definitions

| Agent | Role | Output |
|-------|------|--------|
| `ceo-agent.yaml` | Orchestration + quality gate | Spawns agents, manages workflow |
| `tender-extractor.yaml` | Parse tender doc → structured profile | Project profile dict |
| `solution-architect.yaml` | Design 2-5 solution options | List of solution designs |
| `tender-writer.yaml` | Write formal tender document | Markdown tender draft |
| `qa-agent.yaml` | Quality review + gate | QA verdict (PASS/FAIL) |

## Integration with Smart Solution API

Agents should call the Smart Solution API for computational tasks:

```python
# Example: Solution Architect calls recommendation API
import requests

recommendations = requests.post(
    "http://localhost:8000/api/recommend",
    json={
        "industry": "电商",
        "warehouse_area": 20000,
        "sku_count": 30000,
        "daily_orders": 5000,
        "inventory": 500000,
        "labor_cost_level": "中",
        "budget_level": "中",
        "automation_expectation": "中",
    }
).json()
```

## Running Agents

Agents are executed via OpenClaw's `sessions_spawn`:

```python
sessions_spawn(
    task=agent_prompt,
    label="project-name-agent-name",
    runtime="subagent",
    mode="run",
    runTimeoutSeconds=600,
)
```

See `workflows/pipeline.yaml` for the standard execution sequence.
