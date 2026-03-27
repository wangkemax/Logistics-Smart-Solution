from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes import router
from backend.models.database import init_db
import os

app = FastAPI(
    title="Logistics Presale AI API",
    description="API for warehouse automation recommendations and cost calculations",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def startup_event():
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    init_db()


@app.get("/")
def root():
    return {
        "message": "Logistics Presale AI System",
        "docs": "/docs",
        "health": "/api/health"
    }
