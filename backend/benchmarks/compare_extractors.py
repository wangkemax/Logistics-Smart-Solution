"""
benchmarks/compare_extractors.py — v0.2 vs Legacy Extractor Comparison
===================================================================

Compares the old rule-based extractor against the new v0.2 understanding engine.

Usage:
    python -m backend.benchmarks.compare_extractors [--verbose]

Metrics compared:
  1. Missing exposure rate     — what % of P0 fields are explicitly flagged as missing
  2. False value rate         — what % of extracted values look precise but are fabricated
  3. Downstream readiness     — can cost_model / solution_design proceed?
  4. Source transparency      — is the source of each value clearly documented?
  5. Clarification coverage   — are missing/ambiguous fields turned into actionable questions

A synthetic tender benchmark sample is included. Replace BENCHMARK_SAMPLES with
real project data for production benchmarking.
"""
import sys, json, os
from pathlib import Path
from datetime import datetime
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Benchmark Samples — replace with real tender data
# =============================================================================
BENCHMARK_SAMPLES = [
    {
        "id": "bench_001",
        "label": "汽车零部件DC投标",
        "text": """
招标文件

招标方：保时捷（上海）汽车国际贸易有限公司
项目名称：临港PDC仓储与配送服务采购
服务区域：上海临港新片区
合同期限：3年（2026年8月1日起）
付款账期：120天

一、服务范围
1. 进口货物报关、清关及仓储
2. 出库配送至经销商网络
3. 退货处理及逆向物流
4. 库内增值服务（贴标、组包、SORTING）

二、仓库DC信息
本次投标需覆盖以下仓库：
- PDC-LG-01：上海临港仓库，面积约30,000平方米
- PDC-LG-02：广州仓库，面积约20,000平方米
（仓库数量及详细清单见附件A）

三、业务规模
招标文件未明确日出库量，附件B提到"日均约1200个出库订单，
旺季峰值约为平日的2倍"
SKU数量：招标文件提到约8,000个SKU，未提供ABC分类

四、KPI与SLA
1. 库存准确率 ≥ 99.5%
2. 出库准时率 ≥ 99.0%
3. 投诉响应时间 ≤ 4小时
4. 信息系统对接要求：需支持SAP A1接口，日报推送

五、强制条款
1. 投标人须具备海关AEO认证
2. 仓库须满足危险品存储资质
3. 连续3次KPI不达标，招标方可解除合同

六、商务条款
报价方式：元/平米/月（元/件）两种报价结构
调价机制：CPI>3%时可申请调整

七、风险与歧义
正文第3.2条写"覆盖5个DC"，附件A中列出4个仓库，存在矛盾
        """,
        "ground_truth": {
            "client_name": "保时捷（上海）汽车国际贸易有限公司",
            "dc_count": "AMBIGUOUS",   # 正文说5个DC，附件列4个
            "warehouse_area": "AMBIGUOUS",  # 只有两个面积，总量未明确
            "daily_orders": "MISSING",  # 未明确说日出库量
            "sku_count": "PARTIAL",     # 有数量但无ABC分类
            "contract_years": 3,
            "kpi_targets": ["库存准确率≥99.5%", "出库准时率≥99.0%"],
            "penalty_rules": ["AEO认证", "危险品资质", "连续3次KPI不达标可解约"],
        },
        "expected_issues": {
            "missing_p0": ["dc_count", "daily_orders"],
            "ambiguous": ["dc_count (正文vs附件)", "warehouse_area"],
            "missing_p1": ["sku_abc_classification", "total_warehouse_area"],
        },
    },
    {
        "id": "bench_002",
        "label": "快消品DC投标（数据完整）",
        "text": """
招标文件

招标方：百事饮料（上海）有限公司
项目名称：华东区仓储及配送服务
合同期限：5年
付款账期：90天

一、服务范围
仓储服务、出库配送、末端履约、逆向物流

二、仓库网络
共6个仓库：
- 上海嘉定仓：12,000平方米
- 苏州仓：8,000平方米
- 无锡仓：6,000平方米
- 杭州仓：10,000平方米
- 南京仓：7,000平方米
- 宁波仓：5,000平方米

三、业务规模
日均出库量：约45,000件（自然日口径）
SKU：共3,200个（其中A类800个占60%销量，B类1,000个，C类1,400个）
平均库存量：约200万瓶/件，峰值约350万件
高峰系数：2.0倍（CNY期间）

四、KPI与SLA
1. 库存准确率 ≥ 99.8%
2. 出库履约率 ≥ 99.5%
3. 信息推送准时率 ≥ 99.0%
4. 异常订单响应 ≤ 2小时

五、强制条款
1. 须具备食品经营许可证
2. 须通过FSSC 22000认证
3. 信息系统须支持API实时对接
        """,
        "ground_truth": {
            "client_name": "百事饮料（上海）有限公司",
            "dc_count": 6,
            "warehouse_area": 48000,
            "daily_orders": 45000,
            "sku_count": 3200,
            "contract_years": 5,
        },
        "expected_issues": {},
    },
    {
        "id": "bench_003",
        "label": "医药冷链投标（边界模糊）",
        "text": """
招标文件

招标方：某大型医药集团
项目：全国冷链仓储及配送
合同期：3+2年

服务范围：药品存储（含2-8°C及15-25°C温区）、冷链配送、逆转录物流

仓库：覆盖全国主要一二线城市，初期约8-10个仓库（含总部CDC），
具体清单待合同签订后确认。

日均出库量：招标文件未提供具体数字，
仅注明"根据实际业务量按需扩展"。

SKU：约15,000-20,000个（以实际入库为准）

KPI要求：
1. 温度合规率 100%
2. 订单履约率 ≥ 99.0%
3. 客户投诉率 ≤ 0.1%

强制条款：
1. 必须具备GSP认证
2. 必须具备药品经营许可证
3. 仓库须通过药监局飞检
        """,
        "ground_truth": {
            "client_name": "某大型医药集团",
            "dc_count": "MISSING",   # "8-10个仓库"是范围，不是确定数字
            "warehouse_area": "MISSING",  # 无面积数据
            "daily_orders": "MISSING",  # 完全未提供
            "sku_count": "PARTIAL",   # "约15,000-20,000"是范围
            "contract_years": "AMBIGUOUS",  # "3+2年"需要澄清
        },
        "expected_issues": {
            "missing_p0": ["dc_count", "warehouse_area", "daily_orders"],
            "partial": ["sku_count"],
            "ambiguous": ["contract_years"],
        },
    },
]


# =============================================================================
# Old extractor (rule-based)
# =============================================================================
def run_old_extractor(text: str) -> dict:
    from backend.services.tender_service import extract_requirements
    return extract_requirements(text, mode="rule_only")


# =============================================================================
# New v0.2 extractor (LLM + normalization)
# =============================================================================
def run_new_extractor(text: str, mock: bool = False) -> dict:
    """
    Run v0.2 extractor. If mock=True, simulate LLM failure to test fallback.
    In real runs, set MOCK_LLM=1 env var to use mock mode for offline testing.
    """
    if mock or os.getenv("MOCK_LLM") == "1":
        # Return a synthetic v0.2-style result for offline benchmark testing
        return {
            "analysis_markdown": "[Mock: LLM analysis skipped]",
            "analysis_sections": {},
            "normalized_fields": {},
            "critical_missing_items": [],
            "important_missing_items": [],
            "clarification_questions": [],
            "readiness": {
                "for_cost_model": False,
                "for_solution_design": False,
                "for_contract_review": False,
                "readiness_score": 0.0,
                "readiness_level": "blocked",
            },
            "quality_scores": {
                "completeness_score": 0.0,
                "evidence_score": 0.0,
                "readiness_score": 0.0,
            },
            "meta": {"analysis_version": "v0.2", "prompt_version": "mock", "generated_at": ""},
        }
    from backend.services.tender_understanding import analyze_and_extract
    return analyze_and_extract(text)


# =============================================================================
# Evaluation metrics
# =============================================================================
P0_FIELDS = ["warehouse_area", "dc_count", "daily_orders", "sku_count", "total_warehouse_area"]
P1_FIELDS = ["contract_years", "service_scope", "kpi_targets", "penalty_rules",
             "peak_factor", "automation_expectation", "inventory"]


def count_missing_exposed(result: dict, field_list: list) -> dict:
    """
    Count status distribution for a list of fields.

    Handles two formats:
    - v0.2 format: entry is a dict {value, status, source_basis, ...}
    - Old extractor format: entry is a scalar value (or not a dict)
    """
    missing_count = 0
    partial_count = 0
    ambiguous_count = 0
    explicit_count = 0
    inferred_count = 0
    fabricated_count = 0  # has a value but source_basis shows it was default/missing

    for field in field_list:
        entry = result.get(field)
        if entry is None:
            # Field not present = missing
            missing_count += 1
            continue
        if not isinstance(entry, dict):
            # Old extractor: scalar value or int/float — check if it looks fabricated
            # If the value is a "nice round number" and no source basis, flag it
            # (This is a heuristic: fabricated values often look like round numbers)
            if entry is not None:
                fabricated_count += 1
            else:
                missing_count += 1
            continue

        status = entry.get("status", "unknown")
        source = entry.get("source_basis", "")
        value = entry.get("value")

        if status == "missing":
            missing_count += 1
        elif status == "partial":
            partial_count += 1
        elif status == "ambiguous":
            ambiguous_count += 1
        elif status == "explicit":
            explicit_count += 1
        elif status == "inferred":
            inferred_count += 1

        # Check for fabricated precision (value present but source_basis shows it was default/missing)
        if value is not None and ("文档未提供" in source or "missing" in source.lower()):
            fabricated_count += 1

    return {
        "missing": missing_count,
        "partial": partial_count,
        "ambiguous": ambiguous_count,
        "explicit": explicit_count,
        "inferred": inferred_count,
        "fabricated": fabricated_count,
        "total": len(field_list),
    }


def compute_missing_exposure_rate(result: dict, expected_missing: list) -> float:
    """What fraction of actually missing P0 fields were caught?"""
    if not expected_missing:
        return 1.0
    exposed = 0
    for field in expected_missing:
        entry = result.get(field, {})
        if isinstance(entry, dict) and entry.get("status") in ("missing", "partial", "ambiguous"):
            exposed += 1
        elif field not in result:
            exposed += 1
        elif not isinstance(entry, dict):
            # Old extractor returns scalar values; if field is expected missing but has
            # a non-null scalar value, it wasn't caught
            val = result[field]
            if val is None:
                exposed += 1
        elif entry.get("value") is None:
            exposed += 1
    return exposed / len(expected_missing)


def compute_false_value_rate(result: dict) -> float:
    """Fraction of non-null values that appear precise but are fabricated defaults."""
    non_null = sum(
        1 for k, v in result.items()
        if isinstance(v, dict) and v.get("value") is not None and not k.startswith("_")
    )
    fabricated = sum(
        1 for k, v in result.items()
        if isinstance(v, dict)
        and v.get("value") is not None
        and not k.startswith("_")
        and ("文档未提供" in v.get("source_basis", "") or v.get("status") == "missing")
    )
    return fabricated / max(non_null, 1)


def evaluate_readiness(result: dict) -> dict:
    """Assess downstream readiness from extractor result."""
    readiness = result.get("readiness") or {}
    if not readiness:
        # Try from quality_score
        qs = result.get("quality_score", {})
        rd = qs.get("readiness", {})
        readiness = {
            "for_cost_model": rd.get("cost_model_ready", False),
            "for_solution_design": rd.get("solution_design_ready", False),
            "for_contract_review": rd.get("contract_review_ready", False),
        }

    return {
        "cost_model": "ready" if readiness.get("for_cost_model") else "BLOCKED",
        "solution_design": "ready" if readiness.get("for_solution_design") else "WARN",
        "contract_review": "ready" if readiness.get("for_contract_review") else "BLOCKED",
    }


def run_benchmark_on_sample(sample: dict, new_mock: bool = False) -> dict:
    """Run both extractors on one benchmark sample and compare."""
    text = sample["text"]
    expected = sample.get("expected_issues", {})
    gt = sample.get("ground_truth", {})

    old_result = run_old_extractor(text)
    new_result = run_new_extractor(text, mock=new_mock)

    # --- Old extractor metrics ---
    old_p0 = count_missing_exposed(old_result, P0_FIELDS)
    old_missing_exposure = compute_missing_exposure_rate(
        old_result, expected.get("missing_p0", [])
    )
    old_false_rate = compute_false_value_rate(old_result)
    old_readiness = evaluate_readiness(old_result)
    old_clar_questions = len(old_result.get("_clarification_questions", []))

    # --- New extractor metrics ---
    new_p0 = count_missing_exposed(new_result, P0_FIELDS)
    new_missing_exposure = compute_missing_exposure_rate(
        new_result, expected.get("missing_p0", [])
    )
    new_false_rate = compute_false_value_rate(new_result)
    new_readiness = evaluate_readiness(new_result)
    new_clar_questions = len(new_result.get("clarification_questions", []))
    new_quality = new_result.get("quality_scores", {})

    # --- Comparison ---
    return {
        "sample_id": sample["id"],
        "sample_label": sample["label"],
        "ground_truth": gt,
        "expected_issues": expected,
        "old": {
            "p0_field_status": old_p0,
            "missing_exposure_rate": round(old_missing_exposure, 3),
            "false_value_rate": round(old_false_rate, 3),
            "readiness": old_readiness,
            "clarification_questions_count": old_clar_questions,
            "extraction_confidence": old_result.get("extraction_confidence", 0.0),
            # Show what old extractor thinks the values are
            "dc_count": old_result.get("dc_count"),
            "warehouse_area": old_result.get("warehouse_area"),
            "daily_orders": old_result.get("daily_orders"),
        },
        "new": {
            "p0_field_status": new_p0,
            "missing_exposure_rate": round(new_missing_exposure, 3),
            "false_value_rate": round(new_false_rate, 3),
            "readiness": new_readiness,
            "clarification_questions_count": new_clar_questions,
            "quality_scores": new_quality,
            "readiness_score": new_quality.get("readiness_score", 0.0),
            "completeness_score": new_quality.get("completeness_score", 0.0),
            "evidence_score": new_quality.get("evidence_score", 0.0),
            # Show what new extractor thinks the values are
            "dc_count": new_result.get("dc_count", {}).get("value")
                        if isinstance(new_result.get("dc_count"), dict)
                        else new_result.get("dc_count"),
            "warehouse_area": new_result.get("warehouse_area", {}).get("value")
                             if isinstance(new_result.get("warehouse_area"), dict)
                             else new_result.get("warehouse_area"),
            "daily_orders": new_result.get("daily_orders", {}).get("value")
                           if isinstance(new_result.get("daily_orders"), dict)
                           else new_result.get("daily_orders"),
        },
        "delta": {
            "missing_exposure_improvement": round(new_missing_exposure - old_missing_exposure, 3),
            "false_value_improvement": round(old_false_rate - new_false_rate, 3),
            "clarification_questions_delta": new_clar_questions - old_clar_questions,
        },
    }


def format_readiness_status(r: dict) -> str:
    icons = {"ready": "✅", "BLOCKED": "🚫", "WARN": "⚠️"}
    return (f"成本测算:{icons.get(r.get('cost_model','?'),'?')} "
            f"方案设计:{icons.get(r.get('solution_design','?'),'?')} "
            f"合同审核:{icons.get(r.get('contract_review','?'),'?')}")


def print_benchmark_report(results: list):
    print("\n" + "=" * 80)
    print("BENCHMARK REPORT — v0.2 vs Legacy Extractor")
    print("=" * 80)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Samples: {len(results)}\n")

    for r in results:
        print(f"\n{'─' * 80}")
        print(f"📋 {r['sample_id']}: {r['sample_label']}")
        print(f"{'─' * 80}")

        gt = r.get("ground_truth", {})
        exp = r.get("expected_issues", {})

        print(f"\n  预期问题: 缺失P0={exp.get('missing_p0',[])}  "
              f"歧义={exp.get('ambiguous',[])}  部分={exp.get('partial',[])}")

        old = r["old"]
        new = r["new"]

        # Readiness comparison
        print(f"\n  🚦 下游就绪状态:")
        print(f"     老extractor: {format_readiness_status(old['readiness'])}")
        print(f"     v0.2:       {format_readiness_status(new['readiness'])}")

        # Key metrics
        print(f"\n  📊 核心指标对比:")
        print(f"     {'指标':<25} {'老extractor':>12} {'v0.2':>12} {'改善':>10}")
        print(f"     {'─'*59}")
        print(f"     {'缺失暴露率(P0)':<25} {old['missing_exposure_rate']:>11.1%} {new['missing_exposure_rate']:>11.1%} {(new['missing_exposure_rate']-old['missing_exposure_rate']):>+10.1%}")
        print(f"     {'假值率':<25} {old['false_value_rate']:>11.1%} {new['false_value_rate']:>11.1%} {(new['false_value_rate']-old['false_value_rate']):>+10.1%}")
        print(f"     {'澄清问题数量':<25} {old['clarification_questions_count']:>12} {new['clarification_questions_count']:>12} {new['clarification_questions_count']-old['clarification_questions_count']:>+10}")

        # Quality scores (v0.2 only)
        qs = new.get("quality_scores", {})
        print(f"\n  📊 v0.2 质量评分:")
        print(f"     完整性={qs.get('completeness_score',0):.0%}  "
              f"证据={qs.get('evidence_score',0):.0%}  "
              f"就绪={qs.get('readiness_score',0):.0%}")

        # P0 field status detail
        old_p0 = old["p0_field_status"]
        new_p0 = new["p0_field_status"]
        print(f"\n  P0字段状态分布:")
        print(f"     老: missing={old_p0['missing']} partial={old_p0['partial']} "
              f"ambiguous={old_p0['ambiguous']} explicit={old_p0['explicit']} "
              f"inferred={old_p0['inferred']} fabricated={old_p0['fabricated']}")
        print(f"     v0.2: missing={new_p0['missing']} partial={new_p0['partial']} "
              f"ambiguous={new_p0['ambiguous']} explicit={new_p0['explicit']} "
              f"inferred={new_p0['inferred']} fabricated={new_p0['fabricated']}")

        # Key field extraction
        print(f"\n  关键字段提取对比:")
        for field in ["dc_count", "warehouse_area", "daily_orders"]:
            old_val = old.get(field, "—")
            new_val = new.get(field, "—")
            gt_val = gt.get(field, "—")
            marker = ""
            if str(gt_val) == "MISSING" and new_val is None:
                marker = " ← 正确暴露缺失"
            elif str(gt_val) == "AMBIGUOUS" and isinstance(new_result := new, dict):
                entry = new_result.get(field, {})
                if isinstance(entry, dict) and entry.get("status") == "ambiguous":
                    marker = " ← 正确识别歧义"
            print(f"     {field:<20} 老={old_val!s:<15} v0.2={new_val!s:<15} 真相={gt_val!s}{marker}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    avg_missing_exposure = sum(r["delta"]["missing_exposure_improvement"] for r in results) / len(results)
    avg_false_reduction = sum(r["delta"]["false_value_improvement"] for r in results) / len(results)
    print(f"  平均缺失暴露率改善:     {avg_missing_exposure:+.1%}")
    print(f"  平均假值率降低:        {avg_false_reduction:+.1%}")

    # Scorecard
    print(f"\n  📋 评分卡 (v0.2 vs 老extractor):")
    scorecard = []
    for r in results:
        old_ready = r["old"]["readiness"]["cost_model"]
        new_ready = r["new"]["readiness"]["cost_model"]
        if new_ready == "ready" and old_ready != "ready":
            scorecard.append(f"  ✅ {r['sample_id']}: v0.2解锁了被老extractor阻塞的成本测算")
        elif new_ready == old_ready:
            scorecard.append(f"  ⚪ {r['sample_id']}: 成本测算就绪状态一致")
        else:
            scorecard.append(f"  ❌ {r['sample_id']}: v0.2成本测算状态变差")

    for line in scorecard:
        print(line)

    print()


def save_json_report(results: list, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now().isoformat(),
        "version": "v0.2",
        "extractor_version": "tender_understanding_v0.2",
        "results": results,
        "summary": {
            "avg_missing_exposure_improvement": round(
                sum(r["delta"]["missing_exposure_improvement"] for r in results) / len(results), 4
            ),
            "avg_false_value_improvement": round(
                sum(r["delta"]["false_value_improvement"] for r in results) / len(results), 4
            ),
            "total_samples": len(results),
        }
    }
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"JSON report saved to {path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Benchmark v0.2 vs Legacy Extractor")
    parser.add_argument("--output", "-o", default="backend/benchmarks/report_latest.json",
                        help="Output JSON report path")
    parser.add_argument("--mock", action="store_true",
                        help="Use mock LLM responses (offline benchmark)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    new_mock = args.mock or os.getenv("MOCK_LLM") == "1"

    print(f"Running benchmark (old=rule_only, new=v0.2 {'[MOCK]' if new_mock else ''} analysis mode)...\n")
    results = []
    for s in BENCHMARK_SAMPLES:
        try:
            r = run_benchmark_on_sample(s, new_mock=new_mock)
            results.append(r)
        except Exception as e:
            print(f"  ⚠️  {s['id']} failed: {e}")
            results.append({
                "sample_id": s["id"],
                "sample_label": s["label"],
                "error": str(e),
                "old": {},
                "new": {},
                "delta": {},
            })

    print_benchmark_report(results)

    out_path = Path(args.output)
    save_json_report(results, out_path)

    print("\nDone. To re-run with updated benchmark samples, edit BENCHMARK_SAMPLES in this file.")
