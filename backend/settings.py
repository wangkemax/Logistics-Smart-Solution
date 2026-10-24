"""Process configuration. Empty API_KEY disables auth so local dev still runs."""
from __future__ import annotations

import os

COMPANY_NAME = os.getenv("COMPANY_NAME", "物流解决方案团队")

# Empty means auth is off. Set this before exposing the API.
API_KEY = os.getenv("API_KEY", "").strip()

# Comma-separated browser origins. Never combine "*" with credentials.
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:8501,http://127.0.0.1:8501",
)
CORS_ALLOW_CREDENTIALS = os.getenv("CORS_ALLOW_CREDENTIALS", "false").lower() in (
    "1",
    "true",
    "yes",
)

def max_pdf_bytes() -> int:
    return int(os.getenv("MAX_PDF_BYTES", str(20 * 1024 * 1024)))


def cors_origins() -> list[str]:
    origins = [item.strip() for item in CORS_ORIGINS.split(",") if item.strip()]
    return origins or ["http://localhost:8501"]


def cors_allow_credentials() -> bool:
    origins = cors_origins()
    if "*" in origins:
        return False
    return CORS_ALLOW_CREDENTIALS
