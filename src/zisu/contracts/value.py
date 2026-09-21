"""类型化数值契约（Typed Value Contract）。

本模块是整个系统的基础设施层：**任何进入分析链路的数值都必须包装为
``TypedValue``**，携带七个属性。这样做的直接目的是消除金融分析中
最高频的三类静默错误：

1. **单位混用** —— 「营收 57.5」是元、万元还是亿元？「毛利率 89.8」
   是百分比还是千分比？
2. **时点错配** —— 用 2024 年报数据去解释 2026 年的估值，却没有任何字段
   记录这个数据是什么时候的。
3. **来源丢失** —— 一串数字在报告里流转五轮之后，已经没人知道它来自哪里，
   也无法复现。

契约在构造时即校验，违反契约会在闸门层被拦截，而不是在结论里变成一个
看起来合理的错误数字。

设计取舍见 ``docs/engineering/adr/0002-typed-numeric-contract.md``。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from enum import Enum
from typing import Any

__all__ = [
    "Frequency",
    "Severity",
    "Unit",
    "ContractViolation",
    "UnitMismatchError",
    "MissingValueError",
    "TypedValue",
    "sum_values",
]


class Frequency(str, Enum):
    """数值的时间粒度。"""

    POINT = "point"  # 时点数：股价、市值、股东户数
    ANNUAL = "annual"  # 年度：2024 年营收
    QUARTERLY = "quarterly"  # 单季度
    TTM = "ttm"  # 滚动十二个月
    DAILY = "daily"  # 日频：成交量、北向净流入


class Unit(str, Enum):
    """量纲。刻意保持精简 —— 量纲越多，契约越难维护。"""

    CNY = "CNY"  # 货币金额，配合 currency 字段使用
    SHARES = "SHARES"  # 股数 / 手数
    PERCENT = "PERCENT"  # 百分数，取值范围 [-100, 100] 之外视为可疑
    RATIO = "RATIO"  # 无量纲比值：倍数、周转率、占比（0-1 小数形式）
    RATIO_TTM = "RATIO_TTM"  # 估值倍数，语义上依赖 ttm 盈利
    COUNT = "COUNT"  # 家数、台数、人数


class Severity(str, Enum):
    ERROR = "ERROR"  # 阻断：该数值不得进入分析链路
    WARNING = "WARNING"  # 提示：可继续，但必须在报告中披露


@dataclass(frozen=True)
class ContractViolation:
    """一条契约违反记录。"""

    code: str
    field: str
    message: str
    severity: Severity = Severity.ERROR

    def __str__(self) -> str:  # pragma: no cover - 展示用
        return f"[{self.severity.value}] {self.code} @ {self.field}: {self.message}"


class UnitMismatchError(ValueError):
    """试图对量纲不同的两个数值做加减。"""


class MissingValueError(ValueError):
    """试图对缺失值做算术运算，或用零值填充缺失。"""


@dataclass(frozen=True)
class TypedValue:
    """携带七属性的数值。

    Attributes:
        value: 数值本体。``None`` 表示缺失 —— **绝不允许用 0 代替**。
        unit: 量纲。
        semantic: 语义标签，例如 ``revenue`` / ``pe_ttm`` / ``gross_margin``。
        as_of: 该数值对应的时点。这是防止时点错配的核心字段。
        source: 数据来源标识，必须已在数据源注册表中登记。
        currency: 币种，仅当 ``unit == CNY`` 时有意义。
        frequency: 时间粒度。
        missing_reason: 当 ``value is None`` 时必填，说明缺失原因。
    """

    value: float | None
    unit: Unit
    semantic: str
    as_of: date
    source: str
    currency: str | None = None
    frequency: Frequency = Frequency.POINT
    missing_reason: str | None = None

    # ---------- 构造 ----------

    def __post_init__(self) -> None:
        if self.value is None and not self.missing_reason:
            raise MissingValueError(
                f"缺失值必须说明原因（semantic={self.semantic!r}）。"
                "如果是因为数据源未覆盖，请写明；不要用 0 填充。"
            )
        if self.value is not None and self.missing_reason:
            raise ValueError(
                f"semantic={self.semantic!r} 既有数值又标了缺失原因，语义冲突。"
            )

    @classmethod
    def missing(
        cls,
        *,
        unit: Unit,
        semantic: str,
        as_of: date,
        source: str,
        reason: str,
        currency: str | None = None,
        frequency: Frequency = Frequency.POINT,
    ) -> TypedValue:
        """构造一个显式缺失值。缺失是一种合法状态，零值不是。"""
        return cls(
            value=None,
            unit=unit,
            semantic=semantic,
            as_of=as_of,
            source=source,
            currency=currency,
            frequency=frequency,
            missing_reason=reason,
        )

    # ---------- 状态 ----------

    @property
    def is_missing(self) -> bool:
        return self.value is None

    @property
    def has_currency(self) -> bool:
        return self.currency is not None

    # ---------- 校验 ----------

    def validate(self) -> list[ContractViolation]:
        """返回契约违反清单。空列表表示合规。"""
        v: list[ContractViolation] = []

        if not self.semantic or not self.semantic.strip():
            v.append(
                ContractViolation(
                    code="C001", field="semantic", message="语义标签为空，无法判断口径"
                )
            )
        if not self.source or not self.source.strip():
            v.append(
                ContractViolation(
                    code="C002",
                    field="source",
                    message="来源为空，数值不可追溯",
                )
            )
        if not isinstance(self.as_of, date):
            v.append(
                ContractViolation(
                    code="C003", field="as_of", message="时点字段非法，无法判断时效"
                )
            )
        if self.unit is Unit.CNY and self.currency is None:
            v.append(
                ContractViolation(
                    code="C004",
                    field="currency",
                    message="货币金额缺少币种，跨市场比较会出错",
                )
            )
        if (
            self.unit is Unit.CNY
            and self.currency is not None
            and self.currency.upper() not in {"CNY", "HKD", "USD", "EUR"}
        ):
            v.append(
                ContractViolation(
                    code="C005",
                    field="currency",
                    message=f"未知币种 {self.currency!r}",
                )
            )
        if (
            self.unit is Unit.PERCENT
            and self.value is not None
            and abs(self.value) > 1000
        ):
            v.append(
                ContractViolation(
                    code="C006",
                    field="value",
                    message=(
                        f"百分比取值 {self.value} 超出常见量级，"
                        "疑似把小数形式和百分数形式混用（0.898 vs 89.8）"
                    ),
                    severity=Severity.WARNING,
                )
            )
        # 占比类比值通常在 [0,1]；倍数类可超 1，用语义后缀区分
        if (
            self.unit is Unit.RATIO
            and self.value is not None
            and self.semantic.endswith("_share")
            and not 0.0 <= self.value <= 1.0
        ):
            v.append(
                ContractViolation(
                    code="C007",
                    field="value",
                    message=f"占比类数值 {self.value} 不在 [0,1] 区间",
                )
            )
        if self.frequency is Frequency.TTM and self.as_of.day != 1 and self.as_of.month != 12:
            v.append(
                ContractViolation(
                    code="C008",
                    field="frequency",
                    message="TTM 数值的时点通常应为月度/年度节点，当前时点可疑",
                    severity=Severity.WARNING,
                )
            )
        return v

    def is_valid(self) -> bool:
        return not [x for x in self.validate() if x.severity is Severity.ERROR]

    # ---------- 算术（带量纲传播） ----------

    def _guard_operand(self, other: TypedValue) -> None:
        if self.is_missing or other.is_missing:
            raise MissingValueError(
                f"缺失值不参与运算：{self.semantic!r}(missing={self.is_missing}) / "
                f"{other.semantic!r}(missing={other.is_missing})。"
                "请先在闸门层处理缺失，而不是用零值顶上。"
            )

    def add(self, other: TypedValue) -> TypedValue:
        """同量纲相加。量纲不同直接报错，不做事后解释。"""
        self._guard_operand(other)
        if self.unit is not other.unit:
            raise UnitMismatchError(
                f"量纲不一致：{self.semantic}={self.unit.value} 与 "
                f"{other.semantic}={other.unit.value} 不能相加"
            )
        if self.unit is Unit.CNY and self.currency != other.currency:
            raise UnitMismatchError(
                f"币种不一致：{self.currency} 与 {other.currency} 不能直接相加，请先换算"
            )
        return replace(
            self,
            value=(self.value or 0.0) + (other.value or 0.0),
            semantic=f"({self.semantic}+{other.semantic})",
            source=f"{self.source}|{other.source}",
            as_of=max(self.as_of, other.as_of),
        )

    def sub(self, other: TypedValue) -> TypedValue:
        self._guard_operand(other)
        if self.unit is not other.unit:
            raise UnitMismatchError(
                f"量纲不一致：{self.unit.value} 与 {other.unit.value} 不能相减"
            )
        return replace(
            self,
            value=(self.value or 0.0) - (other.value or 0.0),
            semantic=f"({self.semantic}-{other.semantic})",
            source=f"{self.source}|{other.source}",
            as_of=max(self.as_of, other.as_of),
        )

    def scale(self, factor: float) -> TypedValue:
        """乘以无量纲标量。"""
        if self.is_missing:
            raise MissingValueError(f"缺失值不参与缩放的：{self.semantic!r}")
        return replace(self, value=(self.value or 0.0) * factor)

    def over(self, other: TypedValue) -> TypedValue:
        """相除，结果量纲为 RATIO。"""
        self._guard_operand(other)
        if (other.value or 0.0) == 0:
            raise ZeroDivisionError(f"分母为零：{other.semantic!r}")
        return replace(
            self,
            value=(self.value or 0.0) / (other.value or 0.0),
            unit=Unit.RATIO,
            currency=None,
            semantic=f"({self.semantic}/{other.semantic})",
            source=f"{self.source}|{other.source}",
            as_of=max(self.as_of, other.as_of),
        )

    def to_percent(self) -> TypedValue:
        """RATIO → PERCENT。"""
        if self.unit is not Unit.RATIO:
            raise UnitMismatchError(f"只有 RATIO 可转 PERCENT，当前为 {self.unit.value}")
        if self.is_missing:
            raise MissingValueError(f"缺失值不可转换：{self.semantic!r}")
        return replace(self, value=(self.value or 0.0) * 100.0, unit=Unit.PERCENT)

    def to_currency(self, rate: float, target: str) -> TypedValue:
        """按给定汇率换币。汇率本身必须由调用方提供并留痕。"""
        if self.unit is not Unit.CNY:
            raise UnitMismatchError("只有货币金额可换汇")
        if self.is_missing:
            raise MissingValueError(f"缺失值不可换汇：{self.semantic!r}")
        return replace(
            self,
            value=(self.value or 0.0) * rate,
            currency=target.upper(),
            source=f"{self.source}|fx:{rate}",
        )

    # ---------- 展示 ----------

    def render(self) -> str:
        if self.is_missing:
            return f"{self.semantic}=MISSING({self.missing_reason})"
        cur = f" {self.currency}" if self.currency else ""
        return (
            f"{self.semantic}={self.value:,.4g}{cur} "
            f"[{self.unit.value}·{self.frequency.value}·as_of {self.as_of.isoformat()}·"
            f"src {self.source}]"
        )

    def __str__(self) -> str:  # pragma: no cover - 展示用
        return self.render()

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "unit": self.unit.value,
            "currency": self.currency,
            "frequency": self.frequency.value,
            "semantic": self.semantic,
            "as_of": self.as_of.isoformat(),
            "source": self.source,
            "missing_reason": self.missing_reason,
        }


def sum_values(values: Iterable[TypedValue], *, semantic: str | None = None) -> TypedValue:
    """对一组同量纲数值求和（例如分业务收入加总为总收入）。

    任意一项缺失即整体缺失 —— 不做「缺项按零计」这种会在报告里制造
    假精确的处理。
    """
    seq: Sequence[TypedValue] = list(values)
    if not seq:
        raise ValueError("空序列无法求和")

    missing = [v.semantic for v in seq if v.is_missing]
    if missing:
        head = seq[0]
        return TypedValue.missing(
            unit=head.unit,
            semantic=semantic or f"sum({head.semantic},...)",
            as_of=max(v.as_of for v in seq),
            source="|".join(sorted({v.source for v in seq})),
            reason=f"加总项中存在缺失：{', '.join(missing)}",
            currency=head.currency,
            frequency=head.frequency,
        )

    acc = seq[0]
    for nxt in seq[1:]:
        acc = acc.add(nxt)
    if semantic:
        acc = replace(acc, semantic=semantic)
    return acc
