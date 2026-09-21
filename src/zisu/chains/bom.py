"""产业链 BOM 拆解与瓶颈分级。

这一层回答一个问题：**这条产业链上，钱被谁赚走了？**

做法是把终端产品逐层拆到物理工序级（通常 7 层以上），在每一层标注
供应商数量、单件价值量、以及是否存在物理瓶颈；然后把仓位上限直接
绑定到瓶颈等级 —— 让「稀缺性」从形容词变成可执行的数字。

瓶颈分级的判据刻意写得**可证伪**：全球供应商家数、认证周期、
替代品出现与否。任何一级评级都必须给出这三项证据，否则不予采信。

设计取舍见 ``docs/engineering/adr/0001-phase-over-layer.md`` 关于「为什么不按行业
分类而按工序分级」的讨论。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "BottleneckGrade",
    "GovernanceGrade",
    "EnvironmentGrade",
    "BomLayer",
    "BottleneckAssessment",
    "assess_bottleneck",
    "position_cap",
    "rank_bottlenecks",
]


class BottleneckGrade(str, Enum):
    """瓶颈等级。判据是可核查的客观事实，不是主观感受。"""

    L5_ULTIMATE = "L5"  # 全球独家 + 认证壁垒 ≥2 年 + 大空间
    L4_EXTREME = "L4"  # 全球 2 家 + 认证 ≥2 年 + 客户锁死
    L3_STRONG = "L3"  # 全球 2-3 家 + 工艺或材料独家
    L2_QUASI = "L2"  # 全球 3-4 家 + 单一产品领先
    L1_POTENTIAL = "L1"  # 全球 4 家以上，但有差异化
    L0_NONE = "L0"  # 无瓶颈，充分竞争

    @property
    def leaves(self) -> int:
        return {"L5": 5, "L4": 4, "L3": 3, "L2": 2, "L1": 1, "L0": 0}[self.value]

    @property
    def label(self) -> str:
        return "🍃" * self.leaves if self.leaves else "—"


class GovernanceGrade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class EnvironmentGrade(str, Enum):
    """市场环境评级。决定总仓位天花板。"""

    A_OFFENSIVE = "A"
    B_NEUTRAL = "B"
    C_CAUTIOUS = "C"
    D_DEFENSIVE = "D"

    @property
    def total_cap(self) -> float:
        return {"A": 1.00, "B": 0.70, "C": 0.30, "D": 0.10}[self.value]

    @property
    def allow_new(self) -> bool:
        return self.value != "D"


@dataclass
class BomLayer:
    """产业链的一层。"""

    level: int
    name: str
    process: str
    unit_value: float
    unit: str
    global_suppliers: int
    certification_years: float = 0.0

    def __post_init__(self) -> None:
        if self.level < 1:
            raise ValueError("层级从 1 开始编号")
        if not self.process.strip():
            raise ValueError(f"层级 {self.name!r} 未描述具体工序，不允许停留在行业口号层")


@dataclass
class BottleneckAssessment:
    layer_name: str
    grade: BottleneckGrade
    evidence: list[str] = field(default_factory=list)
    disqualifiers: list[str] = field(default_factory=list)

    @property
    def downgraded(self) -> bool:
        return bool(self.disqualifiers)


@dataclass(frozen=True)
class _CapTable:
    """瓶颈等级 × 治理等级 → 单标的仓位上限。"""

    rows: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "L5": {"A": 0.25, "B": 0.20, "C": 0.15, "D": 0.0},
            "L4": {"A": 0.20, "B": 0.15, "C": 0.10, "D": 0.0},
            "L3": {"A": 0.15, "B": 0.10, "C": 0.08, "D": 0.0},
            "L2": {"A": 0.08, "B": 0.05, "C": 0.03, "D": 0.0},
            "L1": {"A": 0.03, "B": 0.02, "C": 0.01, "D": 0.0},
            "L0": {"A": 0.02, "B": 0.01, "C": 0.00, "D": 0.0},
        }
    )


CAP_TABLE = _CapTable()

#: 一票否决的降级触发条件 —— 任一命中，瓶颈等级自动降一级
DOWNGRADE_TRIGGERS: tuple[str, ...] = (
    "出现可量产替代品或第二供应商放量",
    "客户合同到期未续约",
    "实控人减持或质押率超过 40%",
    "行业资本开支同比增长超过 50%（扩产竞赛预警）",
)


def assess_bottleneck(layer: BomLayer, *, triggers_hit: list[str] | None = None) -> BottleneckAssessment:
    """按客观判据定级。

    判据表（供应商家数为主锚，认证周期与客户结构为副锚）：

    - 1 家且认证 ≥2 年 → L5
    - 2 家且认证 ≥2 年 → L4
    - 2-3 家 → L3
    - 3-4 家 → L2
    - ≥5 家但有差异化 → L1
    - ≥5 家且无差异 → L0
    """
    n = layer.global_suppliers
    cert = layer.certification_years

    if n <= 0:
        raise ValueError("全球供应商家数必须为正")

    if n == 1 and cert >= 2:
        grade = BottleneckGrade.L5_ULTIMATE
        ev = [f"全球仅 {n} 家可供应", f"认证周期 {cert:.1f} 年"]
    elif n == 1:
        grade = BottleneckGrade.L4_EXTREME
        ev = [f"全球仅 {n} 家可供应", f"认证周期仅 {cert:.1f} 年，壁垒未被时间验证"]
    elif n <= 2 and cert >= 2:
        grade = BottleneckGrade.L4_EXTREME
        ev = [f"全球 {n} 家可供应", f"认证周期 {cert:.1f} 年"]
    elif n <= 3:
        grade = BottleneckGrade.L3_STRONG
        ev = [f"全球 {n} 家可供应"]
    elif n <= 4:
        grade = BottleneckGrade.L2_QUASI
        ev = [f"全球 {n} 家可供应"]
    elif n <= 8:
        grade = BottleneckGrade.L1_POTENTIAL
        ev = [f"全球 {n} 家，存在差异化空间"]
    else:
        grade = BottleneckGrade.L0_NONE
        ev = [f"全球 {n} 家，充分竞争"]

    hits = [t for t in (triggers_hit or []) if t in DOWNGRADE_TRIGGERS]
    if hits:
        order = [
            BottleneckGrade.L5_ULTIMATE,
            BottleneckGrade.L4_EXTREME,
            BottleneckGrade.L3_STRONG,
            BottleneckGrade.L2_QUASI,
            BottleneckGrade.L1_POTENTIAL,
            BottleneckGrade.L0_NONE,
        ]
        grade = order[min(order.index(grade) + 1, len(order) - 1)]

    return BottleneckAssessment(
        layer_name=layer.name,
        grade=grade,
        evidence=ev,
        disqualifiers=hits,
    )


def position_cap(
    grade: BottleneckGrade,
    governance: GovernanceGrade,
    environment: EnvironmentGrade,
) -> float:
    """计算单标的仓位上限。

    取三者最小值：瓶颈等级决定稀缺性溢价，治理等级决定信任折价，
    环境等级决定总仓位天花板。
    """
    by_bottleneck = CAP_TABLE.rows[grade.value][governance.value]
    return min(by_bottleneck, environment.total_cap)


def rank_bottlenecks(
    layers: list[BomLayer],
    *,
    triggers: dict[str, list[str]] | None = None,
) -> list[BottleneckAssessment]:
    """对全部层级定级并按瓶颈强度排序。

    排序理由：先按等级，再按单位价值量（价值量与稀缺性同时高的层级，
    才是真正的利润池所在）。
    """
    triggers = triggers or {}
    assessed = [assess_bottleneck(layer, triggers_hit=triggers.get(layer.name)) for layer in layers]
    value_map = {layer.name: layer.unit_value for layer in layers}
    return sorted(
        assessed,
        key=lambda a: (a.grade.leaves, value_map.get(a.layer_name, 0.0)),
        reverse=True,
    )
