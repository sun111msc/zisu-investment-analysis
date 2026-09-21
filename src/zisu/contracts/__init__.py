"""契约层：类型化数值 + 三态输出。

这一层不依赖任何其他内部模块，是纯基础设施。任何上层模块都可以引用它，
但它不反过来引用上层 —— 保持依赖单向。
"""

from zisu.contracts.state import (
    STATE_BANNER,
    OutputState,
    StateDeclaration,
    build_declaration,
    resolve_state,
)
from zisu.contracts.value import (
    ContractViolation,
    Frequency,
    MissingValueError,
    Severity,
    TypedValue,
    Unit,
    UnitMismatchError,
    sum_values,
)

__all__ = [
    "ContractViolation",
    "Frequency",
    "MissingValueError",
    "OutputState",
    "STATE_BANNER",
    "Severity",
    "StateDeclaration",
    "TypedValue",
    "Unit",
    "UnitMismatchError",
    "build_declaration",
    "resolve_state",
    "sum_values",
]
