"""契约层测试。"""

from __future__ import annotations

from datetime import date

import pytest

from zisu.contracts import (
    Frequency,
    MissingValueError,
    OutputState,
    Severity,
    TypedValue,
    Unit,
    UnitMismatchError,
    build_declaration,
    resolve_state,
    sum_values,
)

AS_OF = date(2026, 6, 30)


def make(**kw):
    base = dict(
        value=100.0,
        unit=Unit.CNY,
        semantic="revenue",
        as_of=AS_OF,
        source="financials.statements.primary",
        currency="CNY",
    )
    base.update(kw)
    return TypedValue(**base)


# ---------------------------------------------------------------- 构造校验


def test_missing_requires_reason():
    """缺失必须说明原因 —— 不允许静默的 None。"""
    with pytest.raises(MissingValueError):
        TypedValue(
            value=None,
            unit=Unit.CNY,
            semantic="revenue",
            as_of=AS_OF,
            source="s",
            currency="CNY",
        )


def test_missing_factory_is_legal_state():
    v = TypedValue.missing(
        unit=Unit.CNY,
        semantic="revenue",
        as_of=AS_OF,
        source="unresolved",
        reason="降级链耗尽",
        currency="CNY",
    )
    assert v.is_missing
    assert "降级链耗尽" in v.render()


def test_value_and_reason_conflict():
    with pytest.raises(ValueError):
        make(value=1.0, missing_reason="不该同时存在")


# ---------------------------------------------------------------- 契约校验


def test_missing_currency_is_violation():
    v = make(currency=None)
    codes = [x.code for x in v.validate()]
    assert "C004" in codes
    assert not v.is_valid()


def test_percent_magnitude_warning():
    """89.8 vs 0.898 的混用是最常见的静默错误之一。"""
    v = make(value=1898.0, unit=Unit.PERCENT, semantic="gross_margin", currency=None)
    issues = v.validate()
    assert any(x.code == "C006" and x.severity is Severity.WARNING for x in issues)
    # 是警告而非阻断
    assert v.is_valid()


def test_share_ratio_out_of_range():
    v = make(value=1.8, unit=Unit.RATIO, semantic="revenue_share", currency=None)
    assert any(x.code == "C007" for x in v.validate())


def test_valid_value_passes():
    assert make().is_valid()


# ---------------------------------------------------------------- 算术


def test_unit_mismatch_raises():
    """量纲不同的两个数不能相加 —— 直接报错，不做隐式转换。"""
    a = make(value=100.0, unit=Unit.CNY)
    b = make(value=30.0, unit=Unit.PERCENT, semantic="gross_margin", currency=None)
    with pytest.raises(UnitMismatchError):
        a.add(b)


def test_currency_mismatch_raises():
    a = make(value=100.0, currency="CNY")
    b = make(value=50.0, currency="HKD")
    with pytest.raises(UnitMismatchError):
        a.add(b)


def test_add_same_unit():
    a = make(value=60.0, semantic="seg_a")
    b = make(value=40.0, semantic="seg_b")
    c = a.add(b)
    assert c.value == 100.0
    assert c.as_of == AS_OF


def test_missing_operand_rejected():
    a = make(value=10.0)
    b = TypedValue.missing(
        unit=Unit.CNY, semantic="x", as_of=AS_OF, source="s", reason="无数据", currency="CNY"
    )
    with pytest.raises(MissingValueError):
        a.add(b)


def test_over_yields_ratio():
    a = make(value=25.0, semantic="net_income")
    b = make(value=100.0, semantic="revenue")
    r = a.over(b)
    assert r.unit is Unit.RATIO
    assert r.value == pytest.approx(0.25)
    assert r.to_percent().value == pytest.approx(25.0)


def test_scale_and_fx():
    a = make(value=100.0)
    assert a.scale(1.5).value == pytest.approx(150.0)
    assert a.to_currency(1.08, "USD").currency == "USD"


# ---------------------------------------------------------------- 加总


def test_sum_values_normal():
    parts = [make(value=60.0, semantic="a"), make(value=40.0, semantic="b")]
    total = sum_values(parts, semantic="total_revenue")
    assert total.value == pytest.approx(100.0)
    assert total.semantic == "total_revenue"


def test_sum_with_missing_stays_missing():
    """任何一项缺失，整体即缺失 —— 不用「缺项按零计」制造假精确。"""
    parts = [
        make(value=60.0, semantic="a"),
        TypedValue.missing(
            unit=Unit.CNY, semantic="b", as_of=AS_OF, source="s", reason="未披露", currency="CNY"
        ),
    ]
    total = sum_values(parts)
    assert total.is_missing
    assert "b" in (total.missing_reason or "")


def test_sum_empty_rejected():
    with pytest.raises(ValueError):
        sum_values([])


# ---------------------------------------------------------------- 三态输出


def test_resolve_state_priority():
    assert resolve_state([], []) is OutputState.PASS
    assert resolve_state([], ["w"]) is OutputState.DRAFT_REVIEW
    assert resolve_state(["b"], ["w"]) is OutputState.BLOCKED


def test_blocked_cannot_emit_conclusion():
    d = build_declaration(blockers=["GATE-01 越权"], warnings=[], gate_summary={"FAIL": 1})
    assert d.state is OutputState.BLOCKED
    assert not d.can_emit_conclusion
    assert "BLOCKED" in d.to_markdown()


def test_draft_review_can_emit_with_banner():
    d = build_declaration(blockers=[], warnings=["数据超期"], gate_summary={"PASS": 3, "FAIL": 1})
    assert d.state is OutputState.DRAFT_REVIEW
    assert d.can_emit_conclusion
    assert "DRAFT_REVIEW" in d.to_markdown()


# ---------------------------------------------------------------- 序列化


def test_as_dict_roundtrip_fields():
    d = make().as_dict()
    assert set(d) == {
        "value",
        "unit",
        "currency",
        "frequency",
        "semantic",
        "as_of",
        "source",
        "missing_reason",
    }
    assert d["frequency"] == Frequency.POINT.value
    assert d["as_of"] == AS_OF.isoformat()


def test_frozen():
    from dataclasses import FrozenInstanceError

    v = make()
    with pytest.raises(FrozenInstanceError):
        v.value = 1.0  # type: ignore[misc]
