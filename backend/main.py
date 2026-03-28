from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes import router as api_router
from backend.api import report_api
from agents import orchestrator
from backend.models.database import init_db
import os

app = FastAPI(
    title="Logistics Smart Solution API",
    description="AI-powered warehouse automation recommendation, cost analysis, and presale pipeline",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(report_api.router)
app.include_router(orchestrator.router)


@app.on_event("startup")
async def startup_event():
    os.makedirs("data", exist_ok=True)
    os.makedirs("data/pipelines", exist_ok=True)
    init_db()


@app.get("/")
def root():
    return {
        "message": "Logistics Smart Solution API",
        "version": "0.2.0",
        "docs": "/docs",
        "health": "/api/health",
        "endpoints": {
            "recommend": "/api/recommend",
            "compare": "/api/compare",
            "cost": "/api/cost",
            "report": "/api/report",
            "pipeline": "/api/pipeline/run",
            "pipeline_extract": "/api/pipeline/extract",
        }
    }
