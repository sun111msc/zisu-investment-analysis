"""可观测性：执行轨迹与用量统计。

Agent 系统最难排查的问题不是「报错」，而是「没报错但结果不对」。
因此每次分析都必须留下轨迹：哪个阶段跑了多久、哪些闸门被触发、
取数走了哪一级源、有没有降级。

轨迹是**可归档的普通数据结构**，不依赖任何外部追踪服务 ——
这样 CI 里可以断言、报告里可以附上、issue 里可以粘贴。
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = ["TraceEvent", "Tracer"]


@dataclass
class TraceEvent:
    kind: str  # phase_start / phase_end / gate / fetch / note
    name: str
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_ms: float | None = None
    detail: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Tracer:
    """轻量执行轨迹收集器。"""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []
        self._open: dict[str, float] = {}

    # ---- 记录 ----

    def note(self, name: str, detail: str = "", **payload: Any) -> None:
        self.events.append(TraceEvent(kind="note", name=name, detail=detail, payload=payload))

    def gate(self, gate_id: str, name: str, status: str, detail: str = "") -> None:
        self.events.append(
            TraceEvent(
                kind="gate",
                name=f"{gate_id} {name}",
                detail=detail,
                payload={"status": status},
            )
        )

    def fetch(self, semantic: str, source_id: str, outcome: str, detail: str = "") -> None:
        self.events.append(
            TraceEvent(
                kind="fetch",
                name=semantic,
                detail=detail,
                payload={"source": source_id, "outcome": outcome},
            )
        )

    # ---- 计时 ----

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        self.events.append(TraceEvent(kind="phase_start", name=name))
        try:
            yield
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            self.events.append(
                TraceEvent(kind="phase_end", name=name, duration_ms=round(elapsed, 3))
            )

    # ---- 汇总 ----

    def phase_timings(self) -> dict[str, float]:
        return {
            e.name: e.duration_ms or 0.0
            for e in self.events
            if e.kind == "phase_end"
        }

    def total_ms(self) -> float:
        return round(sum(self.phase_timings().values()), 3)

    def gates_by_status(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.events:
            if e.kind == "gate":
                s = str(e.payload.get("status", "?"))
                out[s] = out.get(s, 0) + 1
        return out

    def fetch_outcomes(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.events:
            if e.kind == "fetch":
                s = str(e.payload.get("outcome", "?"))
                out[s] = out.get(s, 0) + 1
        return out

    def to_markdown(self) -> str:
        lines = ["## 执行轨迹", ""]
        timings = self.phase_timings()
        if timings:
            lines.append("| 阶段 | 耗时 (ms) |")
            lines.append("|---|---|")
            for name, ms in timings.items():
                lines.append(f"| {name} | {ms:,.1f} |")
            lines.append(f"| **合计** | **{self.total_ms():,.1f}** |")
            lines.append("")

        gw = self.gates_by_status()
        if gw:
            lines.append(f"**闸门**：{', '.join(f'{k}×{v}' for k, v in sorted(gw.items()))}")
        fw = self.fetch_outcomes()
        if fw:
            lines.append(f"**取数**：{', '.join(f'{k}×{v}' for k, v in sorted(fw.items()))}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [e.to_dict() for e in self.events],
            "phase_timings_ms": self.phase_timings(),
            "total_ms": self.total_ms(),
            "gates": self.gates_by_status(),
            "fetch": self.fetch_outcomes(),
        }
