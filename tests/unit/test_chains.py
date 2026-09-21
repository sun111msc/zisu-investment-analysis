"""产业链瓶颈分级与仓位映射测试。"""

from __future__ import annotations

import pytest

from zisu.chains import (
    BomLayer,
    BottleneckGrade,
    EnvironmentGrade,
    GovernanceGrade,
    assess_bottleneck,
    position_cap,
    rank_bottlenecks,
)


def layer(**over) -> BomLayer:
    base = dict(
        level=1,
        name="工序A",
        process="精密涂布",
        unit_value=10.0,
        unit="元/m2",
        global_suppliers=3,
        certification_years=1.0,
    )
    base.update(over)
    return BomLayer(**base)


# ---------------------------------------------------------------- 层级定义


def test_layer_rejects_empty_process():
    """不允许停留在行业口号层 —— 必须描述具体工序。"""
    with pytest.raises(ValueError):
        layer(process="   ")


def test_layer_rejects_bad_level():
    with pytest.raises(ValueError):
        layer(level=0)


# ---------------------------------------------------------------- 分级


@pytest.mark.parametrize(
    "suppliers,cert,expected",
    [
        (1, 2.5, BottleneckGrade.L5_ULTIMATE),
        (2, 2.5, BottleneckGrade.L4_EXTREME),
        (2, 0.5, BottleneckGrade.L3_STRONG),
        (3, 0.0, BottleneckGrade.L3_STRONG),
        (4, 0.0, BottleneckGrade.L2_QUASI),
        (6, 0.0, BottleneckGrade.L1_POTENTIAL),
        (20, 0.0, BottleneckGrade.L0_NONE),
    ],
)
def test_grade_by_supplier_count(suppliers, cert, expected):
    res = assess_bottleneck(layer(global_suppliers=suppliers, certification_years=cert))
    assert res.grade is expected


def test_single_supplier_without_cert_is_not_ultimate():
    """独家但无认证壁垒，降级为 L4 —— 判据必须可证伪。"""
    res = assess_bottleneck(layer(global_suppliers=1, certification_years=0.5))
    assert res.grade is BottleneckGrade.L4_EXTREME


def test_zero_suppliers_rejected():
    with pytest.raises(ValueError):
        assess_bottleneck(layer(global_suppliers=0))


def test_grade_leaves():
    assert BottleneckGrade.L5_ULTIMATE.leaves == 5
    assert BottleneckGrade.L0_NONE.leaves == 0
    assert BottleneckGrade.L5_ULTIMATE.label == "🍃🍃🍃🍃🍃"
    assert BottleneckGrade.L0_NONE.label == "—"


# ---------------------------------------------------------------- 降级触发


def test_downgrade_trigger():
    from zisu.chains import DOWNGRADE_TRIGGERS

    res = assess_bottleneck(
        layer(global_suppliers=1, certification_years=2.5),
        triggers_hit=[DOWNGRADE_TRIGGERS[0]],
    )
    assert res.grade is BottleneckGrade.L4_EXTREME
    assert res.downgraded


def test_unknown_trigger_ignored():
    res = assess_bottleneck(layer(global_suppliers=1, certification_years=2.5), triggers_hit=["随便写的"])
    assert res.grade is BottleneckGrade.L5_ULTIMATE


def test_l0_cannot_downgrade_further():
    from zisu.chains import DOWNGRADE_TRIGGERS

    res = assess_bottleneck(layer(global_suppliers=30), triggers_hit=[DOWNGRADE_TRIGGERS[0]])
    assert res.grade is BottleneckGrade.L0_NONE


# ---------------------------------------------------------------- 仓位映射


def test_position_cap_table():
    assert position_cap(BottleneckGrade.L5_ULTIMATE, GovernanceGrade.A, EnvironmentGrade.B_NEUTRAL) == pytest.approx(0.25)
    assert position_cap(BottleneckGrade.L3_STRONG, GovernanceGrade.B, EnvironmentGrade.A_OFFENSIVE) == pytest.approx(0.10)
    assert position_cap(BottleneckGrade.L0_NONE, GovernanceGrade.A, EnvironmentGrade.A_OFFENSIVE) == pytest.approx(0.02)


def test_position_cap_never_exceeds_environment_ceiling():
    """环境评级决定总仓位天花板，单标的不得超过它。"""
    cap = position_cap(BottleneckGrade.L5_ULTIMATE, GovernanceGrade.A, EnvironmentGrade.C_CAUTIOUS)
    assert cap <= EnvironmentGrade.C_CAUTIOUS.total_cap
    # 瓶颈上限 25% 低于环境上限 30%，故取瓶颈值
    assert cap == pytest.approx(0.25)


def test_position_cap_zero_in_defensive_env():
    cap = position_cap(BottleneckGrade.L5_ULTIMATE, GovernanceGrade.A, EnvironmentGrade.D_DEFENSIVE)
    assert cap == pytest.approx(0.10)


def test_governance_d_never_investable():
    for grade in BottleneckGrade:
        assert position_cap(grade, GovernanceGrade.D, EnvironmentGrade.A_OFFENSIVE) == 0.0


def test_environment_flags():
    assert EnvironmentGrade.A_OFFENSIVE.allow_new
    assert EnvironmentGrade.C_CAUTIOUS.allow_new
    assert not EnvironmentGrade.D_DEFENSIVE.allow_new
    assert EnvironmentGrade.D_DEFENSIVE.total_cap == pytest.approx(0.10)


# ---------------------------------------------------------------- 排序


def test_rank_bottlenecks_by_grade_then_value():
    a = layer(name="窄瓶颈", global_suppliers=1, certification_years=3.0, unit_value=10.0)
    b = layer(name="宽瓶颈", global_suppliers=20, unit_value=100.0)
    ranking = rank_bottlenecks([b, a])
    assert ranking[0].layer_name == "窄瓶颈"


def test_rank_same_grade_by_unit_value():
    a = layer(name="低价值", global_suppliers=2, certification_years=3.0, unit_value=5.0)
    b = layer(name="高价值", global_suppliers=2, certification_years=3.0, unit_value=90.0)
    ranking = rank_bottlenecks([a, b])
    assert ranking[0].layer_name == "高价值"
