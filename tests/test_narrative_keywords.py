"""
C层: Narrative 行业语义关键词快照测试
==========================================

Tests that build_narrative() output contains industry-appropriate language
and avoids inappropriate cross-industry terms.

Approach: keyword presence/absence assertions, NOT full-text snapshot.
Lightweight, stable, high signal.

完成标准：
  ✅ 每行业 ≥3 "应出现" 关键词断言
  ✅ 每行业 ≥1 "应避免" 关键词断言
  ✅ 覆盖 narrative 输出层
"""

import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.solution.base_solution_generator import generate_base_solution
from backend.solution.narrative_builder import build_narrative
from tests.fixtures.industry_cases import (
    AUTOMOTIVE, ELECTRONICS, FMCG, MANUFACTURING, GENERIC_3PL,
)


# ─── Helpers ──────────────────────────────────────────────────────────────

def narrative_for(state: dict) -> str:
    """Generate BaseSolution → build narrative text."""
    bs = generate_base_solution(project_state=state, project_id=state["project_name"])
    return build_narrative(bs)


def assert_any(keywords: list[str], text: str, label: str):
    """Assert at least one keyword from the list appears in text."""
    found = [kw for kw in keywords if kw in text]
    assert found, (
        f"[{label}] None of {keywords} found in narrative.\n"
        f"Text excerpt: {text[:300]!r}"
    )


def assert_none(keywords: list[str], text: str, label: str):
    """Assert none of the keywords appear in text."""
    found = [kw for kw in keywords if kw in text]
    assert not found, (
        f"[{label}] Unexpected keyword(s) {found} found in narrative.\n"
        f"Text excerpt: {text[:300]!r}"
    )


# ─── AUTOMOTIVE ──────────────────────────────────────────────────────────

class TestAutomotiveNarrative:
    """AUTOMOTIVE narrative must use automotive supply-chain language."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.text = narrative_for(AUTOMOTIVE)

    def test_has_line_side_term(self):
        """Must use '线边' or similar line-side language."""
        assert_any(["线边", "线边仓", "线边配送"], self.text, "line-side")

    def test_has_feed_or_jit_term(self):
        """Must reference JIT/JIS feeding or supply language."""
        assert_any(["供料", "JIT", "JIS", "节拍"], self.text, "JIT/JIS")

    def test_has_shortage_response_term(self):
        """Must mention shortage /缺料 response (key automotive risk)."""
        assert_any(["缺料", "停线", "器具"], self.text, "shortage/tooling")

    def test_avoids_vmi_hub(self):
        """Should NOT mention VMI Hub (electronics term)."""
        assert_none(["VMI Hub", "VMI Hub 运营模式"], self.text, "VMI (unexpected)")

    def test_avoids_fgcu_high_turnover_language(self):
        """Should NOT use FMCG 波次/门店补货 language."""
        assert_none(["高周转运营模式", "快消高周转", "门店补货"], self.text, "FMCG (unexpected)")


# ─── ELECTRONICS ─────────────────────────────────────────────────────────

class TestElectronicsNarrative:
    """ELECTRONICS narrative must reflect VMI / accuracy / traceability."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.text = narrative_for(ELECTRONICS)

    def test_has_vmi_term(self):
        """Must reference VMI or supplier-managed inventory."""
        assert_any(["VMI", "供应商管理库存", "VMI Hub"], self.text, "VMI")

    def test_has_accuracy_term(self):
        """Must mention inventory/stock accuracy."""
        assert_any(["准确率", "FIFO", "库存准确"], self.text, "accuracy")

    def test_has_traceability_term(self):
        """Must mention traceability or batch management."""
        assert_any(["追溯", "批次", "条码追溯"], self.text, "traceability")

    def test_avoids_line_side(self):
        """Should NOT mention line-side feeding (automotive term)."""
        assert_none(["线边配送", "线边仓", "产线配套"], self.text, "line-side (unexpected)")

    def test_avoids_store_replenishment(self):
        """Should NOT mention store/channel replenishment (FMCG term)."""
        assert_none(["门店补货", "渠道补货", "高周转运营模式"], self.text, "FMCG (unexpected)")


# ─── FMCG ────────────────────────────────────────────────────────────────

class TestFMCGNarrative:
    """FMCG narrative must reflect high-turnover / wave / fulfillment speed."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.text = narrative_for(FMCG)

    def test_has_throughput_term(self):
        """Must mention high turnover / wave拣选."""
        assert_any(["高周转", "波次", "快速周转"], self.text, "throughput")

    def test_has_replenishment_term(self):
        """Must mention replenishment / 补货."""
        assert_any(["补货", "渠道补货", "履约"], self.text, "replenishment")

    def test_has_fulfillment_term(self):
        """Must mention fulfillment / 履约时效."""
        assert_any(["履约", "时效", "峰值"], self.text, "fulfillment")

    def test_avoids_jis_sequencing(self):
        """Should NOT mention JIT/JIS or sequencing (automotive terms)."""
        assert_none(["JIS", "sequencing", "线边配送"], self.text, "automotive (unexpected)")

    def test_avoids_vmi_hub(self):
        """Should NOT mention VMI Hub (electronics term)."""
        assert_none(["VMI Hub", "供应商管理库存"], self.text, "VMI (unexpected)")


# ─── MANUFACTURING ───────────────────────────────────────────────────────

class TestManufacturingNarrative:
    """MANUFACTURING narrative must reflect WIP / batch / production rhythm."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.text = narrative_for(MANUFACTURING)

    def test_has_wip_or_raw_material_term(self):
        """Must mention WIP / raw material / semi-finished goods."""
        assert_any(["在制品", "原材料", "半成品", "WIP", "工单"], self.text, "WIP/materials")

    def test_has_production_rhythm_term(self):
        """Must mention production rhythm / supply节奏."""
        assert_any(["班次", "供给节奏", "产线", "生产节奏"], self.text, "production rhythm")

    def test_has_batch_traceability_term(self):
        """Must mention batch traceability (manufacturing key KPI)."""
        assert_any(["批次追溯", "批次管理", "配料"], self.text, "batch/batching")

    def test_avoids_vmi_hub(self):
        """Should NOT mention VMI Hub (electronics term)."""
        assert_none(["VMI Hub", "供应商管理库存"], self.text, "VMI (unexpected)")

    def test_avoids_store_delivery(self):
        """Should NOT mention store delivery / 门店配送 (FMCG term)."""
        assert_none(["门店配送", "渠道补货", "波次拣选"], self.text, "FMCG (unexpected)")


# ─── GENERIC_3PL ─────────────────────────────────────────────────────────

class TestGeneric3PLNarrative:
    """GENERIC_3PL narrative must be generic / neutral — no strong industry lock-in."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.text = narrative_for(GENERIC_3PL)

    def test_is_present_and_nonempty(self):
        """Narrative must exist and not be empty."""
        assert self.text and len(self.text) > 50, \
            f"Narrative too short or empty: {self.text[:100]!r}"

    def test_uses_generic_warehouse_language(self):
        """Must use generic warehouse language (not strongly bound to one industry)."""
        # At minimum should mention 仓储/仓配/标准仓
        assert_any(["仓储", "仓配", "标准仓", "运营"], self.text, "generic warehouse")

    def test_avoids_automotive_terms(self):
        """Should NOT be strongly automotive-coded."""
        assert_none(["线边配送", "JIT", "JIS", "停线事件"], self.text, "automotive")

    def test_avoids_vmi_hub(self):
        """Should NOT mention VMI Hub (electronics signature term)."""
        assert_none(["VMI Hub", "供应商管理库存"], self.text, "electronics VMI")

    def test_avoids_fgcu_terms(self):
        """Should NOT be strongly FMCG-coded."""
        assert_none(["高周转运营模式", "快消", "门店补货"], self.text, "FMCG")
