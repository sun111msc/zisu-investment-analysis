"""反向 DCF 与估值模块测试。

重点验证两件事：
1. 反解结果代回正算必须自洽（数学正确性）；
2. 边界情形必须返回「未收敛」而不是伪解（工程正确性）。
"""

from __future__ import annotations

import pytest

from zisu.valuation import (
    MIN_SPREAD,
    DCFInput,
    PeerMetrics,
    enterprise_value,
    equity_value,
    peer_valuation,
    percentile_of,
    solve_implied_g,
    solve_implied_wacc,
)

FCFF = (10.69, 13.06, 15.55, 18.13, 20.77)


# ---------------------------------------------------------------- 正向 DCF


def test_enterprise_value_positive():
    ev, pv_exp, pv_term = enterprise_value(FCFF, 0.10, 0.03)
    assert ev == pytest.approx(pv_exp + pv_term)
    assert pv_exp > 0 and pv_term > 0


def test_wacc_below_growth_rejected():
    with pytest.raises(ValueError):
        enterprise_value(FCFF, 0.02, 0.03)


def test_equity_bridge():
    res = equity_value(
        DCFInput(fcff_forecast=FCFF, wacc=0.10, terminal_g=0.03, net_debt=20.0, shares_outstanding=7.0)
    )
    assert res.equity_value == pytest.approx(res.enterprise_value - 20.0)
    assert res.per_share == pytest.approx(res.equity_value / 7.0)


def test_terminal_share_reported():
    res = equity_value(DCFInput(fcff_forecast=FCFF, wacc=0.10, terminal_g=0.03))
    assert 0 < res.terminal_share < 1
    assert res.valid


def test_low_spread_marked_invalid():
    """利差过低时永续模型数值不稳定，必须标记为无效而不是输出巨大数字。"""
    res = equity_value(DCFInput(fcff_forecast=FCFF, wacc=0.032, terminal_g=0.03))
    assert not res.valid
    assert "稳健阈值" in res.note


# ---------------------------------------------------------------- 反向 DCF


def test_reverse_dcf_roundtrip_self_consistent():
    """反解出的 g 代回正算，误差必须小于千分之一。"""
    target_ev, _, _ = enterprise_value(FCFF, 0.10, 0.05)
    res = solve_implied_g(target_ev, FCFF, 0.10)
    assert res.converged, res.note
    assert res.implied_g == pytest.approx(0.05, abs=1e-4)

    check, _, _ = enterprise_value(FCFF, 0.10, res.implied_g or 0)
    assert abs(check - target_ev) / target_ev < 1e-3


def test_reverse_dcf_does_not_emit_price_target():
    """反向 DCF 的返回值里没有价格字段 —— 这是刻意的设计约束。"""
    res = solve_implied_g(200.0, FCFF, 0.10)
    payload = res.to_gate_payload()
    assert set(payload) == {"converged", "implied_g", "implied_wacc", "note"}
    assert not any("price" in k or "target" in k for k in payload)


def test_reverse_dcf_market_too_high_not_converged():
    """市值高于任何合理参数下的价值 → 未收敛，而不是给一个巨大的 g。"""
    res = solve_implied_g(100_000.0, FCFF, 0.10)
    assert not res.converged
    assert res.implied_g is None
    assert res.bounds_hit
    assert "反身性" in res.note or "无法解释" in res.note


def test_reverse_dcf_market_too_low_not_converged():
    res = solve_implied_g(10.0, FCFF, 0.10)
    assert not res.converged
    assert res.bounds_hit


def test_reverse_dcf_invalid_inputs():
    with pytest.raises(ValueError):
        solve_implied_g(100.0, (), 0.10)
    with pytest.raises(ValueError):
        solve_implied_g(-5.0, FCFF, 0.10)


def test_reverse_dcf_wacc_bounds():
    """WACC 过低时搜索区间为空，必须拒绝而不是除以负数。"""
    res = solve_implied_g(200.0, FCFF, 0.01)
    assert not res.converged


# ---------------------------------------------------------------- WACC 反解


def test_implied_wacc_roundtrip():
    target_ev, _, _ = enterprise_value(FCFF, 0.12, 0.03)
    res = solve_implied_wacc(target_ev, FCFF, 0.03)
    assert res.converged, res.note
    assert res.implied_wacc == pytest.approx(0.12, abs=1e-3)


def test_implied_wacc_monotonic_direction():
    """WACC 越高价值越低，反解方向必须与之相反。"""
    low = solve_implied_wacc(400.0, FCFF, 0.03)
    high = solve_implied_wacc(150.0, FCFF, 0.03)
    if low.converged and high.converged:
        assert (low.implied_wacc or 0) < (high.implied_wacc or 0)


# ---------------------------------------------------------------- 可比估值


def test_peer_valuation_percentile():
    peers = [PeerMetrics(name=f"P{i}", pe=v) for i, v in enumerate([10, 15, 20, 25, 30])]
    target = PeerMetrics(name="T", pe=28.0, is_target=True)
    res = peer_valuation(target, peers, "pe")
    assert res.peer_count == 5
    assert res.peer_median == pytest.approx(20.0)
    assert res.percentile == pytest.approx(0.8)
    assert res.premium_to_median == pytest.approx(0.4, abs=0.01)
    assert "偏高" in res.note


def test_peer_valuation_target_excluded_from_population():
    peers = [
        PeerMetrics(name="P1", pe=10.0),
        PeerMetrics(name="P2", pe=20.0),
        PeerMetrics(name="P3", pe=30.0),
        PeerMetrics(name="T", pe=999.0, is_target=True),
    ]
    res = peer_valuation(PeerMetrics(name="T", pe=999.0, is_target=True), peers, "pe")
    assert res.peer_count == 3


def test_peer_valuation_insufficient_sample_warns():
    peers = [PeerMetrics(name="P1", pe=10.0)]
    res = peer_valuation(PeerMetrics(name="T", pe=12.0, is_target=True), peers, "pe")
    assert res.warnings


def test_peer_valuation_negative_target():
    peers = [PeerMetrics(name=f"P{i}", pe=v) for i, v in enumerate([10, 15, 20, 25])]
    res = peer_valuation(PeerMetrics(name="T", pe=-5.0, is_target=True), peers, "pe")
    assert res.target_value is None
    assert any("不适用" in w for w in res.warnings)


def test_percentile_of():
    assert percentile_of(20, [10, 20, 30, 40]) == pytest.approx(0.5)
    assert percentile_of(100, [10, 20]) == pytest.approx(1.0)


def test_min_spread_constant():
    assert MIN_SPREAD > 0
