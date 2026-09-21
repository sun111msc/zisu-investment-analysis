"""数据源层测试：登记门禁与降级链。"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from zisu.datasources import (
    CapabilityManifest,
    DataSourceSpec,
    FallbackChain,
    FetchOutcome,
    StaticDataSource,
    build_registry,
)

TODAY = date.today()


def primary(**records):
    return StaticDataSource(
        source_id="market.quote.primary",
        semantics=frozenset({"price", "pe_ttm", "market_cap"}),
        records=records,
    )


# ---------------------------------------------------------------- 登记门禁


def test_unregistered_source_blocked():
    """未登记的数据源一律禁止 —— 这是 fail-closed 的核心。"""
    reg = build_registry()
    m = CapabilityManifest(symbol="T.SZ")
    m.declare("some.unknown.search", {"pe_ttm"})
    issues = reg.verify_manifest(m)
    assert any(i.code == "R001" and i.blocking for i in issues)


def test_news_source_cannot_provide_valuation_semantics():
    """非结构化源无权提供估值语义 —— 把「网页搜不到 PE」变成代码约束。"""
    reg = build_registry()
    m = CapabilityManifest(symbol="T.SZ")
    m.declare("news.events", {"pe_ttm", "market_cap"})
    issues = reg.verify_manifest(m)
    codes = {i.code for i in issues}
    assert codes == {"R002"}
    assert len(issues) == 2
    assert all(i.blocking for i in issues)


def test_news_source_allowed_for_news_semantics():
    reg = build_registry()
    m = CapabilityManifest(symbol="T.SZ")
    m.declare("news.events", {"news_event", "policy_change"})
    assert reg.verify_manifest(m) == []


def test_compliant_manifest_passes():
    reg = build_registry()
    m = CapabilityManifest(symbol="T.SZ")
    m.declare("market.quote.primary", {"price", "pe_ttm"})
    m.declare("financials.statements.primary", {"revenue", "net_income"})
    assert reg.verify_manifest(m) == []


def test_coverage_check_reports_gap():
    reg = build_registry()
    m = CapabilityManifest(symbol="T.SZ")
    m.declare("market.quote.primary", {"price"})
    issues = reg.verify_semantic_coverage(m, {"price", "net_income"})
    assert len(issues) == 1
    assert issues[0].semantic == "net_income"


def test_duplicate_registration_rejected():
    reg = build_registry()
    spec = DataSourceSpec(
        source_id="market.quote.primary",
        kind="x",
        description="dup",
        allowed_semantics=frozenset({"price"}),
        priority=0,
    )
    with pytest.raises(ValueError):
        reg.register(spec)


# ---------------------------------------------------------------- 时效


def test_freshness_ok(registry):
    assert registry.check_freshness("market.quote.primary", TODAY) is None


def test_freshness_stale_warns_not_blocks(registry):
    old = TODAY - timedelta(days=30)
    issue = registry.check_freshness("market.quote.primary", old)
    assert issue is not None
    assert not issue.blocking
    assert issue.code == "R005"


# ---------------------------------------------------------------- 降级链


def test_bind_unregistered_source_rejected(registry):
    chain = FallbackChain(registry)
    with pytest.raises(ValueError):
        chain.bind(
            "not.registered",
            StaticDataSource(source_id="not.registered", semantics=frozenset()),
        )


def test_fallback_l0_to_l1(registry):
    """主源不可用时由备源接管，且审计日志留痕。"""
    l0 = StaticDataSource(
        source_id="market.quote.primary",
        semantics=frozenset({"price"}),
        healthy=False,
    )
    l1 = StaticDataSource(
        source_id="market.quote.backup",
        semantics=frozenset({"price"}),
        records={("price", "T.SZ"): (12.5, TODAY, "CNY")},
    )
    chain = FallbackChain(registry)
    chain.bind("market.quote.primary", l0).bind("market.quote.backup", l1)

    result = chain.fetch("price", "T.SZ")
    assert result.value.value == pytest.approx(12.5)
    assert result.served_by == "market.quote.backup"
    assert result.degraded
    outcomes = [a.outcome for a in result.audit]
    assert FetchOutcome.UNAVAILABLE in outcomes
    assert FetchOutcome.HIT in outcomes


def test_fallback_exhausted_returns_missing_not_zero(registry):
    """全链耗尽必须返回显式缺失 —— 这是与「用零填充」的分界线。"""
    l0 = StaticDataSource(
        source_id="market.quote.primary", semantics=frozenset({"price"}), healthy=False
    )
    l1 = StaticDataSource(
        source_id="market.quote.backup", semantics=frozenset({"price"}), healthy=False
    )
    chain = FallbackChain(registry)
    chain.bind("market.quote.primary", l0).bind("market.quote.backup", l1)

    result = chain.fetch("price", "T.SZ")
    assert result.value.is_missing
    assert result.value.value is None
    assert "降级链耗尽" in (result.value.missing_reason or "")


def test_fallback_source_error_continues(registry):
    broken = StaticDataSource(
        source_id="market.quote.primary",
        semantics=frozenset({"price"}),
        fail_on_fetch=True,
    )
    good = StaticDataSource(
        source_id="market.quote.backup",
        semantics=frozenset({"price"}),
        records={("price", "T.SZ"): (9.9, TODAY, "CNY")},
    )
    chain = FallbackChain(registry)
    chain.bind("market.quote.primary", broken).bind("market.quote.backup", good)

    result = chain.fetch("price", "T.SZ")
    assert result.value.value == pytest.approx(9.9)
    assert any(a.outcome is FetchOutcome.ERROR for a in result.audit)


def test_fallback_no_registered_source(registry):
    """没有任何已绑定源时，返回缺失且说明原因。"""
    chain = FallbackChain(registry)
    result = chain.fetch("price", "T.SZ")
    assert result.value.is_missing
    assert any(a.outcome is FetchOutcome.EXHAUSTED for a in result.audit)


def test_semantic_not_covered_returns_none(registry):
    adapter = primary()
    assert adapter.fetch("nonexistent_semantic", "T.SZ") is None


def test_audit_log_written(registry, tmp_path):
    path = tmp_path / "audit.jsonl"
    adapter = StaticDataSource(
        source_id="market.quote.primary",
        semantics=frozenset({"price"}),
        records={("price", "T.SZ"): (5.0, TODAY, "CNY")},
    )
    chain = FallbackChain(registry, audit_path=path)
    chain.bind("market.quote.primary", adapter)
    chain.fetch("price", "T.SZ")
    assert path.exists()
    assert "HIT" in path.read_text(encoding="utf-8")


def test_degradation_report_counts(registry):
    adapter = StaticDataSource(
        source_id="market.quote.primary",
        semantics=frozenset({"price"}),
        records={("price", "T.SZ"): (5.0, TODAY, "CNY")},
    )
    chain = FallbackChain(registry)
    chain.bind("market.quote.primary", adapter)
    chain.fetch("price", "T.SZ")
    report = chain.degradation_report()
    assert report.get("HIT") == 1
