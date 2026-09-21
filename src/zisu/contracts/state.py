"""三态输出门禁（Three-State Output Gate）。

传统的成功/失败二态无法描述 LLM 分析中的真实情况：多数时候系统**能跑完**，
但**不够格被称为完成**。二态会强迫在「假装通过」和「整份丢弃」之间二选一，
两者都很糟。

三态的定义：

- ``PASS`` —— 全部门禁通过，报告可作为正式结论输出。
- ``DRAFT_REVIEW`` —— 存在未达标准的项（例如数据时效超期、某项缺失、
  单位疑似混用），报告可以输出，但**必须**带状态声明，使用者应人工复核。
- ``BLOCKED`` —— 存在致命项（未登记数据源、契约违反、关键数据缺失、
  估值反解不收敛）。**禁止输出结论**，只输出阻断原因清单。

核心规则：**缺失数据禁止用零值填充**。缺失是一种必须被显式传播的状态，
而不是可以被抹平的空洞。

设计取舍见 ``docs/engineering/adr/0004-three-state-output.md``。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

__all__ = ["OutputState", "StateDeclaration", "resolve_state", "STATE_BANNER"]


class OutputState(str, Enum):
    PASS = "PASS"
    DRAFT_REVIEW = "DRAFT_REVIEW"
    BLOCKED = "BLOCKED"


STATE_BANNER: dict[OutputState, str] = {
    OutputState.PASS: "✅ 状态声明：PASS —— 闸门全通过，本报告可作为正式结论使用。",
    OutputState.DRAFT_REVIEW: (
        "⚠️ 状态声明：DRAFT_REVIEW —— 存在未达标项，本报告仅供内部复核，"
        "不得作为对外结论。请人工确认下方清单。"
    ),
    OutputState.BLOCKED: (
        "⛔ 状态声明：BLOCKED —— 存在致命项，本报告**未产生结论**。"
        "下方仅列出阻断原因，不包含任何估值或操作建议。"
    ),
}


@dataclass
class StateDeclaration:
    """一条可追溯的状态声明。每个分析产出物都必须携带。"""

    state: OutputState
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    gate_summary: dict[str, int] = field(default_factory=dict)
    decided_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def banner(self) -> str:
        return STATE_BANNER[self.state]

    @property
    def can_emit_conclusion(self) -> bool:
        """只有非 BLOCKED 才允许输出结论段。"""
        return self.state is not OutputState.BLOCKED

    def to_markdown(self) -> str:
        lines = [f"> {self.banner}", ""]
        if self.blockers:
            lines.append("**阻断项（必须修复）**")
            lines.extend(f"- {b}" for b in self.blockers)
            lines.append("")
        if self.warnings:
            lines.append("**未达标项（需人工复核）**")
            lines.extend(f"- {w}" for w in self.warnings)
            lines.append("")
        if self.gate_summary:
            total = sum(self.gate_summary.values())
            passed = self.gate_summary.get("PASS", 0)
            lines.append(f"**门禁统计**：{passed}/{total} 通过")
            for k, n in sorted(self.gate_summary.items()):
                lines.append(f"- {k}: {n}")
        lines.append("")
        lines.append(f"_状态判定时间：{self.decided_at.isoformat()}_")
        return "\n".join(lines)


def resolve_state(
    blockers: Sequence[str],
    warnings: Sequence[str],
) -> OutputState:
    """由阻断项与非阻断项推导最终状态。阻断优先级最高。"""
    if blockers:
        return OutputState.BLOCKED
    if warnings:
        return OutputState.DRAFT_REVIEW
    return OutputState.PASS


def build_declaration(
    blockers: Sequence[str],
    warnings: Sequence[str],
    gate_summary: dict[str, int] | None = None,
) -> StateDeclaration:
    """构造状态声明。"""
    b = list(blockers)
    w = list(warnings)
    return StateDeclaration(
        state=resolve_state(b, w),
        blockers=b,
        warnings=w,
        gate_summary=dict(gate_summary or {}),
    )
