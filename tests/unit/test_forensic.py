"""法务会计模型测试。"""

from __future__ import annotations

import pytest

from zisu.forensic import (
    FinancialSnapshot,
    altman_z_score,
    beneish_m_score,
    piotroski_f_score,
    run_all,
    sloan_accrual_ratio,
)


def snap(**over) -> FinancialSnapshot:
    base = dict(
        year=2026,
        revenue=1000.0,
        cogs=700.0,
        net_income=120.0,
        cfo=140.0,
        total_assets=1000.0,
        current_assets=500.0,
        current_liabilities=250.0,
        long_term_debt=180.0,
        total_liabilities=450.0,
        total_equity=550.0,
        retained_earnings=200.0,
        ebit=150.0,
        depreciation=50.0,
        sga=120.0,
        receivables=150.0,
        ppe=350.0,
        market_value_equity=1200.0,
        shares_outstanding=40.0,
    )
    base.update(over)
    return FinancialSnapshot(**base)


# ---------------------------------------------------------------- 派生属性


def test_derived_metrics():
    s = snap()
    assert s.gross_profit == pytest.approx(300.0)
    assert s.gross_margin == pytest.approx(0.3)
    assert s.working_capital == pytest.approx(250.0)
    assert s.roa == pytest.approx(0.12)
    assert s.asset_turnover == pytest.approx(1.0)
    assert s.leverage == pytest.approx(0.45)


# ---------------------------------------------------------------- Beneish


def test_beneish_requires_denominators():
    """分母为零时不给分 —— 不用 0 冒充计算结果。"""
    res = beneish_m_score(snap(revenue=1000.0), snap(revenue=1000.0, total_assets=1000.0))
    # 正常应能算出分数
    assert res.score is not None


def test_beneish_zero_revenue_returns_none():
    res = beneish_m_score(snap(), snap(revenue=0.0))
    assert res.score is None
    assert "无法计算" in res.verdict


def test_beneish_growth_caveat_triggered():
    """高成长公司在本模型中天然得分偏高，必须给出误报提示。"""
    cur = snap(revenue=1500.0)
    prior = snap(revenue=1000.0)
    res = beneish_m_score(cur, prior)
    assert any("SGI" in c for c in res.caveats)


def test_beneish_components_present():
    res = beneish_m_score(snap(), snap())
    assert set(res.components) == {"DSRI", "GMI", "AQI", "SGI", "DEPI", "SGAI", "TATA", "LVGI"}


# ---------------------------------------------------------------- Piotroski


def test_piotroski_range():
    res = piotroski_f_score(snap(), snap())
    assert res.score is not None
    assert 0 <= res.score <= 9


def test_piotroski_improving_beats_deteriorating():
    improving = piotroski_f_score(
        snap(net_income=150.0, cfo=180.0, revenue=1200.0),
        snap(net_income=100.0, cfo=90.0, revenue=1000.0),
    )
    deteriorating = piotroski_f_score(
        snap(net_income=50.0, cfo=20.0, revenue=900.0, total_assets=1100.0),
        snap(net_income=120.0, cfo=140.0, revenue=1000.0, total_assets=1000.0),
    )
    assert (improving.score or 0) > (deteriorating.score or 0)


def test_piotroski_dilution_signal():
    res = piotroski_f_score(snap(shares_outstanding=50.0), snap(shares_outstanding=40.0))
    assert res.components["signals"]["7_no_dilution"] is False


def test_piotroski_missing_shares_caveat():
    res = piotroski_f_score(snap(shares_outstanding=None), snap(shares_outstanding=None))
    assert res.components["signals"]["7_no_dilution"] is None
    assert any("股本" in c for c in res.caveats)


# ---------------------------------------------------------------- Altman


def test_altman_listed_uses_market_value():
    res = altman_z_score(snap(), listed=True)
    assert "上市公司版" in res.model
    assert res.score is not None
    assert res.score > 2.99  # 低杠杆高分


def test_altman_unlisted_switches_version():
    res = altman_z_score(snap(market_value_equity=None), listed=True)
    assert "Z''" in res.model
    assert any("切换" in c for c in res.caveats)


def test_altman_distress_zone():
    stressed = snap(
        ebit=-50.0,
        retained_earnings=-200.0,
        total_liabilities=1200.0,
        total_equity=-200.0,
        market_value_equity=50.0,
        revenue=300.0,
    )
    res = altman_z_score(stressed, listed=True)
    assert res.score is not None
    assert "困境区" in res.verdict


def test_altman_zero_assets_returns_none():
    res = altman_z_score(snap(total_assets=0.0), listed=True)
    assert res.score is None


# ---------------------------------------------------------------- Sloan


def test_sloan_high_accrual_flagged():
    res = sloan_accrual_ratio(snap(net_income=200.0, cfo=50.0))
    assert res.score is not None
    assert res.score == pytest.approx(0.15)
    assert "偏低" in res.verdict


def test_sloan_negative_accrual():
    res = sloan_accrual_ratio(snap(net_income=100.0, cfo=150.0))
    assert res.score is not None
    assert res.score < 0
    assert "优于账面利润" in res.verdict


def test_sloan_zero_assets():
    assert sloan_accrual_ratio(snap(total_assets=0.0)).score is None


# ---------------------------------------------------------------- run_all


def test_run_all_with_prior():
    res = run_all(snap(), snap())
    assert set(res) == {"beneish", "piotroski", "altman", "sloan"}


def test_run_all_without_prior():
    res = run_all(snap())
    assert set(res) == {"altman", "sloan"}
