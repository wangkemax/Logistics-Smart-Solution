from fastapi import APIRouter, HTTPException
from backend.services.financial_service import FinancialService
from backend.schemas.financial_schemas import FinancialInput, FinancialResult

router = APIRouter(prefix="/financial", tags=["financial"])
_service = FinancialService()


@router.post("/calculate", response_model=FinancialResult)
def calculate_financial(input: FinancialInput):
    """
    输入财务参数，输出完整财务测算结果。
    包括 CAPEX 汇总、OPEX 分解、ROI/IRR/Payback、现金流量表。
    """
    return _service.calculate(input)


@router.post("/calculate-and-save/{workspace_id}", response_model=FinancialResult)
def calculate_and_save(workspace_id: str, input: FinancialInput):
    """计算并保存财务快照"""
    input.workspace_id = workspace_id
    result = _service.calculate(input)
    _service.save_snapshot(result, workspace_id, snapshot_version=1)
    return result
