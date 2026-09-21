"""数据源适配器。

这个模块提供两类适配器：

- ``StaticDataSource`` —— 从内存记录读取的适配器。用于测试、示例与 CI，
  让整条链路可以在**不依赖任何外部服务**的情况下跑通。
- ``TextSourceAdapter`` —— 非结构化文本源适配器的占位实现。它演示了
  「新闻源无权提供估值语义」这条规则在代码层面如何自然成立。

接入你自己的真实数据源时，实现 ``DataSource`` 协议并在注册表登记即可，
本模块不需要改动。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from zisu.contracts import Frequency, TypedValue, Unit
from zisu.datasources.base import SourceError

__all__ = ["StaticDataSource", "TextSourceAdapter", "SEMANTIC_UNITS", "infer_unit"]


#: 语义 → 默认量纲。真实的适配器应当自己决定量纲，这里只是兜底。
SEMANTIC_UNITS: dict[str, Unit] = {
    "price": Unit.CNY,
    "market_cap": Unit.CNY,
    "revenue": Unit.CNY,
    "net_income": Unit.CNY,
    "operating_cash_flow": Unit.CNY,
    "capex": Unit.CNY,
    "total_assets": Unit.CNY,
    "total_liabilities": Unit.CNY,
    "total_equity": Unit.CNY,
    "current_assets": Unit.CNY,
    "current_liabilities": Unit.CNY,
    "long_term_debt": Unit.CNY,
    "retained_earnings": Unit.CNY,
    "ebit": Unit.CNY,
    "depreciation": Unit.CNY,
    "sga": Unit.CNY,
    "ppe": Unit.CNY,
    "revenue_prior": Unit.CNY,
    "net_income_prior": Unit.CNY,
    "total_assets_prior": Unit.CNY,
    "inventory": Unit.CNY,
    "accounts_receivable": Unit.CNY,
    "eps": Unit.CNY,
    "shares_outstanding": Unit.SHARES,
    "gross_margin": Unit.PERCENT,
    "roe": Unit.PERCENT,
    "pledge_ratio": Unit.PERCENT,
    "market_share": Unit.PERCENT,
    "pe_ttm": Unit.RATIO_TTM,
    "pe_forward": Unit.RATIO_TTM,
    "pb": Unit.RATIO_TTM,
    "ps": Unit.RATIO_TTM,
    "peg": Unit.RATIO,
    "capacity": Unit.COUNT,
    "shipment": Unit.COUNT,
}

#: 语义 → 默认频率
SEMANTIC_FREQUENCY: dict[str, Frequency] = {
    "revenue": Frequency.ANNUAL,
    "net_income": Frequency.ANNUAL,
    "operating_cash_flow": Frequency.ANNUAL,
    "capex": Frequency.ANNUAL,
    "total_assets": Frequency.ANNUAL,
    "total_liabilities": Frequency.ANNUAL,
    "inventory": Frequency.ANNUAL,
    "accounts_receivable": Frequency.ANNUAL,
    "eps": Frequency.TTM,
    "roe": Frequency.TTM,
    "pe_ttm": Frequency.TTM,
    "pb": Frequency.POINT,
}


def infer_unit(semantic: str) -> Unit:
    return SEMANTIC_UNITS.get(semantic, Unit.RATIO)


def infer_frequency(semantic: str) -> Frequency:
    return SEMANTIC_FREQUENCY.get(semantic, Frequency.POINT)


@dataclass
class StaticDataSource:
    """从内存记录读取的数据源。

    ``records`` 的键是 ``(semantic, symbol)``，值是 ``(数值, 时点, 可选币种)``。
    未登记的键返回 ``None``（不覆盖），而不是零值。
    """

    source_id: str
    semantics: frozenset[str]
    records: dict[tuple[str, str], tuple[float, date, str | None]] = field(default_factory=dict)
    healthy: bool = True
    fail_on_fetch: bool = False

    def supports(self, semantic: str) -> bool:
        return semantic in self.semantics

    def available(self) -> bool:
        return self.healthy

    def put(
        self,
        semantic: str,
        symbol: str,
        value: float,
        as_of: date,
        currency: str | None = None,
    ) -> StaticDataSource:
        self.records[(semantic, symbol)] = (value, as_of, currency)
        return self

    def fetch(
        self,
        semantic: str,
        symbol: str,
        *,
        as_of: date | None = None,
    ) -> TypedValue | None:
        if self.fail_on_fetch:
            raise SourceError(self.source_id, "模拟调用失败")

        rec = self.records.get((semantic, symbol))
        if rec is None:
            return None

        value, rec_as_of, currency = rec
        unit = infer_unit(semantic)
        if unit is Unit.CNY and currency is None:
            currency = "CNY"

        return TypedValue(
            value=value,
            unit=unit,
            semantic=semantic,
            as_of=rec_as_of,
            source=self.source_id,
            currency=currency,
            frequency=infer_frequency(semantic),
        )


@dataclass
class TextSourceAdapter:
    """非结构化文本源。

    它的语义白名单由注册表决定，而不是由自己决定 —— 即使它「知道」某个
    市盈率，注册表也不会为这个语义授权，因此降级链根本不会把它列为候选。
    """

    source_id: str
    semantics: frozenset[str]
    snippets: Mapping[str, str] = field(default_factory=dict)
    healthy: bool = True

    def supports(self, semantic: str) -> bool:
        return semantic in self.semantics

    def available(self) -> bool:
        return self.healthy

    def fetch(
        self,
        semantic: str,
        symbol: str,
        *,
        as_of: date | None = None,
    ) -> TypedValue | None:
        # 非结构化源不产出数值 —— 它只产出线索。
        return None

    def search(self, query: str) -> list[str]:
        return [v for k, v in self.snippets.items() if query in k]
