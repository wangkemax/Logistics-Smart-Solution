"""
backend/api/rfp_api.py — v1.3 RFP Ingestion API Endpoints
========================================================

POST /rfp/extract             — 从 RFP 文本提取结构化字段
POST /rfp/extract/pdf         — 上传 RFP PDF 文件提取内容
POST /rfp/extract-and-clarify — 完整管道：提取 + 识别缺失 + 生成澄清问题
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel, ConfigDict
from typing import Optional

from backend.services.rfp_extractor import RFPExtractor

router = APIRouter(prefix="/rfp", tags=["rfp"])
_extractor = RFPExtractor()


# =============================================================================
# Request/Response models
# =============================================================================

class RFPExtractRequest(BaseModel):
    rfp_text: str
    language: str = "cn"


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    extracted: dict
    confidence_scores: dict
    extraction_confidence: float
    extraction_method: str
    text_length: int
    error: Optional[str] = None


class ClarificationQuestion(BaseModel):
    question_id: str
    field_key: str
    category: str
    question_text: str
    guidance: str
    unit_hint: str
    impact: str


class FullPipelineResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    extracted: dict
    confidence_scores: dict
    extraction_confidence: float
    extraction_method: str
    filled: dict
    missing_p0: list
    missing_p1: list
    low_confidence: list
    clarification_questions: list
    assumptions_registered: list
    total_questions: int
    p0_questions: int
    p1_questions: int
    error: Optional[str] = None
    run_id: Optional[str] = None


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/extract", response_model=ExtractionResponse)
def extract_from_text(request: RFPExtractRequest):
    """
    从 RFP 文本提取结构化字段。
    返回提取的字段值及每字段的置信度分数。
    """
    result = _extractor.extract_from_text(request.rfp_text, request.language)
    return ExtractionResponse(
        success=result.get("error") is None,
        extracted=result.get("extracted", {}),
        confidence_scores=result.get("confidence_scores", {}),
        extraction_confidence=result.get("extraction_confidence", 0.0),
        extraction_method=result.get("extraction_method", "unknown"),
        text_length=result.get("text_length", 0),
        error=result.get("error"),
    )


@router.post("/extract/pdf", response_model=ExtractionResponse)
async def extract_from_pdf(
    file: UploadFile = File(...),
    language: str = "cn",
):
    """
    上传 RFP PDF 文件提取内容。
    PDF 文件保存到临时路径，处理完成后自动删除。
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件格式")

    # Save to temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        content = await file.read()
        f.write(content)
        pdf_path = f.name

    try:
        result = _extractor.extract_from_pdf(pdf_path, language)
        return ExtractionResponse(
            success=result.get("error") is None,
            extracted=result.get("extracted", {}),
            confidence_scores=result.get("confidence_scores", {}),
            extraction_confidence=result.get("extraction_confidence", 0.0),
            extraction_method=result.get("extraction_method", "unknown"),
            text_length=result.get("text_length", 0),
            error=result.get("error"),
        )
    finally:
        # Clean up temp file
        try:
            os.unlink(pdf_path)
        except OSError:
            pass


@router.post("/extract-and-clarify", response_model=FullPipelineResponse)
def extract_and_clarify(
    request: RFPExtractRequest,
    run_id: Optional[str] = None,
):
    """
    完整管道：提取 + 识别缺失 + 生成澄清问题。
    可选传入 run_id，将已提取字段注册为 Assumptions（source="rfp_extracted"）。
    """
    result = _extractor.run_full_pipeline(
        rfp_text=request.rfp_text,
        pdf_path=None,
        run_id=run_id,
    )
    return FullPipelineResponse(
        success=result.get("success", False),
        extracted=result.get("extracted", {}),
        confidence_scores=result.get("confidence_scores", {}),
        extraction_confidence=result.get("extraction_confidence", 0.0),
        extraction_method=result.get("extraction_method", "unknown"),
        filled=result.get("filled", {}),
        missing_p0=result.get("missing_p0", []),
        missing_p1=result.get("missing_p1", []),
        low_confidence=result.get("low_confidence", []),
        clarification_questions=result.get("clarification_questions", []),
        assumptions_registered=result.get("assumptions_registered", []),
        total_questions=result.get("total_questions", 0),
        p0_questions=result.get("p0_questions", 0),
        p1_questions=result.get("p1_questions", 0),
        error=result.get("error"),
        run_id=run_id,
    )
