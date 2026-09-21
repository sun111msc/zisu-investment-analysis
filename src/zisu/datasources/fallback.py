"""多级降级链与取数审计。

降级链解决的问题：主源挂了怎么办？

朴素的做法是让模型自己重试或换个源 —— 这正是事故的来源，因为模型会
「顺手」换到一个口径不同的源，而报告里看不出来。

本模块的做法：把降级变成**确定的、可审计的流程**。

- 按注册表里的 ``priority`` 依次尝试（L0 → L1 → L2）；
- 每次尝试都写一条审计记录（成功 / 未覆盖 / 失败）；
- 全部失败时返回**显式缺失值**，而不是异常、更不是零值；
- 审计日志随报告一起归档，任何数值都能回溯到「哪一级源给的」。

设计取舍见 ``docs/engineering/adr/0003-fail-closed-registry.md``。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path

from zisu.contracts import Frequency, TypedValue, Unit
from zisu.datasources.base import DataSource, SourceError
from zisu.datasources.registry import DataSourceRegistry, DataSourceSpec

__all__ = ["FetchOutcome", "FetchAudit", "FallbackChain", "FetchResult"]


class FetchOutcome(str, Enum):
    HIT = "HIT"  # 命中并返回数值
    NOT_COVERED = "NOT_COVERED"  # 该源不覆盖此语义
    UNAVAILABLE = "UNAVAILABLE"  # 健康探针失败
    ERROR = "ERROR"  # 调用抛错
    STALE = "STALE"  # 命中但超过时效
    EXHAUSTED = "EXHAUSTED"  # 全链耗尽


@dataclass
class FetchAudit:
    semantic: str
    symbol: str
    source_id: str
    tier: str
    outcome: FetchOutcome
    detail: str = ""
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> str:
        d = asdict(self)
        d["outcome"] = self.outcome.value
        return json.dumps(d, ensure_ascii=False)


@dataclass
class FetchResult:
    """降级链的返回。``value.is_missing`` 为真时说明全链耗尽。"""

    value: TypedValue
    audit: list[FetchAudit] = field(default_factory=list)

    @property
    def served_by(self) -> str | None:
        for a in self.audit:
            if a.outcome is FetchOutcome.HIT:
                return a.source_id
        return None

    @property
    def degraded(self) -> bool:
        """是否走了备份源（即 L0 未命中）。"""
        for a in self.audit:
            if a.outcome is FetchOutcome.HIT:
                return a.tier != "L0"
        return False


_SEMANTIC_DEFAULT_UNIT: dict[str, Unit] = {
    "price": Unit.CNY,
    "market_cap": Unit.CNY,
    "revenue": Unit.CNY,
    "net_income": Unit.CNY,
    "operating_cash_flow": Unit.CNY,
    "capex": Unit.CNY,
    "total_assets": Unit.CNY,
    "total_liabilities": Unit.CNY,
    "inventory": Unit.CNY,
    "accounts_receivable": Unit.CNY,
    "eps": Unit.CNY,
    "gross_margin": Unit.PERCENT,
    "roe": Unit.PERCENT,
    "pledge_ratio": Unit.PERCENT,
    "pe_ttm": Unit.RATIO_TTM,
    "pe_forward": Unit.RATIO_TTM,
    "pb": Unit.RATIO_TTM,
    "ps": Unit.RATIO_TTM,
    "peg": Unit.RATIO,
    "capacity": Unit.COUNT,
    "shipment": Unit.COUNT,
}


class FallbackChain:
    """按优先级依次尝试数据源。"""

    def __init__(
        self,
        registry: DataSourceRegistry,
        adapters: dict[str, DataSource] | None = None,
        *,
        audit_path: str | Path | None = None,
    ) -> None:
        self.registry = registry
        self.adapters: dict[str, DataSource] = dict(adapters or {})
        self.audit_path = Path(audit_path) if audit_path else None
        self._audit: list[FetchAudit] = []

    # ---- 绑定 ----

    def bind(self, source_id: str, adapter: DataSource) -> FallbackChain:
        if not self.registry.is_registered(source_id):
            raise ValueError(
                f"不能绑定未登记的数据源 {source_id!r}。请先登记其能力边界。"
            )
        self.adapters[source_id] = adapter
        return self

    # ---- 主流程 ----

    def _candidates(self, semantic: str) -> list[DataSourceSpec]:
        """筛出有资格覆盖该语义的已登记源，按优先级排序。

        注意：筛选依据是注册表的授权，不是源的自我声明。
        """
        return [
            s
            for s in self.registry.all_specs()
            if s.covers(semantic) and s.source_id in self.adapters
        ]

    def fetch(
        self,
        semantic: str,
        symbol: str,
        *,
        as_of: date | None = None,
        required: bool = True,
    ) -> FetchResult:
        """沿降级链取数。永不抛错 —— 全败时返回显式缺失值。"""
        chain_audit: list[FetchAudit] = []
        candidates = self._candidates(semantic)

        if not candidates:
            note = FetchAudit(
                semantic=semantic,
                symbol=symbol,
                source_id="-",
                tier="-",
                outcome=FetchOutcome.EXHAUSTED,
                detail="没有任何已登记且已绑定的数据源可覆盖该语义",
            )
            chain_audit.append(note)
            self._record(note)
            return FetchResult(
                value=self._missing(semantic, symbol, "无可用的已登记数据源"), audit=chain_audit
            )

        for spec in candidates:
            adapter = self.adapters[spec.source_id]

            # 1) 健康探针
            try:
                healthy = adapter.available()
            except Exception as exc:  # noqa: BLE001 - 探针异常视为不可用
                healthy = False
                chain_audit.append(
                    FetchAudit(
                        semantic,
                        symbol,
                        spec.source_id,
                        spec.tier,
                        FetchOutcome.ERROR,
                        f"健康探针异常：{exc}",
                    )
                )

            if not healthy:
                a = FetchAudit(
                    semantic,
                    symbol,
                    spec.source_id,
                    spec.tier,
                    FetchOutcome.UNAVAILABLE,
                    "健康探针返回不可用",
                )
                chain_audit.append(a)
                self._record(a)
                continue

            # 2) 实际取数
            try:
                val = adapter.fetch(semantic, symbol, as_of=as_of)
            except SourceError as exc:
                a = FetchAudit(
                    semantic, symbol, spec.source_id, spec.tier, FetchOutcome.ERROR, exc.message
                )
                chain_audit.append(a)
                self._record(a)
                continue
            except Exception as exc:  # noqa: BLE001
                a = FetchAudit(
                    semantic, symbol, spec.source_id, spec.tier, FetchOutcome.ERROR, repr(exc)
                )
                chain_audit.append(a)
                self._record(a)
                continue

            if val is None:
                a = FetchAudit(
                    semantic,
                    symbol,
                    spec.source_id,
                    spec.tier,
                    FetchOutcome.NOT_COVERED,
                    "本源返回 None（不覆盖该语义）",
                )
                chain_audit.append(a)
                self._record(a)
                continue

            # 3) 时效校验
            stale = self.registry.check_freshness(spec.source_id, val.as_of)
            if stale is not None:
                a = FetchAudit(
                    semantic,
                    symbol,
                    spec.source_id,
                    spec.tier,
                    FetchOutcome.STALE,
                    stale.message,
                )
                chain_audit.append(a)
                self._record(a)
                # 超期不阻断取数，但审计留痕；时效问题由闸门层决定是否降级输出状态
                hit = FetchAudit(
                    semantic,
                    symbol,
                    spec.source_id,
                    spec.tier,
                    FetchOutcome.HIT,
                    f"命中但数据超期：{stale.message}",
                )
                chain_audit.append(hit)
                self._record(hit)
                return FetchResult(value=val, audit=chain_audit)

            hit = FetchAudit(
                semantic, symbol, spec.source_id, spec.tier, FetchOutcome.HIT, "命中"
            )
            chain_audit.append(hit)
            self._record(hit)
            return FetchResult(value=val, audit=chain_audit)

        # 全链耗尽
        detail = (
            f"降级链耗尽（尝试 {len(candidates)} 个源："
            f"{', '.join(c.source_id for c in candidates)}）"
        )
        exhausted = FetchAudit(
            semantic, symbol, "-", "-", FetchOutcome.EXHAUSTED, detail
        )
        chain_audit.append(exhausted)
        self._record(exhausted)
        return FetchResult(
            value=self._missing(semantic, symbol, detail),
            audit=chain_audit,
        )

    def fetch_many(
        self, semantics: Iterable[str], symbol: str, *, as_of: date | None = None
    ) -> dict[str, TypedValue]:
        return {
            sem: self.fetch(sem, symbol, as_of=as_of).value for sem in semantics
        }

    # ---- 内部 ----

    @staticmethod
    def _missing(semantic: str, symbol: str, reason: str) -> TypedValue:
        return TypedValue.missing(
            unit=_SEMANTIC_DEFAULT_UNIT.get(semantic, Unit.RATIO),
            semantic=semantic,
            as_of=date.today(),
            source="unresolved",
            reason=f"{symbol}: {reason}",
            frequency=Frequency.POINT,
        )

    def _record(self, a: FetchAudit) -> None:
        self._audit.append(a)
        if self.audit_path:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8") as fh:
                fh.write(a.to_json() + "\n")

    def audit_log(self) -> list[FetchAudit]:
        return list(self._audit)

    def degradation_report(self) -> dict[str, int]:
        """各类结局计数，用于 CI 里做降级率回归。"""
        out: dict[str, int] = {}
        for a in self._audit:
            out[a.outcome.value] = out.get(a.outcome.value, 0) + 1
        return out
