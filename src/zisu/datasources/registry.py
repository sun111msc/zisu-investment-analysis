"""数据源注册表与编译期登记门禁。

这是整套系统里**最重要的一道防线**。

背景（真实事故）：在早期版本中，数据源约束写在提示词里，靠模型自觉遵守。
一次分析中，模型为图省事改用通用网页搜索去估一个滚动市盈率，
结果与数据库口径相比偏差达 **+76% ~ +265%**。事后复盘发现，问题不在模型能力，
而在**约束的性质**：提示词是「提醒」，不是「门禁」。

改造后的做法是**编译期登记**：

1. 正式分析前，先产出一份 ``CapabilityManifest`` —— 声明本次计划使用哪些源、
   各自负责哪些语义；
2. ``DataSourceRegistry.verify_manifest()`` 逐条核验：源是否已登记？
   该源是否有资格覆盖这个语义？（例如「新闻源」永远无权提供估值语义）
3. 任一核验失败 → 返回阻断原因，**分析不得开始**。

这叫 fail-closed：默认拒绝，除非显式证明合规。

设计取舍见 ``docs/engineering/adr/0003-fail-closed-registry.md``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

__all__ = [
    "VALUATION_SEMANTICS",
    "NEWS_ALLOWED_SEMANTICS",
    "DataSourceSpec",
    "ManifestIssue",
    "CapabilityManifest",
    "DataSourceRegistry",
    "build_default_registry",
]


# --------------------------------------------------------------------------
# 语义词表
# --------------------------------------------------------------------------

#: 估值类语义 —— 这些标签**只能**由结构化数据源提供。
VALUATION_SEMANTICS: frozenset[str] = frozenset(
    {
        "price",
        "market_cap",
        "pe_ttm",
        "pe_forward",
        "pb",
        "ps",
        "peg",
        "roe",
        "eps",
        "revenue",
        "net_income",
        "gross_margin",
        "operating_cash_flow",
        "capex",
        "total_assets",
        "total_liabilities",
        "inventory",
        "accounts_receivable",
        "pledge_ratio",
        "top10_holders",
        "capacity",
        "market_share",
        "shipment",
        "product_price",
    }
)

#: 新闻/事件类语义 —— 通用网页搜索**只**被允许提供这一组。
#: 这是把「WebSearch 严禁用于 PE / 市值 / 三表 / 产能」这条纪律代码化的结果。
NEWS_ALLOWED_SEMANTICS: frozenset[str] = frozenset(
    {
        "news_event",
        "policy_change",
        "announcement",
        "management_change",
        "regulatory_action",
    }
)


# --------------------------------------------------------------------------
# 数据源声明
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DataSourceSpec:
    """一个已登记数据源的规格说明。"""

    source_id: str
    kind: str
    description: str
    allowed_semantics: frozenset[str]
    priority: int  # 0=L0 主源，1=L1 备源，2=L2 降级源
    ttl_days: int = 1
    structured: bool = True
    base_url: str | None = None
    notes: str = ""

    @property
    def tier(self) -> str:
        return f"L{self.priority}"

    def covers(self, semantic: str) -> bool:
        return semantic in self.allowed_semantics


@dataclass(frozen=True)
class ManifestIssue:
    """能力清单核验发现的一处问题。"""

    code: str
    source_id: str
    semantic: str
    message: str
    blocking: bool = True

    def __str__(self) -> str:  # pragma: no cover - 展示用
        level = "BLOCK" if self.blocking else "WARN"
        return f"[{level}] {self.code} {self.source_id}:{self.semantic} — {self.message}"


@dataclass
class CapabilityManifest:
    """本次分析的能力声明。

    必须在开始分析**之前**产出。事后补登记视为无效。
    """

    symbol: str
    claims: dict[str, set[str]] = field(default_factory=dict)  # source_id -> semantics
    declared_at: date = field(default_factory=date.today)

    def declare(self, source_id: str, semantics: set[str]) -> CapabilityManifest:
        self.claims.setdefault(source_id, set()).update(semantics)
        return self

    def all_semantics(self) -> set[str]:
        out: set[str] = set()
        for s in self.claims.values():
            out |= s
        return out

    def to_markdown(self) -> str:
        lines = [f"**能力清单**（标的 {self.symbol}，声明于 {self.declared_at.isoformat()}）", ""]
        lines.append("| 数据源 | 覆盖语义 |")
        lines.append("|---|---|")
        for sid, sem in sorted(self.claims.items()):
            lines.append(f"| `{sid}` | {', '.join(sorted(sem)) or '—'} |")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# 注册表
# --------------------------------------------------------------------------


class DataSourceRegistry:
    """数据源登记门禁。

    关键性质：**未登记 = 禁止**。没有「先用了再补登记」这条路。
    """

    def __init__(self) -> None:
        self._specs: dict[str, DataSourceSpec] = {}

    # ---- 登记 ----

    def register(self, spec: DataSourceSpec) -> None:
        if spec.source_id in self._specs:
            raise ValueError(f"数据源 {spec.source_id!r} 已登记，不允许覆盖")
        self._specs[spec.source_id] = spec

    def get(self, source_id: str) -> DataSourceSpec | None:
        return self._specs.get(source_id)

    def is_registered(self, source_id: str) -> bool:
        return source_id in self._specs

    def all_specs(self) -> list[DataSourceSpec]:
        return sorted(self._specs.values(), key=lambda s: (s.priority, s.source_id))

    def by_kind(self, kind: str, priority: int | None = None) -> list[DataSourceSpec]:
        specs = [s for s in self.all_specs() if s.kind == kind]
        if priority is not None:
            specs = [s for s in specs if s.priority == priority]
        return specs

    # ---- 门禁 ----

    def verify_manifest(self, manifest: CapabilityManifest) -> list[ManifestIssue]:
        """核验能力清单。返回空列表 = 放行。

        三类核验：
        1. 源必须已登记（未登记 → 阻断）
        2. 源必须有权覆盖所声明的语义（越权 → 阻断）
        3. 计划必须覆盖所有估值类语义（缺源 → 阻断）
        """
        issues: list[ManifestIssue] = []

        for source_id, semantics in manifest.claims.items():
            spec = self.get(source_id)
            if spec is None:
                for sem in sorted(semantics):
                    issues.append(
                        ManifestIssue(
                            code="R001",
                            source_id=source_id,
                            semantic=sem,
                            message=(
                                "数据源未登记。请先在注册表中登记其能力边界，"
                                "否则本次分析不得使用该源。"
                            ),
                        )
                    )
                continue

            for sem in sorted(semantics):
                if not spec.covers(sem):
                    issues.append(
                        ManifestIssue(
                            code="R002",
                            source_id=source_id,
                            semantic=sem,
                            message=(
                                f"越权：该源（kind={spec.kind}，结构化={spec.structured}）"
                                f"未获授权提供语义 {sem!r}。"
                            ),
                        )
                    )

        # 覆盖度检查：声明中的估值语义是否确实有源承接
        declared_cov: set[str] = set()
        for source_id, semantics in manifest.claims.items():
            spec = self.get(source_id)
            if spec is not None:
                declared_cov |= {s for s in semantics if spec.covers(s)}

        return issues

    def verify_semantic_coverage(
        self,
        manifest: CapabilityManifest,
        required: set[str],
    ) -> list[ManifestIssue]:
        """检查必需语义是否已被某个合规源覆盖。"""
        covered: set[str] = set()
        for source_id, semantics in manifest.claims.items():
            spec = self.get(source_id)
            if spec is None:
                continue
            covered |= {s for s in semantics if spec.covers(s)}

        return [
            ManifestIssue(
                code="R003",
                source_id="-",
                semantic=sem,
                message=f"必需语义 {sem!r} 没有任何已登记数据源承接，分析无法完成",
            )
            for sem in sorted(required - covered)
        ]

    # ---- 时效 ----

    def check_freshness(
        self,
        source_id: str,
        as_of: date,
        *,
        reference: date | None = None,
    ) -> ManifestIssue | None:
        """检查数据是否超过该源的时效上限。"""
        spec = self.get(source_id)
        if spec is None:
            return ManifestIssue(
                code="R004",
                source_id=source_id,
                semantic="-",
                message="未登记源无法校验时效",
            )
        ref = reference or date.today()
        if ref - as_of > timedelta(days=spec.ttl_days):
            return ManifestIssue(
                code="R005",
                source_id=source_id,
                semantic="-",
                message=(
                    f"数据时点 {as_of.isoformat()} 超过该源时效上限 "
                    f"{spec.ttl_days} 天（参考日 {ref.isoformat()}）"
                ),
                blocking=False,
            )
        return None


# --------------------------------------------------------------------------
# 默认注册表（逻辑源，非具体厂商）
# --------------------------------------------------------------------------


def build_default_registry() -> DataSourceRegistry:
    """构造一份默认注册表。

    这里登记的是**逻辑数据源**（primary / backup / degraded），而不是具体厂商。
    接入真实数据时，把你的适配器绑定到对应逻辑源即可 ——
    这样更换供应商不会动摇门禁规则。
    """
    r = build_registry([], seed_default=True)
    return r


def build_registry(
    specs: list[DataSourceSpec] | None = None,
    *,
    seed_default: bool = True,
) -> DataSourceRegistry:
    reg = DataSourceRegistry()
    if seed_default:
        for spec in _DEFAULT_SPECS:
            reg.register(spec)
    for spec in specs or []:
        reg.register(spec)
    return reg


_DEFAULT_SPECS: list[DataSourceSpec] = [
    DataSourceSpec(
        source_id="market.quote.primary",
        kind="market_data",
        description="行情主源：价量、估值倍数、市值、股本",
        allowed_semantics=frozenset(
            {
                "price",
                "market_cap",
                "pe_ttm",
                "pe_forward",
                "pb",
                "ps",
                "peg",
                "volume",
                "shares_outstanding",
            }
        ),
        priority=0,
        ttl_days=1,
        structured=True,
    ),
    DataSourceSpec(
        source_id="market.quote.backup",
        kind="market_data",
        description="行情备源：主源不可用时接管",
        allowed_semantics=frozenset(
            {
                "price",
                "market_cap",
                "pe_ttm",
                "pe_forward",
                "pb",
                "ps",
                "peg",
                "volume",
                "shares_outstanding",
            }
        ),
        priority=1,
        ttl_days=1,
        structured=True,
    ),
    DataSourceSpec(
        source_id="financials.statements.primary",
        kind="financials",
        description="三大报表主源：损益、资产负债、现金流量表全科目",
        allowed_semantics=frozenset(
            {
                "revenue",
                "net_income",
                "gross_margin",
                "operating_cash_flow",
                "capex",
                "total_assets",
                "total_liabilities",
                "total_equity",
                "current_assets",
                "current_liabilities",
                "long_term_debt",
                "retained_earnings",
                "ebit",
                "depreciation",
                "sga",
                "ppe",
                "inventory",
                "accounts_receivable",
                "roe",
                "eps",
                "revenue_prior",
                "net_income_prior",
                "total_assets_prior",
            }
        ),
        priority=0,
        ttl_days=120,
        structured=True,
    ),
    DataSourceSpec(
        source_id="financials.statements.backup",
        kind="financials",
        description="三大报表备源",
        allowed_semantics=frozenset(
            {
                "revenue",
                "net_income",
                "gross_margin",
                "operating_cash_flow",
                "capex",
                "total_assets",
                "total_liabilities",
                "total_equity",
                "current_assets",
                "current_liabilities",
                "long_term_debt",
                "retained_earnings",
                "ebit",
                "depreciation",
                "sga",
                "ppe",
                "inventory",
                "accounts_receivable",
                "roe",
                "eps",
                "revenue_prior",
                "net_income_prior",
                "total_assets_prior",
            }
        ),
        priority=1,
        ttl_days=120,
        structured=True,
    ),
    DataSourceSpec(
        source_id="shareholding.registry",
        kind="ownership",
        description="股东与质押：十大股东、质押比例",
        allowed_semantics=frozenset({"top10_holders", "pledge_ratio"}),
        priority=0,
        ttl_days=120,
        structured=True,
    ),
    DataSourceSpec(
        source_id="industry.statistics",
        kind="industry",
        description="行业结构化统计：产能、市占率、出货量、产品价格",
        allowed_semantics=frozenset({"capacity", "market_share", "shipment", "product_price"}),
        priority=0,
        ttl_days=180,
        structured=True,
    ),
    DataSourceSpec(
        source_id="research.consensus",
        kind="research",
        description="卖方一致预期",
        allowed_semantics=frozenset({"eps", "pe_forward", "revenue", "net_income"}),
        priority=1,
        ttl_days=30,
        structured=True,
    ),
    DataSourceSpec(
        source_id="news.events",
        kind="news",
        description=(
            "新闻与事件线索源。**刻意不授予任何估值类语义** —— "
            "通用网页检索在数值口径上不可靠，只允许用于线索发现。"
        ),
        allowed_semantics=NEWS_ALLOWED_SEMANTICS,
        priority=2,
        ttl_days=3,
        structured=False,
        notes="本源的 allowed_semantics 是反例清单：任何估值语义都会被 R002 拦截。",
    ),
]
