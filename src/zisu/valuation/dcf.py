"""现金流折现（DCF）基础模型。

定位说明（重要）：在本体系中，正向 DCF **不是**主要的目标价来源，
而是用来检验「市场当前定价隐含了什么假设」。

原因：终值假设对结果的影响通常在 60%-80% 之间，任何单点 DCF 输出的
「精确」目标价都是伪精确。真正有信息量的是**反解**——
把市值当作已知量，问「市场在第几年、以什么增速、要求多少回报」。
见 ``zisu/valuation/reverse_dcf.py``。

本模块同时提供一个显式的失效检测：当 WACC 与永续增速的差距小于阈值时，
永续期现值会被放大到失去意义，此时应判定模型无效而非输出一个巨大数字。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = ["DCFInput", "DCFResult", "enterprise_value", "equity_value", "MIN_SPREAD"]


#: WACC 与永续增速的最小利差。低于此值时永续模型数值不稳定。
MIN_SPREAD = 0.015


@dataclass(frozen=True)
class DCFInput:
    fcff_forecast: tuple[float, ...]  # 显式预测期各年自由现金流
    wacc: float
    terminal_g: float
    net_debt: float = 0.0
    shares_outstanding: float | None = None
    mid_year_convention: bool = False


@dataclass(frozen=True)
class DCFResult:
    enterprise_value: float
    pv_explicit: float
    pv_terminal: float
    terminal_share: float  # 终值占企业价值的比例 —— 用于判断结论稳健性
    equity_value: float
    per_share: float | None
    valid: bool
    note: str = ""


def enterprise_value(
    fcff_forecast: Sequence[float],
    wacc: float,
    terminal_g: float,
    *,
    mid_year_convention: bool = False,
) -> tuple[float, float, float]:
    """返回 ``(企业价值, 显式期现值, 终值现值)``。"""
    if not fcff_forecast:
        raise ValueError("预测期现金流为空")
    if wacc <= terminal_g:
        raise ValueError(
            f"折现率 {wacc:.4%} 不高于永续增速 {terminal_g:.4%}，永续增长模型不成立"
        )

    offset = 0.5 if mid_year_convention else 0.0
    pv_explicit = sum(
        cf / (1.0 + wacc) ** (i + 1 - offset) for i, cf in enumerate(fcff_forecast)
    )
    terminal_cf = fcff_forecast[-1] * (1.0 + terminal_g)
    terminal_value = terminal_cf / (wacc - terminal_g)
    pv_terminal = terminal_value / (1.0 + wacc) ** (len(fcff_forecast) - offset)

    return pv_explicit + pv_terminal, pv_explicit, pv_terminal


def equity_value(inp: DCFInput) -> DCFResult:
    """由 FCFF 推导股权价值与每股价值，并给出稳健性判定。"""
    spread = inp.wacc - inp.terminal_g
    if spread <= 0:
        return DCFResult(
            enterprise_value=float("nan"),
            pv_explicit=float("nan"),
            pv_terminal=float("nan"),
            terminal_share=float("nan"),
            equity_value=float("nan"),
            per_share=None,
            valid=False,
            note=f"折现率与永续增速利差 {spread:.4%} 非正，模型失效",
        )

    ev, pv_exp, pv_term = enterprise_value(
        inp.fcff_forecast,
        inp.wacc,
        inp.terminal_g,
        mid_year_convention=inp.mid_year_convention,
    )
    eq = ev - inp.net_debt
    per_share = (eq / inp.shares_outstanding) if inp.shares_outstanding else None
    share = pv_term / ev if ev else float("nan")

    valid = spread >= MIN_SPREAD
    note = ""
    if not valid:
        note = (
            f"利差 {spread:.2%} 低于稳健阈值 {MIN_SPREAD:.2%}，"
            "终值主导结果，DCF 数值仅供参考"
        )
    elif share > 0.85:
        note = f"终值占企业价值 {share:.0%}，结论对永续假设高度敏感"

    return DCFResult(
        enterprise_value=ev,
        pv_explicit=pv_exp,
        pv_terminal=pv_term,
        terminal_share=share,
        equity_value=eq,
        per_share=per_share,
        valid=valid,
        note=note,
    )
