from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.models.database import get_db
from backend.schemas.schemas import (
    ProjectProfileCreate, ProjectProfileResponse,
    RecommendationRequest, RecommendationResponse,
    CostRequest, CostResponse
)
from backend.services.project_service import (
    create_project, get_project, get_recommendations, get_cost_analysis
)

router = APIRouter(prefix="/api", tags=["presale"])


@router.post("/project", response_model=ProjectProfileResponse)
def create_project_endpoint(project: ProjectProfileCreate, db: Session = Depends(get_db)):
    """Create and save a new project profile."""
    return create_project(db, project)


@router.get("/project/{project_id}", response_model=ProjectProfileResponse)
def get_project_endpoint(project_id: int, db: Session = Depends(get_db)):
    """Get project by ID."""
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/recommend", response_model=RecommendationResponse)
def get_recommendations_endpoint(request: RecommendationRequest):
    """Get automation scenario recommendations based on project profile."""
    profile_dict = request.model_dump()
    result = get_recommendations(profile_dict)
    return result


@router.post("/cost", response_model=CostResponse)
def calculate_cost_endpoint(request: CostRequest):
    """Calculate cost breakdown for a project."""
    profile_dict = request.model_dump()
    region = profile_dict.pop("region", "华东")
    scenario_id = profile_dict.pop("selected_scenario_id", None)
    result = get_cost_analysis(profile_dict, region, scenario_id)
    return result


@router.get("/health")
def health_check():
    return {"status": "healthy", "service": "logistics-presale-ai"}
