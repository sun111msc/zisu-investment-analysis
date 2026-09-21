"""反向 DCF —— 把市值当已知量，反解市场的隐含预期。

**这是本体系估值部分的核心工具，而且它刻意不产出目标价。**

正向 DCF 问的是「这家公司值多少钱」，答案是观点。
反向 DCF 问的是「当前市值要求这家公司未来做到什么」，答案是事实约束。

为什么后者更重要：DCF 的输出对永续假设极度敏感（终值常占企业价值的
60%-85%），所以正向 DCF 的「目标价」本质上是在输出自己的假设。
而反向 DCF 把假设的球踢回给市场 ——
如果反解出的隐含增速是 35%、且需要连续十年维持，那么问题就变成了
「这个增速可信吗」，这是一个**可以被事实检验**的问题。

因此本模块的设计约束：

1. **不输出目标价。** 输出的是隐含增速与隐含折现率。
2. **不收敛就是结论。** 若市值高于任何合理参数下的价值，说明市值无法用
   现金流假设解释 —— 这本身是重要信号（反身性溢价 / 泡沫），而不是失败。
3. **永不返回看似精确的伪解。** 二分法达到迭代上限即判定未收敛。

设计取舍见 ``docs/engineering/adr/0005-reverse-dcf-guardrail.md``。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from zisu.valuation.dcf import MIN_SPREAD, enterprise_value

__all__ = [
    "ReverseDCFResult",
    "solve_implied_g",
    "solve_implied_wacc",
    "interpret",
]


@dataclass(frozen=True)
class ReverseDCFResult:
    """反解结果。

    ``converged=False`` 时 ``implied_g`` / ``implied_wacc`` 为 ``None`` ——
    不给出伪解。
    """

    converged: bool
    target_ev: float
    achieved_ev: float
    implied_g: float | None = None
    implied_wacc: float | None = None
    iterations: int = 0
    bounds_hit: bool = False
    note: str = ""

    @property
    def residual(self) -> float:
        return self.achieved_ev - self.target_ev

    def to_gate_payload(self) -> dict[str, object]:
        """转成 GATE-50 需要的结构。"""
        return {
            "converged": self.converged,
            "implied_g": self.implied_g,
            "implied_wacc": self.implied_wacc,
            "note": self.note,
        }


def _ev(fcff: Sequence[float], wacc: float, g: float) -> float | None:
    """求值；参数非法时返回 None。"""
    try:
        ev, _, _ = enterprise_value(fcff, wacc, g)
        return ev
    except ValueError:
        return None


def solve_implied_g(
    target_ev: float,
    fcff_forecast: Sequence[float],
    wacc: float,
    *,
    g_low: float = -0.10,
    g_high: float | None = None,
    tol: float = 1e-6,
    max_iter: int = 200,
) -> ReverseDCFResult:
    """反解永续增长率 g，使 DCF 企业价值等于给定市值。

    EV 关于 g 单调递增，因此可直接二分。
    """
    if not fcff_forecast:
        raise ValueError("预测期现金流为空")
    if target_ev <= 0:
        raise ValueError("目标企业价值必须为正")

    hi = g_high if g_high is not None else wacc - MIN_SPREAD
    hi = min(hi, wacc - MIN_SPREAD)
    if hi <= g_low:
        return ReverseDCFResult(
            converged=False,
            target_ev=target_ev,
            achieved_ev=float("nan"),
            note=f"搜索区间非法：上界 {hi:.4%} ≤ 下界 {g_low:.4%}（WACC 过低）",
        )

    ev_low = _ev(fcff_forecast, wacc, g_low)
    ev_high = _ev(fcff_forecast, wacc, hi)
    if ev_low is None or ev_high is None:
        return ReverseDCFResult(
            converged=False,
            target_ev=target_ev,
            achieved_ev=float("nan"),
            note="边界求值失败，无法开始二分",
        )

    if target_ev < ev_low:
        return ReverseDCFResult(
            converged=False,
            target_ev=target_ev,
            achieved_ev=ev_low,
            bounds_hit=True,
            note=(
                f"市值低于最悲观假设下的价值（g={g_low:.0%} 时 EV={ev_low:,.0f}），"
                "隐含预期低于搜索下界"
            ),
        )
    if target_ev > ev_high:
        return ReverseDCFResult(
            converged=False,
            target_ev=target_ev,
            achieved_ev=ev_high,
            bounds_hit=True,
            note=(
                f"市值高于最乐观假设下的价值（g={hi:.2%} 时 EV={ev_high:,.0f}），"
                "现金流假设无法解释当前市值 —— 需考虑反身性溢价或市场错误定价"
            ),
        )

    lo, high = g_low, hi
    mid = lo
    for i in range(1, max_iter + 1):
        mid = (lo + high) / 2.0
        ev_mid = _ev(fcff_forecast, wacc, mid)
        if ev_mid is None:
            high = mid
            continue
        if abs(ev_mid - target_ev) <= tol * max(target_ev, 1.0):
            return ReverseDCFResult(
                converged=True,
                target_ev=target_ev,
                achieved_ev=ev_mid,
                implied_g=mid,
                implied_wacc=wacc,
                iterations=i,
                note=f"隐含永续增速 {mid:.2%}（折现率固定 {wacc:.2%}）",
            )
        if ev_mid < target_ev:
            lo = mid
        else:
            high = mid

    return ReverseDCFResult(
        converged=False,
        target_ev=target_ev,
        achieved_ev=_ev(fcff_forecast, wacc, mid) or float("nan"),
        iterations=max_iter,
        note="达到迭代上限仍未收敛，不给出伪解",
    )


def solve_implied_wacc(
    target_ev: float,
    fcff_forecast: Sequence[float],
    terminal_g: float,
    *,
    wacc_low: float = 0.03,
    wacc_high: float = 0.40,
    tol: float = 1e-6,
    max_iter: int = 200,
) -> ReverseDCFResult:
    """反解折现率，使 DCF 企业价值等于给定市值。

    EV 关于 WACC 单调递减（WACC 越高，价值越低），二分方向与 g 相反。
    """
    if not fcff_forecast:
        raise ValueError("预测期现金流为空")
    lo = max(wacc_low, terminal_g + MIN_SPREAD)
    hi = max(wacc_high, lo + 1e-4)

    ev_low = _ev(fcff_forecast, lo, terminal_g)
    ev_high = _ev(fcff_forecast, hi, terminal_g)
    if ev_low is None or ev_high is None:
        return ReverseDCFResult(
            converged=False,
            target_ev=target_ev,
            achieved_ev=float("nan"),
            note="边界求值失败，无法开始二分",
        )

    if target_ev > ev_low:
        return ReverseDCFResult(
            converged=False,
            target_ev=target_ev,
            achieved_ev=ev_low,
            bounds_hit=True,
            note=(
                f"市值高于最低折现率（{lo:.2%}）下的价值 {ev_low:,.0f}，"
                "市场要求的回报率低于搜索下界"
            ),
        )
    if target_ev < ev_high:
        return ReverseDCFResult(
            converged=False,
            target_ev=target_ev,
            achieved_ev=ev_high,
            bounds_hit=True,
            note=f"市值低于最高折现率（{hi:.2%}）下的价值 {ev_high:,.0f}",
        )

    a, b = lo, hi  # ev(a) > target > ev(b)
    mid = (a + b) / 2.0
    for i in range(1, max_iter + 1):
        mid = (a + b) / 2.0
        ev_mid = _ev(fcff_forecast, mid, terminal_g)
        if ev_mid is None:
            b = mid
            continue
        if abs(ev_mid - target_ev) <= tol * max(target_ev, 1.0):
            return ReverseDCFResult(
                converged=True,
                target_ev=target_ev,
                achieved_ev=ev_mid,
                implied_wacc=mid,
                implied_g=terminal_g,
                iterations=i,
                note=f"隐含折现率 {mid:.2%}（永续增速固定 {terminal_g:.2%}）",
            )
        if ev_mid > target_ev:
            a = mid
        else:
            b = mid

    return ReverseDCFResult(
        converged=False,
        target_ev=target_ev,
        achieved_ev=_ev(fcff_forecast, mid, terminal_g) or float("nan"),
        iterations=max_iter,
        note="达到迭代上限仍未收敛，不给出伪解",
    )


def interpret(result: ReverseDCFResult, *, growth_reference: float | None = None) -> str:
    """把反解结果翻译成一句可被检验的话。"""
    if not result.converged:
        return f"未收敛：{result.note}"

    g = result.implied_g
    wacc = result.implied_wacc
    parts = [f"当前市值隐含：永续增速 {g:.2%}、折现率 {wacc:.2%}。"]

    if growth_reference is not None and g is not None:
        gap = g - growth_reference
        if gap > 0.05:
            parts.append(
                f"该增速比历史/同业参考值 {growth_reference:.2%} 高 {gap:.2%}，"
                "需要验证新增产能、客户订单或价格弹性是否支撑。"
            )
        elif gap < -0.05:
            parts.append(
                f"该增速低于参考值 {growth_reference:.2%}，市场可能在定价增速下滑。"
            )
        else:
            parts.append(f"该增速与参考值 {growth_reference:.2%} 基本一致。")

    return "".join(parts)
