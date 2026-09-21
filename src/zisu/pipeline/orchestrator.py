"""流水线编排器。

编排器的职责边界很窄但很关键：

1. 按序执行阶段，检查产物依赖；
2. 在正确的时点调用闸门 —— 分两轮，因为「状态声明」本身是一道闸门，
   而它又依赖闸门结果，需要先算出中间状态再定稿；
3. 产出唯一一份带状态的报告结果。

**编排器不修改阶段产物，也不给结论。** 它只决定「能不能发」。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from zisu.contracts import StateDeclaration
from zisu.gates import GateEngine, GateReport, GateStage, build_engine
from zisu.pipeline.base import Phase, PhaseResult, PhaseStatus, PipelineContext
from zisu.pipeline.phases import default_phases

__all__ = ["PipelineRun", "Pipeline"]


@dataclass
class PipelineRun:
    symbol: str
    phase_results: list[PhaseResult] = field(default_factory=list)
    gate_report: GateReport = field(default_factory=GateReport)
    declaration: StateDeclaration | None = None
    ctx: PipelineContext | None = None

    # ---- 便捷属性 ----

    @property
    def state(self) -> str:
        return self.declaration.state.value if self.declaration else "UNKNOWN"

    @property
    def can_emit_conclusion(self) -> bool:
        return bool(self.declaration and self.declaration.can_emit_conclusion)

    def phase(self, phase_id: str) -> PhaseResult | None:
        return next((p for p in self.phase_results if p.phase_id == phase_id), None)

    def all_notes(self) -> list[str]:
        out: list[str] = []
        for p in self.phase_results:
            out.extend(f"[{p.phase_id}] {n}" for n in p.notes)
        return out

    # ---- 输出 ----

    def to_markdown(self) -> str:
        parts: list[str] = []
        if self.declaration:
            parts.append(self.declaration.to_markdown())
            parts.append("")

        parts.append("## 阶段执行")
        parts.append("")
        parts.append("| 阶段 | 名称 | 状态 | 说明 |")
        parts.append("|---|---|---|---|")
        mark = {"OK": "✅", "SKIPPED": "➖", "BLOCKED": "⛔"}
        for p in self.phase_results:
            note = "；".join(p.notes[:2]) or "—"
            parts.append(f"| {p.phase_id} | {p.name} | {mark[p.status.value]} | {note} |")
        parts.append("")

        if self.ctx:
            body = self.ctx.get("report.markdown")
            if self.can_emit_conclusion and body:
                parts.append(body)
                parts.append("")

        parts.append(self.gate_report.to_markdown())
        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "state": self.state,
            "phases": [
                {"phase_id": p.phase_id, "name": p.name, "status": p.status.value, "notes": p.notes}
                for p in self.phase_results
            ],
            "gates": [r.to_dict() for r in self.gate_report.results],
            "gate_summary": self.gate_report.summary(),
            "pass_rate": round(self.gate_report.pass_rate(), 4),
            "declaration": {
                "state": self.declaration.state.value,
                "blockers": self.declaration.blockers,
                "warnings": self.declaration.warnings,
            }
            if self.declaration
            else None,
            "trace": self.ctx.tracer.to_dict() if self.ctx else None,
        }


class Pipeline:
    """八阶段流水线。"""

    def __init__(
        self,
        phases: Sequence[Phase] | None = None,
        engine: GateEngine | None = None,
    ) -> None:
        self.phases: list[Phase] = list(phases) if phases else default_phases()
        self.engine = engine or build_engine()

    # ---- 主流程 ----

    def run(self, ctx: PipelineContext) -> PipelineRun:
        run = PipelineRun(symbol=ctx.symbol, ctx=ctx)

        # 0) 编译期门禁：先核验能力清单，再动笔
        if ctx.manifest is not None and ctx.registry is not None:
            ctx.manifest_issues = ctx.registry.verify_manifest(ctx.manifest)

        # 1) 执行阶段
        for phase in self.phases:
            with ctx.tracer.span(f"{phase.phase_id} {phase.name}"):
                result = phase.run(ctx)
            run.phase_results.append(result)
            for note in result.notes:
                ctx.tracer.note(f"{phase.phase_id}", note)

        # 2) 第一轮闸门：数据 / 深度 / 逻辑
        first = self.engine.run(
            ctx.to_gate_context(),
            stages=[GateStage.DATA, GateStage.DEPTH, GateStage.LOGIC],
        )
        self._trace_gates(ctx, first)

        # 3) 中间状态声明 —— 供格式阶段的门禁检查
        ctx.put("report.declaration", first.to_declaration())

        # 4) 第二轮闸门：格式 / 判断
        second = self.engine.run(
            ctx.to_gate_context(),
            stages=[GateStage.FORMAT, GateStage.JUDGMENT],
        )
        self._trace_gates(ctx, second)

        # 5) 合并并定稿
        merged = GateReport(results=first.results + second.results)
        declaration = merged.to_declaration()
        ctx.put("report.declaration", declaration)

        run.gate_report = merged
        run.declaration = declaration
        return run

    # ---- 内部 ----

    @staticmethod
    def _trace_gates(ctx: PipelineContext, report: GateReport) -> None:
        for r in report.results:
            ctx.tracer.gate(r.gate_id, r.name, r.status.value, r.detail)

    # ---- 断点重跑 ----

    def run_from(
        self,
        ctx: PipelineContext,
        phase_id: str,
    ) -> PipelineRun:
        """从指定阶段开始重跑（用于局部修正后避免全量重算）。"""
        ids = [p.phase_id for p in self.phases]
        if phase_id not in ids:
            raise ValueError(f"未知阶段 {phase_id!r}，可用：{ids}")
        start = ids.index(phase_id)
        sub = Pipeline(phases=self.phases[start:], engine=self.engine)
        run = sub.run(ctx)

        # 把已跳过的阶段补到列表头部，保持输出结构一致
        reused = [
            PhaseResult(
                phase_id=phase.phase_id,
                name=phase.name,
                status=PhaseStatus.SKIPPED,
                notes=["复用既有产物，未重跑"],
            )
            for phase in self.phases[:start]
        ]
        run.phase_results = reused + run.phase_results
        return run
