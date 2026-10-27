from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from backend.api.routes import router as api_router
from backend.api import report_api
from backend.api import task_api
from backend.api import clarification_api
from backend.api import solution_api
from backend.api import workspace_api
from backend.api import proposal_api
from backend.api import document_api
from backend.api import equipment_api
from backend.api import financial_api
from backend.api import rfp_api
from backend.api import diff_api
from agents import orchestrator
from backend.models.database import init_db
from backend.settings import cors_allow_credentials, cors_origins
import os

_AUTH_EXEMPT = {"/", "/api/health", "/docs", "/openapi.json", "/redoc"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    """When API_KEY is set, require X-API-Key except on health and docs.

    Empty API_KEY leaves the check off so local development still starts.
    """

    async def dispatch(self, request, call_next):
        from backend.settings import API_KEY
        if not API_KEY or request.method == "OPTIONS" or request.url.path in _AUTH_EXEMPT:
            return await call_next(request)
        if request.headers.get("x-api-key") != API_KEY:
            return JSONResponse(status_code=401, content={"detail": "invalid or missing API key"})
        return await call_next(request)


app = FastAPI(
    title="Logistics Smart Solution API",
    description="AI-powered warehouse automation recommendation, cost analysis, and presale pipeline",
    version="0.7",
)

# API key is added first so CORS stays the outer middleware and can tag 401 responses.
app.add_middleware(APIKeyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=cors_allow_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(report_api.router)
app.include_router(task_api.router)
app.include_router(clarification_api.router)
app.include_router(solution_api.router)
app.include_router(workspace_api.router)
app.include_router(orchestrator.router)
app.include_router(proposal_api.router)
app.include_router(document_api.router)
app.include_router(equipment_api.router)
app.include_router(financial_api.router)
app.include_router(rfp_api.router)
app.include_router(diff_api.router)


@app.on_event("startup")
async def startup_event():
    os.makedirs("data", exist_ok=True)
    os.makedirs("data/pipelines", exist_ok=True)
    init_db()
    # Ensure automation_scenarios DB matches current DEFAULT_SCENARIOS (including new AUTO scenarios)
    from backend.repositories import seed_default_scenarios
    seed_default_scenarios()


@app.get("/")
def root():
    return {
        "message": "Logistics Smart Solution API",
        "version": "0.7",
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
