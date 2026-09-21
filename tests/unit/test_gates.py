"""闸门引擎与规则测试。"""

from __future__ import annotations

from datetime import date

import pytest

from zisu.contracts import TypedValue, Unit
from zisu.datasources import CapabilityManifest, build_registry
from zisu.gates import (
    ALL_RULES,
    GateContext,
    GateEngine,
    GateStage,
    GateStatus,
    build_engine,
    fail,
    ok,
)

TODAY = date.today()


def val(semantic: str, value: float, unit: Unit = Unit.CNY, source: str = "market.quote.primary"):
    return TypedValue(
        value=value,
        unit=unit,
        semantic=semantic,
        as_of=TODAY,
        source=source,
        currency="CNY" if unit is Unit.CNY else None,
    )


def ctx_with(arts: dict) -> GateContext:
    """artifacts 的键含点号（如 ``phase0.one_liner``），故用字典显式传入。"""
    return GateContext(symbol="T.SZ", values={}, artifacts=arts)


# ---------------------------------------------------------------- 引擎本身


def test_gate_ids_unique():
    ids = [r[0] for r in ALL_RULES]
    assert len(ids) == len(set(ids)), "闸门编号必须唯一"


def test_gate_count_matches_documentation():
    """文档声称 25 道，代码必须一致 —— 防止文档漂移。"""
    assert len(ALL_RULES) == 25


def test_engine_rejects_duplicate_registration():
    e = GateEngine()
    e.register("G1", "a", GateStage.DATA, lambda c: ok())
    with pytest.raises(ValueError):
        e.register("G1", "b", GateStage.DATA, lambda c: ok())


def test_rule_exception_becomes_blocking_failure():
    """规则自身出错必须按阻断处理，绝不静默放行。"""

    def boom(_):
        raise RuntimeError("规则内部错误")

    e = GateEngine()
    e.register("GX", "炸弹", GateStage.DATA, boom)
    report = e.run(GateContext(symbol="T.SZ"))
    assert report.results[0].status is GateStatus.FAIL
    assert report.results[0].blocking


def test_skip_not_counted_in_denominator():
    from zisu.gates.engine import GateSkipped

    def needs(_):
        raise GateSkipped("前提不足")

    e = GateEngine()
    e.register("GS", "跳过", GateStage.DATA, needs)
    e.register("GP", "通过", GateStage.DATA, lambda c: ok())
    report = e.run(GateContext(symbol="T.SZ"))
    assert report.summary()["SKIP"] == 1
    assert report.pass_rate() == 1.0


def test_report_to_declaration_mapping():
    e = GateEngine()
    e.register("GB", "阻断", GateStage.DATA, lambda c: fail("坏了"), blocking=True)
    e.register("GW", "提示", GateStage.DATA, lambda c: fail("小问题"), blocking=False)
    report = e.run(GateContext(symbol="T.SZ"))
    d = report.to_declaration()
    assert d.state.value == "BLOCKED"
    assert len(d.blockers) == 1
    assert len(d.warnings) == 1


# ---------------------------------------------------------------- GATE-01


def test_gate01_missing_manifest_blocks():
    e = build_engine()
    report = e.run(GateContext(symbol="T.SZ"), only=["GATE-01"])
    assert report.results[0].status is GateStatus.FAIL


def test_gate01_unregistered_source_blocks():
    e = build_engine()
    m = CapabilityManifest(symbol="T.SZ")
    m.declare("unknown.source", {"price"})
    ctx = GateContext(symbol="T.SZ", manifest=m, registry=build_registry())
    report = e.run(ctx, only=["GATE-01"])
    assert report.results[0].status is GateStatus.FAIL
    assert "R001" in report.results[0].detail


def test_gate01_compliant_passes():
    e = build_engine()
    m = CapabilityManifest(symbol="T.SZ")
    m.declare("market.quote.primary", {"price"})
    ctx = GateContext(symbol="T.SZ", manifest=m, registry=build_registry())
    report = e.run(ctx, only=["GATE-01"])
    assert report.results[0].status is GateStatus.PASS


# ---------------------------------------------------------------- GATE-02


def test_gate02_missing_currency_fails():
    e = build_engine()
    bad = TypedValue(
        value=1.0, unit=Unit.CNY, semantic="revenue", as_of=TODAY, source="s", currency=None
    )
    report = e.run(GateContext(symbol="T.SZ", values={"revenue": bad}), only=["GATE-02"])
    assert report.results[0].status is GateStatus.FAIL
    assert "C004" in report.results[0].detail


def test_gate02_clean_passes():
    e = build_engine()
    report = e.run(
        GateContext(symbol="T.SZ", values={"revenue": val("revenue", 100.0)}), only=["GATE-02"]
    )
    assert report.results[0].status is GateStatus.PASS


def test_gate02_empty_values_fails():
    e = build_engine()
    report = e.run(GateContext(symbol="T.SZ", values={}), only=["GATE-02"])
    assert report.results[0].status is GateStatus.FAIL


# ---------------------------------------------------------------- GATE-11 / 21


def test_gate11_requires_two_lines():
    e = build_engine()
    ctx = ctx_with({"phase0.business_lines": [{"name": "A", "revenue_share": 1.0}]})
    ctx.values = {"gross_margin": val("gross_margin", 30.0, Unit.PERCENT)}
    report = e.run(ctx, only=["GATE-11"])
    assert report.results[0].status is GateStatus.FAIL


def test_gate11_weighted_margin_mismatch_fails():
    e = build_engine()
    lines = [
        {"name": "A", "revenue_share": 0.6, "gross_margin": 45.0},
        {"name": "B", "revenue_share": 0.4, "gross_margin": 25.0},
    ]
    ctx = ctx_with({"phase0.business_lines": lines})
    ctx.values = {"gross_margin": val("gross_margin", 55.0, Unit.PERCENT)}
    report = e.run(ctx, only=["GATE-11"])
    assert report.results[0].status is GateStatus.FAIL
    assert "加权毛利率" in report.results[0].detail


def test_gate11_consistent_passes():
    e = build_engine()
    lines = [
        {"name": "A", "revenue_share": 0.6, "gross_margin": 45.0},
        {"name": "B", "revenue_share": 0.4, "gross_margin": 25.0},
    ]
    ctx = ctx_with({"phase0.business_lines": lines})
    ctx.values = {"gross_margin": val("gross_margin", 37.0, Unit.PERCENT)}
    report = e.run(ctx, only=["GATE-11"])
    assert report.results[0].status is GateStatus.PASS


def test_gate21_segment_sum_mismatch():
    e = build_engine()
    lines = [
        {"name": "A", "revenue": 30.0, "revenue_share": 0.5, "gross_margin": 30.0},
        {"name": "B", "revenue": 20.0, "revenue_share": 0.5, "gross_margin": 30.0},
    ]
    ctx = ctx_with({"phase0.business_lines": lines})
    ctx.values = {"revenue": val("revenue", 100.0)}
    report = e.run(ctx, only=["GATE-21"])
    assert report.results[0].status is GateStatus.FAIL


# ---------------------------------------------------------------- GATE-12/13/14


def test_gate12_rejects_industry_jargon():
    e = build_engine()
    layers = [
        {"name": f"L{i}", "process": "p", "unit_value": 1.0} for i in range(7)
    ]
    layers[3]["name"] = "上游材料行业"
    report = e.run(ctx_with({"phase2.bom_layers": layers}), only=["GATE-12"])
    assert report.results[0].status is GateStatus.FAIL
    assert "行业口号" in report.results[0].detail


def test_gate12_requires_unit_value():
    e = build_engine()
    layers = [{"name": f"L{i}", "process": "p", "unit_value": 1.0} for i in range(7)]
    layers[2]["unit_value"] = None
    report = e.run(ctx_with({"phase2.bom_layers": layers}), only=["GATE-12"])
    assert report.results[0].status is GateStatus.FAIL


def test_gate13_weak_reason_fails():
    e = build_engine()
    rows = [{"name": f"C{i}", "reason": "不行"} for i in range(5)]
    report = e.run(ctx_with({"phase2.excluded_competitors": rows}), only=["GATE-13"])
    assert report.results[0].status is GateStatus.FAIL


def test_gate14_missing_bridge_field():
    e = build_engine()
    bridge = {"equipment_units": 10, "asp": 5.0, "unit": "元"}
    report = e.run(ctx_with({"phase2.capacity_bridge": bridge}), only=["GATE-14"])
    assert report.results[0].status is GateStatus.FAIL


# ---------------------------------------------------------------- GATE-16


def test_gate16_weak_bear_fails():
    """空头写得太弱 = 自我确认，必须拦截。"""
    e = build_engine()
    ctx = ctx_with(
        {
            "phase4.bear_arguments": [{"claim": "贵", "evidence_grade": "L4"}],
            "phase4.bull_arguments": [
                {"claim": "a", "evidence_grade": "L1"},
                {"claim": "b", "evidence_grade": "L1"},
            ],
        }
    )
    report = e.run(ctx, only=["GATE-16"])
    assert report.results[0].status is GateStatus.FAIL
    assert "自我确认" in report.results[0].detail


# ---------------------------------------------------------------- GATE-41


def test_gate41_detects_zero_fill():
    e = build_engine()
    ctx = GateContext(
        symbol="T.SZ",
        values={
            "revenue": val("revenue", 100.0),
            "accounts_receivable": val("accounts_receivable", 0.0),
        },
    )
    report = e.run(ctx, only=["GATE-41"])
    assert report.results[0].status is GateStatus.FAIL
    assert "零填充" in report.results[0].detail


def test_gate41_allows_legitimate_zero():
    e = build_engine()
    ctx = GateContext(
        symbol="T.SZ",
        values={"net_income": val("net_income", 0.0), "revenue": val("revenue", 100.0)},
    )
    report = e.run(ctx, only=["GATE-41"])
    assert report.results[0].status is GateStatus.PASS


# ---------------------------------------------------------------- GATE-53/54


def test_gate53_stop_above_entry_fails():
    e = build_engine()
    ctx = ctx_with({"phase6.position": {"entry_price": 10.0, "stop_loss": 12.0}})
    report = e.run(ctx, only=["GATE-53"])
    assert report.results[0].status is GateStatus.FAIL


def test_gate53_excessive_risk_fails():
    e = build_engine()
    ctx = ctx_with({"phase6.position": {"entry_price": 10.0, "stop_loss": 6.0}})
    report = e.run(ctx, only=["GATE-53"])
    assert report.results[0].status is GateStatus.FAIL
    assert "1% 资金风险" in report.results[0].detail


def test_gate54_single_number_target_fails():
    e = build_engine()
    ctx = ctx_with({"phase0.exec_summary": {"target_range": 19.5}})
    report = e.run(ctx, only=["GATE-54"])
    assert report.results[0].status is GateStatus.FAIL


def test_gate54_range_passes():
    e = build_engine()
    ctx = ctx_with({"phase0.exec_summary": {"target_range": [32.0, 41.0]}})
    report = e.run(ctx, only=["GATE-54"])
    assert report.results[0].status is GateStatus.PASS


# ---------------------------------------------------------------- 阶段筛选


def test_stage_filtering():
    e = build_engine()
    report = e.run(GateContext(symbol="T.SZ", values={"revenue": val("revenue", 1.0)}),
                   stages=[GateStage.FORMAT])
    assert all(r.stage is GateStage.FORMAT for r in report.results)
    assert len(report.results) == 4
