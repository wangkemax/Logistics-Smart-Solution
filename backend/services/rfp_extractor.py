"""
backend/services/rfp_extractor.py — v1.3 RFP Ingestion Service
=============================================================

RFP/招标文件解析服务。
职责：
1. 上传 RFP 文本，利用 LLM 提取关键字段
2. 对比已提取字段与 Assumption Defaults，识别缺失项
3. 生成 Clarification Questions（澄清问题清单）
"""

from __future__ import annotations

import json
import re
import sys
import os
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.assumption_service import AssumptionService
from backend.services.tender_schema import FIELD_REGISTRY, FIELD_PRIORITY, P0_FIELDS, P1_FIELDS

# =============================================================================
# RFP Extraction Prompt
# =============================================================================

RFP_EXTRACTION_PROMPT = '''你是一个专业的物流招标文件解析专家。请从以下文本中提取结构化信息。

要求：
- 只提取文本中明确提到的信息，不要猜测
- 如果某个字段在文本中未提及，标记为 null 并附上 confidence=0.0
- 如果字段值是模糊的（如"约5000"），提取为数值并附上 confidence=0.6
- 如果字段值是明确的，附上 confidence=0.9

输出格式（JSON）：
{{
  "project_name": "...",
  "client_name": "...",
  "industry": "AUTOMOTIVE/ELECTRONICS/FMCG/MANUFACTURING/GENERIC_3PL",
  "region": "华东/华南/华北/华中/西部/东北",
  "warehouse_area": 25000,  // m²，无则为 null
  "dc_count": 1,  // 数量，无则为 null
  "sku_count": 50000,  // 无则为 null
  "daily_orders": 8000,  // 无则为 null
  "peak_orders": 12000,  // 无则为 null
  "labor_cost_level": "高/中/低/null",
  "budget_level": "高/中/低/null",
  "contract_years": 5,  // 无则为 null
  "automation_level": "高/中/低/null",
  "throughput_requirement": 8000,  // 无则为 null
  "special_requirements": "...",  // 温度带、合规等
  "confidence_scores": {{
    "warehouse_area": 0.9,
    "dc_count": 0.9,
    "sku_count": 0.6,
    "daily_orders": 0.9,
    "peak_orders": 0.6,
    "labor_cost_level": 0.7,
    "budget_level": 0.7,
    "contract_years": 0.8,
    "automation_level": 0.6,
    "throughput_requirement": 0.5,
    "special_requirements": 0.5
  }}
}}

招标文件内容：
{tender_text}
'''

# =============================================================================
# Clarification Question Templates (field_key -> question metadata)
# =============================================================================

_CLAR_QUESTION_TEMPLATES = {
    "warehouse_area": {
        "question": "请确认本项目仓库总面积（平方米）及各仓库面积分布。",
        "guidance": "建议填写范围：5000-100000 m²，可按各仓库分别填写。",
        "unit_hint": "平方米（m²）",
        "impact": "影响设备选型、布局设计和投资规模测算。",
    },
    "dc_count": {
        "question": "请确认本项目覆盖的仓库/DC数量及各仓库所在城市。",
        "guidance": "如多仓联动运营，请提供各仓库面积及功能定位。",
        "unit_hint": "个（配送中心）",
        "impact": "影响运营模式设计和成本分摊逻辑。",
    },
    "sku_count": {
        "question": "请确认投标SKU品类总数及ABC分类占比。",
        "guidance": "建议填写范围：1000-100000，可按品类估算。",
        "unit_hint": "品类数量（个）",
        "impact": "影响存储方式、拆零比例和人员配置。",
    },
    "daily_orders": {
        "question": "请确认日均出库订单量（件数）的统计口径：是否按自然日？峰值是多少？",
        "guidance": "请注明按件计还是按单计，提供淡旺季差异说明。",
        "unit_hint": "件/单（按自然日）",
        "impact": "影响自动化设备选型和人力测算。",
    },
    "peak_orders": {
        "question": "请确认旺季/峰值日均出库量及高峰期持续时长。",
        "guidance": "例如双11期间峰值约平时3倍，持续约15天。",
        "unit_hint": "件/单（峰值）",
        "impact": "影响峰值产能设计和设备冗余配置。",
    },
    "labor_cost_level": {
        "question": "请确认当地人工成本水平（月均工资）大致范围。",
        "guidance": "例如华东地区约6000-8000元/月，华南约5000-7000元/月。",
        "unit_hint": "元/月（人均）",
        "impact": "影响人力成本测算和ROI模型。",
    },
    "budget_level": {
        "question": "请确认本项目预算规模或预算等级（高/中/低）。",
        "guidance": "如有具体预算数字请提供，否则可给出等级区间。",
        "unit_hint": "万元，或高/中/低等级",
        "impact": "影响自动化方案选型和投资规模决策。",
    },
    "contract_years": {
        "question": "请确认合同期限（年）及是否有分期解锁条款。",
        "guidance": "例如3+2年，前3年锁定，后2年视KPI达成续约。",
        "unit_hint": "年",
        "impact": "影响ROI分摊测算和设备折旧模型。",
    },
    "automation_level": {
        "question": "请确认客户对自动化程度的期望或要求（如货架/AGV/AMR/交叉带分拣等）。",
        "guidance": "请描述期望的自动化场景或参考案例。",
        "unit_hint": "高/中/低，或具体设备类型",
        "impact": "直接影响投资规模和自动化方案设计。",
    },
    "throughput_requirement": {
        "question": "请确认系统吞吐量要求（件/小时或单/小时）。",
        "guidance": "请提供持续吞吐量和峰值吞吐量的具体数值。",
        "unit_hint": "件/小时 或 单/小时",
        "impact": "影响分拣系统、输送线和设备规格选型。",
    },
    "special_requirements": {
        "question": "请确认是否有特殊仓储要求，如温度带（冷藏/冷冻）、合规认证（医疗器械/GMP）等。",
        "guidance": "如有多个仓库，请分别说明各仓的特殊要求。",
        "unit_hint": "温度带/认证类型/其他特殊要求",
        "impact": "影响仓库建设标准、设备选型和合规成本。",
    },
    "industry": {
        "question": "请确认客户所属行业分类（汽车/电子/快消/制造/第三方物流）。",
        "guidance": "影响作业流程设计和设备选型逻辑。",
        "unit_hint": "行业类型",
        "impact": "影响成本测算模型和行业基准参照。",
    },
    "region": {
        "question": "请确认项目所在地区/城市。",
        "guidance": "请提供项目主要运营地所在省份和城市。",
        "unit_hint": "省份/城市",
        "impact": "影响人工成本、仓租成本和地区系数。",
    },
}

# Fields that map from RFP schema to assumption field keys
_FIELD_KEY_MAP = {
    "warehouse_area": "warehouse_area",
    "dc_count": "dc_count",
    "sku_count": "sku_count",
    "daily_orders": "daily_orders",
    "peak_orders": "peak_orders",
    "labor_cost_level": "labor_cost_level",
    "budget_level": "budget_level",
    "contract_years": "contract_years",
    "automation_level": "automation_expectation",
    "throughput_requirement": "throughput_requirement",
    "special_requirements": "special_requirements",
    "industry": "industry",
    "region": "region",
    "project_name": "project_name",
    "client_name": "client_name",
}

# Default confidence threshold — below this, field is flagged as low confidence
_CONFIDENCE_THRESHOLD = 0.5


# =============================================================================
# MiniMax LLM Helper (mirrors llm_extractor.py)
# =============================================================================

def _get_api_key() -> Optional[str]:
    """Get API key from env or .env file."""
    api_key = os.getenv("MINIMAX_API_KEY") or os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key
    try:
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k in ("MINIMAX_API_KEY", "OPENAI_API_KEY") and not v.startswith("your"):
                        os.environ[k] = v
                        return v
    except Exception:
        pass
    return None


def _call_minimax_llm(prompt: str, timeout: int = 30) -> Optional[dict]:
    """Call MiniMax or OpenAI API for LLM extraction."""
    api_key = _get_api_key()
    if not api_key:
        return None

    base_url = "https://api.minimaxi.com/anthropic"
    model = "MiniMax-M2.7-highspeed"
    if not api_key.startswith("sk-api-"):
        base_url = "https://api.openai.com/v1"
        model = "gpt-4o-mini"

    import urllib.request
    payload = {
        "model": model,
        "max_tokens": 8192,
        "messages": [{"role": "user", "content": prompt}]
    }
    req_url = f"{base_url}/v1/messages"
    req = urllib.request.Request(
        req_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
            content_list = result.get("content", [])
            raw_text = ""
            if isinstance(content_list, list):
                raw_text = "\n".join(b.get("text", "") for b in content_list if b.get("type") == "text")
            else:
                raw_text = str(content_list)
            print(f"[RFPExtractor] LLM raw_output_len={len(raw_text)}")
            return _parse_json_response(raw_text)
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        print(f"[RFPExtractor] HTTP {e.code} body: {body}")
        return None
    except Exception as e:
        print(f"[RFPExtractor] LLM API call failed: {e}")
        return None


def _parse_json_response(text: str) -> Optional[dict]:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            candidate = match.group(0)
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return None


# =============================================================================
# PDF Text Extraction Helper
# =============================================================================

def _extract_pdf_text(pdf_path: str) -> str:
    """
    Extract text from a PDF file.
    Uses pdfminer.six if available, otherwise returns an error dict as string.
    """
    try:
        from pdfminer.high_level import extract_text
        return extract_text(pdf_path)
    except ImportError:
        raise ImportError(
            "PDF读取需要安装 pdfminer.six。请运行: pip install pdfminer.six"
        )
    except Exception as e:
        raise RuntimeError(f"PDF读取失败: {e}")


# =============================================================================
# Main RFPExtractor Class
# =============================================================================

class RFPExtractor:
    """
    RFP/招标文件解析服务。
    """

    def __init__(self):
        self._assumption_svc = AssumptionService()

    # -------------------------------------------------------------------------
    # Core extraction
    # -------------------------------------------------------------------------

    def extract_from_text(
        self,
        rfp_text: str,
        language: str = "cn",
    ) -> dict:
        """
        从 RFP 文本中提取结构化字段。

        Returns:
            dict with extracted fields + confidence_scores + extraction_confidence
        """
        if not rfp_text or len(rfp_text.strip()) < 20:
            return self._empty_extraction()

        prompt = RFP_EXTRACTION_PROMPT.format(tender_text=rfp_text[:8000])
        llm_result = _call_minimax_llm(prompt)

        if llm_result:
            confidence_scores = llm_result.get("confidence_scores", {})
            extracted = {
                "project_name": llm_result.get("project_name"),
                "client_name": llm_result.get("client_name"),
                "industry": llm_result.get("industry"),
                "region": llm_result.get("region"),
                "warehouse_area": llm_result.get("warehouse_area"),
                "dc_count": llm_result.get("dc_count"),
                "sku_count": llm_result.get("sku_count"),
                "daily_orders": llm_result.get("daily_orders"),
                "peak_orders": llm_result.get("peak_orders"),
                "labor_cost_level": llm_result.get("labor_cost_level"),
                "budget_level": llm_result.get("budget_level"),
                "contract_years": llm_result.get("contract_years"),
                "automation_level": llm_result.get("automation_level"),
                "throughput_requirement": llm_result.get("throughput_requirement"),
                "special_requirements": llm_result.get("special_requirements"),
            }
            overall_conf = (
                sum(confidence_scores.values()) / max(len(confidence_scores), 1)
                if confidence_scores else 0.5
            )
            return {
                "extracted": extracted,
                "confidence_scores": confidence_scores,
                "extraction_confidence": overall_conf,
                "extraction_method": "llm",
                "text_length": len(rfp_text),
            }

        # Fallback: return empty extraction with 0 confidence
        print("[RFPExtractor] LLM extraction failed, returning empty extraction")
        return self._empty_extraction()

    def extract_from_pdf(self, pdf_path: str, language: str = "cn") -> dict:
        """
        从 PDF 文件提取文本，然后调用 extract_from_text。
        """
        try:
            pdf_text = _extract_pdf_text(pdf_path)
        except ImportError as e:
            return {
                "error": str(e),
                "extracted": {},
                "confidence_scores": {},
                "extraction_confidence": 0.0,
                "extraction_method": "pdf_failed",
            }
        except RuntimeError as e:
            return {
                "error": str(e),
                "extracted": {},
                "confidence_scores": {},
                "extraction_confidence": 0.0,
                "extraction_method": "pdf_failed",
            }

        if not pdf_text or len(pdf_text.strip()) < 20:
            return {
                "error": "PDF提取的文本内容过短或为空",
                "extracted": {},
                "confidence_scores": {},
                "extraction_confidence": 0.0,
                "extraction_method": "pdf_empty",
            }

        result = self.extract_from_text(pdf_text, language)
        result["source"] = "pdf"
        result["pdf_path"] = pdf_path
        return result

    # -------------------------------------------------------------------------
    # Missing field identification
    # -------------------------------------------------------------------------

    def identify_missing_fields(
        self,
        extracted: dict,
        assumption_defaults: dict,
    ) -> dict:
        """
        对比已提取字段与 Assumption Defaults，识别缺失项。

        Returns:
            {
                "filled": {field: value},
                "missing_p0": [...],
                "missing_p1": [...],
                "low_confidence": [...],
            }
        """
        # All target RFP fields that we care about
        rfp_target_fields = {
            "project_name", "client_name", "warehouse_area", "dc_count",
            "sku_count", "daily_orders", "peak_orders", "labor_cost_level",
            "budget_level", "contract_years", "automation_level",
            "throughput_requirement", "special_requirements", "industry", "region",
        }
        # Fields that map to different assumption keys in tender_schema
        rfp_to_assumption = {
            "automation_level": "automation_expectation",
            "throughput_requirement": "throughput_requirement",
        }
        p0_keys = set(P0_FIELDS)
        p1_keys = set(P1_FIELDS)

        filled = {}
        missing_p0 = []
        missing_p1 = []
        low_confidence = []
        confidence_scores = extracted.get("confidence_scores", {})

        # Iterate over ALL target fields (not just keys present in extracted)
        # so that truly missing fields are properly detected
        for field_key in rfp_target_fields:
            val = extracted.get(field_key)
            conf = confidence_scores.get(field_key, 1.0)
            assumption_key = rfp_to_assumption.get(field_key, field_key)

            is_filled = (
                val is not None
                and val != "null"
                and val != ""
                and val != 0
            )

            if is_filled:
                filled[field_key] = val
                if conf < _CONFIDENCE_THRESHOLD:
                    low_confidence.append(field_key)
            else:
                # Determine if P0 or P1 based on the assumption key
                if assumption_key in p0_keys:
                    missing_p0.append(field_key)
                elif assumption_key in p1_keys:
                    missing_p1.append(field_key)
                # Fields not in P0/P1 (industry, region, project_name, etc.) — skip

        return {
            "filled": filled,
            "missing_p0": list(set(missing_p0)),
            "missing_p1": list(set(missing_p1)),
            "low_confidence": list(set(low_confidence)),
        }

    # -------------------------------------------------------------------------
    # Clarification question generation
    # -------------------------------------------------------------------------

    def generate_clarification_questions(
        self,
        missing_p0: list,
        missing_p1: list,
        context: dict,
    ) -> list[dict]:
        """
        为缺失字段生成 Clarification Questions。

        Returns list of question dicts:
            {
                "question_id": "CLAR-001",
                "field_key": "sku_count",
                "category": "P0",
                "question_text": "...",
                "guidance": "...",
                "unit_hint": "...",
                "impact": "...",
            }
        """
        questions = []
        counter = 1

        all_missing = [(fk, "P0") for fk in missing_p0] + [(fk, "P1") for fk in missing_p1]

        for field_key, category in all_missing:
            template = _CLAR_QUESTION_TEMPLATES.get(field_key, {})
            question_text = template.get(
                "question",
                f"请确认「{field_key}」的具体数据或要求。",
            )
            guidance = template.get(
                "guidance",
                "请提供具体数值或等级描述。",
            )
            unit_hint = template.get(
                "unit_hint",
                "数值或描述",
            )
            impact = template.get(
                "impact",
                "影响下游成本测算和方案设计。",
            )

            questions.append({
                "question_id": f"CLAR-{counter:03d}",
                "field_key": field_key,
                "category": category,
                "question_text": question_text,
                "guidance": guidance,
                "unit_hint": unit_hint,
                "impact": impact,
            })
            counter += 1

        return questions

    # -------------------------------------------------------------------------
    # Full pipeline
    # -------------------------------------------------------------------------

    def run_full_pipeline(
        self,
        rfp_text: str,
        pdf_path: str | None = None,
        run_id: str | None = None,
    ) -> dict:
        """
        完整管道：
        1. extract_from_text（或从 pdf 读）
        2. identify_missing_fields
        3. generate_clarification_questions
        4. 将已提取字段注册为 Assumptions（source="rfp_extracted"）
        """
        # Step 1: extract
        if pdf_path:
            extract_result = self.extract_from_pdf(pdf_path)
        else:
            extract_result = self.extract_from_text(rfp_text)

        if extract_result.get("error") or extract_result.get("text_length", 1) == 0:
            return {
                "success": False,
                "error": extract_result.get("error") or "输入文本为空或过短",
                "extraction_confidence": 0.0,
                "clarification_questions": [],
            }

        extracted = extract_result.get("extracted", {})
        confidence_scores = extract_result.get("confidence_scores", {})

        # Step 2: identify missing fields
        # Use empty assumption_defaults (no prior assumptions for new RFP)
        assumption_defaults = {}
        missing_result = self.identify_missing_fields(extracted, assumption_defaults)

        # Step 3: generate clarification questions
        context = {
            "extracted": extracted,
            "confidence_scores": confidence_scores,
            "extraction_method": extract_result.get("extraction_method", "llm"),
        }
        questions = self.generate_clarification_questions(
            missing_result["missing_p0"],
            missing_result["missing_p1"],
            context,
        )

        # Step 4: register extracted fields as assumptions (if run_id provided)
        assumptions_registered = []
        if run_id:
            for field_key, value in missing_result["filled"].items():
                conf = confidence_scores.get(field_key, extract_result.get("extraction_confidence", 0.5))
                try:
                    self._assumption_svc.register(
                        run_id=run_id,
                        field_key=field_key,
                        value=str(value),
                        rule="rfp_extracted",
                        source="rfp_extracted",
                        source_type="rfp_extracted",
                        confidence=conf,
                    )
                    assumptions_registered.append(field_key)
                except Exception as e:
                    print(f"[RFPExtractor] Failed to register assumption {field_key}: {e}")

        return {
            "success": True,
            "extracted": extracted,
            "confidence_scores": confidence_scores,
            "extraction_confidence": extract_result.get("extraction_confidence", 0.0),
            "extraction_method": extract_result.get("extraction_method", "llm"),
            "filled": missing_result["filled"],
            "missing_p0": missing_result["missing_p0"],
            "missing_p1": missing_result["missing_p1"],
            "low_confidence": missing_result["low_confidence"],
            "clarification_questions": questions,
            "assumptions_registered": assumptions_registered,
            "total_questions": len(questions),
            "p0_questions": sum(1 for q in questions if q["category"] == "P0"),
            "p1_questions": sum(1 for q in questions if q["category"] == "P1"),
        }

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _empty_extraction(self) -> dict:
        return {
            "extracted": {},
            "confidence_scores": {},
            "extraction_confidence": 0.0,
            "extraction_method": "empty_input",
            "text_length": 0,
        }
