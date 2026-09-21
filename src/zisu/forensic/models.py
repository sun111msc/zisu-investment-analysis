"""法务会计四大模型。

这四个模型都是公开的学术成果，本模块提供工程实现。它们各自回答一个
特定问题，**不构成对财务造假的判定** —— 全部是筛查工具，命中只意味着
「值得进一步核查」，而不是结论。

| 模型 | 回答的问题 | 输出 |
|---|---|---|
| Beneish M-Score | 盈余操纵的概率是否异常偏高 | 分数 + 八个分解项 |
| Piotroski F-Score | 基本面是否在改善 | 0-9 分 + 九个信号明细 |
| Altman Z-Score | 短期财务困境风险 | 分数 + 分区 |
| Sloan 应计 | 利润中非现金成分占比 | 应计比率 |

实现约定：分母为零时返回 ``None`` 而非 0 或 inf —— 让「无法计算」保持可见。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "FinancialSnapshot",
    "ScoreResult",
    "beneish_m_score",
    "piotroski_f_score",
    "altman_z_score",
    "sloan_accrual_ratio",
    "run_all",
]


@dataclass(frozen=True)
class FinancialSnapshot:
    """一个报告期的财务快照。金额单位需全表一致。"""

    year: int
    revenue: float
    cogs: float
    net_income: float
    cfo: float
    total_assets: float
    current_assets: float
    current_liabilities: float
    long_term_debt: float
    total_liabilities: float
    total_equity: float
    retained_earnings: float
    ebit: float
    depreciation: float
    sga: float
    receivables: float
    ppe: float
    market_value_equity: float | None = None
    shares_outstanding: float | None = None

    @property
    def gross_profit(self) -> float:
        return self.revenue - self.cogs

    @property
    def gross_margin(self) -> float | None:
        return self.gross_profit / self.revenue if self.revenue else None

    @property
    def working_capital(self) -> float:
        return self.current_assets - self.current_liabilities

    @property
    def roa(self) -> float | None:
        return self.net_income / self.total_assets if self.total_assets else None

    @property
    def asset_turnover(self) -> float | None:
        return self.revenue / self.total_assets if self.total_assets else None

    @property
    def leverage(self) -> float | None:
        return self.total_liabilities / self.total_assets if self.total_assets else None


@dataclass
class ScoreResult:
    model: str
    score: float | None
    verdict: str
    components: dict[str, Any] = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "score": self.score,
            "verdict": self.verdict,
            "components": self.components,
            "caveats": self.caveats,
        }


def _safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


# --------------------------------------------------------------------------
# Beneish M-Score
# --------------------------------------------------------------------------

_BENEISH_COEF = {
    "DSRI": 0.920,
    "GMI": 0.528,
    "AQI": 0.404,
    "SGI": 0.892,
    "DEPI": 0.115,
    "SGAI": -0.172,
    "TATA": 4.679,
    "LVGI": -0.327,
}
_BENEISH_INTERCEPT = -4.84
_BENEISH_THRESHOLD = -1.78


def beneish_m_score(current: FinancialSnapshot, prior: FinancialSnapshot) -> ScoreResult:
    """Beneish M-Score。高于 -1.78 视为需要进一步核查。

    注意：本模型对**高速成长的公司会给出偏高分数**（因为 SGI 系数为 0.892），
    这是已知的误报来源，判定时必须结合成长性说明。
    """
    caveats: list[str] = []
    c: dict[str, float | None] = {}

    c["DSRI"] = _safe_div(
        _safe_div(current.receivables, current.revenue),
        _safe_div(prior.receivables, prior.revenue),
    )
    gm_cur, gm_prior = current.gross_margin, prior.gross_margin
    c["GMI"] = _safe_div(gm_prior, gm_cur)
    aq_cur = 1 - _safe_div(current.current_assets + current.ppe, current.total_assets) if current.total_assets else None
    aq_prior = 1 - _safe_div(prior.current_assets + prior.ppe, prior.total_assets) if prior.total_assets else None
    c["AQI"] = _safe_div(aq_cur, aq_prior)
    c["SGI"] = _safe_div(current.revenue, prior.revenue)

    dep_rate_cur = _safe_div(current.depreciation, current.depreciation + current.ppe)
    dep_rate_prior = _safe_div(prior.depreciation, prior.depreciation + prior.ppe)
    c["DEPI"] = _safe_div(dep_rate_prior, dep_rate_cur)
    c["SGAI"] = _safe_div(
        _safe_div(current.sga, current.revenue), _safe_div(prior.sga, prior.revenue)
    )
    c["TATA"] = _safe_div(current.net_income - current.cfo, current.total_assets)
    c["LVGI"] = _safe_div(
        _safe_div(current.long_term_debt + current.current_liabilities, current.total_assets),
        _safe_div(prior.long_term_debt + prior.current_liabilities, prior.total_assets),
    )

    missing = [k for k, v in c.items() if v is None]
    if missing:
        return ScoreResult(
            model="Beneish M-Score",
            score=None,
            verdict=f"无法计算：{', '.join(missing)} 缺少分母或上期数据",
            components={k: None for k in _BENEISH_COEF},
            caveats=["分母为零或数据缺失时不给分，避免用 0 充当计算结果"],
        )

    m = _BENEISH_INTERCEPT + sum(_BENEISH_COEF[k] * (c[k] or 0.0) for k in _BENEISH_COEF)

    if m > _BENEISH_THRESHOLD:
        verdict = f"M={m:.2f} > {_BENEISH_THRESHOLD}，需进一步核查收入确认与应计项目"
    else:
        verdict = f"M={m:.2f} ≤ {_BENEISH_THRESHOLD}，未触发盈余操纵预警"

    sgi = c.get("SGI") or 0
    if sgi > 1.3:
        caveats.append(
            f"营收指数 SGI={sgi:.2f} 较高，高成长公司在本模型中天然得分偏高，存在误报"
        )
    if current.market_value_equity is None:
        caveats.append("未使用市值变量，本计算为原始八变量版本")

    return ScoreResult(
        model="Beneish M-Score",
        score=m,
        verdict=verdict,
        components={k: c[k] for k in _BENEISH_COEF},
        caveats=caveats,
    )


# --------------------------------------------------------------------------
# Piotroski F-Score
# --------------------------------------------------------------------------


def piotroski_f_score(current: FinancialSnapshot, prior: FinancialSnapshot) -> ScoreResult:
    """Piotroski F-Score，0-9 分。≥7 视为基本面改善。"""
    signals: dict[str, bool | None] = {}

    roa = current.roa
    cfo_ta = _safe_div(current.cfo, current.total_assets)
    roa_prior = prior.roa

    signals["1_roa_positive"] = (roa > 0) if roa is not None else None
    signals["2_cfo_positive"] = (current.cfo > 0)
    signals["3_roa_improving"] = (
        (roa > roa_prior) if (roa is not None and roa_prior is not None) else None
    )
    signals["4_cfo_exceeds_roa"] = (
        (cfo_ta > roa) if (cfo_ta is not None and roa is not None) else None
    )

    lev_cur = _safe_div(current.long_term_debt, current.total_assets)
    lev_prior = _safe_div(prior.long_term_debt, prior.total_assets)
    signals["5_leverage_down"] = (
        (lev_cur < lev_prior) if (lev_cur is not None and lev_prior is not None) else None
    )

    cr_cur = _safe_div(current.current_assets, current.current_liabilities)
    cr_prior = _safe_div(prior.current_assets, prior.current_liabilities)
    signals["6_liquidity_up"] = (
        (cr_cur > cr_prior) if (cr_cur is not None and cr_prior is not None) else None
    )

    if current.shares_outstanding is not None and prior.shares_outstanding is not None:
        signals["7_no_dilution"] = current.shares_outstanding <= prior.shares_outstanding
    else:
        signals["7_no_dilution"] = None

    gm_cur, gm_prior = current.gross_margin, prior.gross_margin
    signals["8_margin_up"] = (
        (gm_cur > gm_prior) if (gm_cur is not None and gm_prior is not None) else None
    )

    at_cur, at_prior = current.asset_turnover, prior.asset_turnover
    signals["9_turnover_up"] = (
        (at_cur > at_prior) if (at_cur is not None and at_prior is not None) else None
    )

    computable = {k: v for k, v in signals.items() if v is not None}
    score = float(sum(1 for v in computable.values() if v))
    max_possible = len(computable) * 9 / len(signals)

    caveats: list[str] = []
    if signals["7_no_dilution"] is None:
        caveats.append("缺少股本数据，第 7 项（未增发）未计入，满分按比例折算")

    if score >= 7:
        verdict = f"F={score:.0f}，基本面改善信号强"
    elif score >= 4:
        verdict = f"F={score:.0f}，基本面中性"
    else:
        verdict = f"F={score:.0f}，基本面存在恶化信号"

    return ScoreResult(
        model="Piotroski F-Score",
        score=score,
        verdict=verdict,
        components={"signals": signals, "max_possible": round(max_possible, 1)},
        caveats=caveats,
    )


# --------------------------------------------------------------------------
# Altman Z-Score
# --------------------------------------------------------------------------

_ALTMAN_BANDS = ((2.99, "安全区"), (1.81, "灰色区"), (float("-inf"), "困境区"))


def altman_z_score(s: FinancialSnapshot, *, listed: bool = True) -> ScoreResult:
    """Altman Z-Score（上市公司版）。

    未上市或市值缺失时，改用 Z'' 版本（去掉 X4 市场价值项，并使用账面权益）。
    """
    caveats: list[str] = []

    x1 = _safe_div(s.working_capital, s.total_assets)
    x2 = _safe_div(s.retained_earnings, s.total_assets)
    x3 = _safe_div(s.ebit, s.total_assets)
    x5 = _safe_div(s.revenue, s.total_assets)

    use_market = listed and s.market_value_equity is not None
    if use_market:
        x4 = _safe_div(s.market_value_equity, s.total_liabilities)
        weights = (1.2, 1.4, 3.3, 0.6, 1.0)
        version = "Z（上市公司版）"
    else:
        x4 = _safe_div(s.total_equity, s.total_liabilities)
        weights = (6.56, 3.26, 6.72, 0.0, 1.05)
        version = "Z''（非上市/市值缺失版）"
        caveats.append("市值缺失，已自动切换 Z'' 版本，系数与分区阈值不同")

    xs = (x1, x2, x3, x4, x5)
    if any(x is None for x in xs):
        return ScoreResult(
            model="Altman Z-Score",
            score=None,
            verdict="无法计算：关键分母缺失",
            components=dict(zip(("X1", "X2", "X3", "X4", "X5"), xs, strict=True)),
            caveats=caveats,
        )

    z = sum(w * (x or 0.0) for w, x in zip(weights, xs, strict=True))

    if use_market:
        band = next(name for cutoff, name in _ALTMAN_BANDS if z > cutoff)
    else:
        band = "安全区" if z > 2.6 else ("灰色区" if z > 1.1 else "困境区")

    caveats.append(
        "Altman 模型基于美国制造业样本校准，对轻资产、高研发或高预收模式的公司"
        "区分度下降，仅作筛查"
    )

    return ScoreResult(
        model=f"Altman Z-Score · {version}",
        score=z,
        verdict=f"Z={z:.2f}，{band}",
        components=dict(zip(("X1", "X2", "X3", "X4", "X5"), xs, strict=True)),
        caveats=caveats,
    )


# --------------------------------------------------------------------------
# Sloan 应计
# --------------------------------------------------------------------------


def sloan_accrual_ratio(current: FinancialSnapshot, *, threshold: float = 0.10) -> ScoreResult:
    """应计比率 =（净利润 − 经营现金流）/ 总资产。

    该比率高，说明利润中非现金成分多，盈余质量偏低。
    """
    ratio = _safe_div(current.net_income - current.cfo, current.total_assets)
    if ratio is None:
        return ScoreResult(
            model="Sloan 应计比率",
            score=None,
            verdict="无法计算：总资产为零",
            components={},
        )

    if ratio > threshold:
        verdict = f"应计比率 {ratio:.2%} 高于 {threshold:.0%}，利润现金含量偏低"
    elif ratio < 0:
        verdict = f"应计比率为负（{ratio:.2%}），现金流优于账面利润"
    else:
        verdict = f"应计比率 {ratio:.2%}，处于正常区间"

    return ScoreResult(
        model="Sloan 应计比率",
        score=ratio,
        verdict=verdict,
        components={
            "net_income": current.net_income,
            "cfo": current.cfo,
            "total_assets": current.total_assets,
        },
        caveats=["应计比率对重资产扩张期的公司会自然偏高，需结合资本开支节奏解读"],
    )


def run_all(current: FinancialSnapshot, prior: FinancialSnapshot | None = None) -> dict[str, ScoreResult]:
    """跑全套模型。缺上期数据时跳过需要两期的模型。"""
    out: dict[str, ScoreResult] = {}
    if prior is not None:
        out["beneish"] = beneish_m_score(current, prior)
        out["piotroski"] = piotroski_f_score(current, prior)
    out["altman"] = altman_z_score(current)
    out["sloan"] = sloan_accrual_ratio(current)
    return out
