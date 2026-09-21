"""可比公司与相对估值。

相对估值回答的是「现在贵不贵」，绝对估值回答的是「值不值」。
两者必须交叉 —— 只有单锚的估值结论不予采信（见 GATE-51）。

本模块的刻意设计：**输出的是分位区间，不是单点倍数**。
「给 30 倍 PE」是一种观点；「当前估值处于同业第 85 分位」是一个事实。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import median

__all__ = ["PeerMetrics", "PeerValuation", "percentile_of", "peer_valuation"]


@dataclass(frozen=True)
class PeerMetrics:
    name: str
    pe: float | None = None
    pb: float | None = None
    ps: float | None = None
    ev_ebitda: float | None = None
    roic: float | None = None
    revenue_growth: float | None = None
    is_target: bool = False

    def metric(self, key: str) -> float | None:
        return getattr(self, key, None)


@dataclass
class PeerValuation:
    metric: str
    target_value: float | None
    peer_count: int
    peer_median: float | None
    peer_p25: float | None
    peer_p75: float | None
    percentile: float | None
    premium_to_median: float | None
    note: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "target_value": self.target_value,
            "peer_count": self.peer_count,
            "peer_median": self.peer_median,
            "peer_p25": self.peer_p25,
            "peer_p75": self.peer_p75,
            "percentile": self.percentile,
            "premium_to_median": self.premium_to_median,
            "note": self.note,
        }


def _quantile(sorted_vals: Sequence[float], q: float) -> float:
    """线性插值分位数。"""
    if not sorted_vals:
        raise ValueError("空序列")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def percentile_of(value: float, population: Sequence[float]) -> float:
    """value 在 population 中的分位（0-1）。使用「小于等于」计数。"""
    if not population:
        raise ValueError("总体为空")
    below = sum(1 for x in population if x <= value)
    return below / len(population)


def peer_valuation(
    target: PeerMetrics,
    peers: Sequence[PeerMetrics],
    metric: str = "pe",
    *,
    min_peers: int = 4,
) -> PeerValuation:
    """计算目标公司在同业中的相对位置。"""
    warnings: list[str] = []

    peer_vals = [
        v
        for p in peers
        if not p.is_target and (v := p.metric(metric)) is not None and v > 0
    ]
    if len(peer_vals) < min_peers:
        warnings.append(
            f"有效同业样本仅 {len(peer_vals)} 家，少于 {min_peers} 家门槛，"
            "相对估值结论不稳定"
        )

    tgt = target.metric(metric)
    if tgt is not None and tgt <= 0:
        warnings.append(f"目标公司 {metric} 为负或零，相对估值不适用（应改用 PB 或 PS）")
        tgt = None

    if not peer_vals:
        return PeerValuation(
            metric=metric,
            target_value=tgt,
            peer_count=0,
            peer_median=None,
            peer_p25=None,
            peer_p75=None,
            percentile=None,
            premium_to_median=None,
            note="无可比样本，本法不适用",
            warnings=warnings,
        )

    s = sorted(peer_vals)
    med = median(s)
    p25 = _quantile(s, 0.25)
    p75 = _quantile(s, 0.75)

    pct = percentile_of(tgt, s) if tgt is not None else None
    prem = ((tgt - med) / med) if (tgt is not None and med) else None

    if pct is not None:
        if pct >= 0.8:
            note = f"处于同业第 {pct:.0%} 分位，估值偏高，需要更高增速或更强护城河支撑"
        elif pct <= 0.2:
            note = f"处于同业第 {pct:.0%} 分位，估值偏低，需排查是否为基本面劣化所致"
        else:
            note = f"处于同业第 {pct:.0%} 分位，位于中位区间"
    else:
        note = "目标值缺失，无法定位分位"

    return PeerValuation(
        metric=metric,
        target_value=tgt,
        peer_count=len(peer_vals),
        peer_median=med,
        peer_p25=p25,
        peer_p75=p75,
        percentile=pct,
        premium_to_median=prem,
        note=note,
        warnings=warnings,
    )
