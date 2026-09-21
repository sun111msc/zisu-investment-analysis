"""闸门引擎。

把「分析纪律」从提示词里的文字，变成可执行、可测试、可回归校验的代码。

三态结果：

- ``PASS`` —— 满足要求
- ``FAIL`` —— 不满足，且该闸门为阻断型时，整份报告降为 BLOCKED
- ``SKIP`` —— 前置条件不足（例如对应 Phase 未执行），不计入通过率分母

五阶段质控（按执行时点分组，降低一次性检查的认知负荷）：

1. 数据采集质量 —— 取数完成后
2. 分析深度质量 —— 各章节分析完成后
3. 逻辑一致性质量 —— 报告整合后
4. 格式与合规质量 —— 发布前
5. 投资判断质量 —— 最终决策前

设计取舍见 ``docs/engineering/adr/0003-fail-closed-registry.md`` 与
``docs/engineering/adr/0004-three-state-output.md``。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from zisu.contracts import (
    Severity,
    StateDeclaration,
    TypedValue,
    build_declaration,
)
from zisu.datasources.fallback import FetchAudit, FetchResult
from zisu.datasources.registry import CapabilityManifest, DataSourceRegistry

__all__ = [
    "GateStage",
    "GateStatus",
    "GateResult",
    "GateContext",
    "GateReport",
    "GateRule",
    "GateEngine",
]


class GateStage(str, Enum):
    DATA = "S1 数据采集质量"
    DEPTH = "S2 分析深度质量"
    LOGIC = "S3 逻辑一致性质量"
    FORMAT = "S4 格式与合规质量"
    JUDGMENT = "S5 投资判断质量"


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class GateResult:
    gate_id: str
    name: str
    stage: GateStage
    status: GateStatus
    blocking: bool = True
    detail: str = ""
    evidence: str = ""

    @property
    def ok(self) -> bool:
        return self.status is GateStatus.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "name": self.name,
            "stage": self.stage.value,
            "status": self.status.value,
            "blocking": self.blocking,
            "detail": self.detail,
        }


@dataclass
class GateContext:
    """闸门运行时上下文。所有规则只读，不修改。"""

    symbol: str
    values: dict[str, TypedValue] = field(default_factory=dict)
    fetch_results: dict[str, FetchResult] = field(default_factory=dict)
    manifest: CapabilityManifest | None = None
    registry: DataSourceRegistry | None = None
    manifest_issues: list[Any] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)

    # ---- 便捷读取 ----

    def value(self, semantic: str) -> TypedValue | None:
        return self.values.get(semantic)

    def num(self, semantic: str, default: float | None = None) -> float | None:
        v = self.values.get(semantic)
        if v is None or v.is_missing:
            return default
        return v.value

    def art(self, key: str, default: Any = None) -> Any:
        return self.artifacts.get(key, default)

    def has_art(self, key: str) -> bool:
        return key in self.artifacts

    def audit(self) -> list[FetchAudit]:
        out: list[FetchAudit] = []
        for r in self.fetch_results.values():
            out.extend(r.audit)
        return out

    def missing_semantics(self) -> list[str]:
        return [k for k, v in self.values.items() if v.is_missing]


GateRule = Callable[[GateContext], GateResult]


@dataclass
class GateReport:
    results: list[GateResult] = field(default_factory=list)

    # ---- 汇总 ----

    @property
    def failures(self) -> list[GateResult]:
        return [r for r in self.results if r.status is GateStatus.FAIL]

    @property
    def blockers(self) -> list[GateResult]:
        return [r for r in self.failures if r.blocking]

    @property
    def warnings(self) -> list[GateResult]:
        return [r for r in self.failures if not r.blocking]

    @property
    def passed(self) -> list[GateResult]:
        return [r for r in self.results if r.status is GateStatus.PASS]

    @property
    def executed(self) -> list[GateResult]:
        return [r for r in self.results if r.status is not GateStatus.SKIP]

    def pass_rate(self) -> float:
        denom = len(self.executed)
        return (len(self.passed) / denom) if denom else 1.0

    def summary(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.results:
            out[r.status.value] = out.get(r.status.value, 0) + 1
        return out

    def by_stage(self) -> dict[str, list[GateResult]]:
        grouped: dict[str, list[GateResult]] = {}
        for r in self.results:
            grouped.setdefault(r.stage.value, []).append(r)
        return grouped

    def to_declaration(self) -> StateDeclaration:
        return build_declaration(
            blockers=[f"{r.gate_id} {r.name}：{r.detail}" for r in self.blockers],
            warnings=[f"{r.gate_id} {r.name}：{r.detail}" for r in self.warnings],
            gate_summary=self.summary(),
        )

    def to_markdown(self) -> str:
        lines = ["## 闸门报告", ""]
        for stage, items in self.by_stage().items():
            lines.append(f"### {stage}")
            lines.append("")
            lines.append("| 闸门 | 名称 | 状态 | 说明 |")
            lines.append("|---|---|---|---|")
            for r in items:
                mark = {"PASS": "✅", "FAIL": "❌", "SKIP": "➖"}[r.status.value]
                lines.append(f"| {r.gate_id} | {r.name} | {mark} | {r.detail or '—'} |")
            lines.append("")
        lines.append(
            f"**通过率**：{len(self.passed)}/{len(self.executed)} "
            f"= {self.pass_rate():.1%}"
        )
        return "\n".join(lines)


class GateEngine:
    """闸门调度器。"""

    def __init__(self) -> None:
        self._rules: list[tuple[str, str, GateStage, bool, GateRule]] = []

    # ---- 注册 ----

    def register(
        self,
        gate_id: str,
        name: str,
        stage: GateStage,
        rule: GateRule,
        *,
        blocking: bool = True,
    ) -> GateEngine:
        if any(g[0] == gate_id for g in self._rules):
            raise ValueError(f"闸门编号 {gate_id!r} 重复")
        self._rules.append((gate_id, name, stage, blocking, rule))
        return self

    def register_all(self, rules: Iterable[tuple[str, str, GateStage, GateRule, bool]]) -> None:
        for gate_id, name, stage, rule, blocking in rules:
            self.register(gate_id, name, stage, rule, blocking=blocking)

    def rule_ids(self) -> list[str]:
        return [r[0] for r in self._rules]

    # ---- 执行 ----

    def run(
        self,
        ctx: GateContext,
        *,
        stages: Sequence[GateStage] | None = None,
        only: Sequence[str] | None = None,
    ) -> GateReport:
        report = GateReport()
        wanted = set(stages) if stages else None
        only_set = set(only) if only else None

        for gate_id, name, stage, blocking, rule in self._rules:
            if wanted and stage not in wanted:
                continue
            if only_set and gate_id not in only_set:
                continue
            try:
                result = rule(ctx)
                result.gate_id = gate_id
                result.name = name
                result.stage = stage
                result.blocking = blocking
            except GateSkipped as exc:
                result = GateResult(
                    gate_id=gate_id,
                    name=name,
                    stage=stage,
                    status=GateStatus.SKIP,
                    blocking=blocking,
                    detail=str(exc),
                )
            except Exception as exc:  # noqa: BLE001 - 规则异常按失败处理，绝不静默
                result = GateResult(
                    gate_id=gate_id,
                    name=name,
                    stage=stage,
                    status=GateStatus.FAIL,
                    blocking=True,
                    detail=f"闸门自身异常，按阻断处理：{exc!r}",
                )
            report.results.append(result)

        return report


class GateSkipped(Exception):
    """规则主动声明前置条件不足。"""


# --------------------------------------------------------------------------
# 规则编写辅助
# --------------------------------------------------------------------------


def ok(detail: str = "", evidence: str = "") -> GateResult:
    return GateResult("", "", GateStage.DATA, GateStatus.PASS, detail=detail, evidence=evidence)


def fail(detail: str, evidence: str = "") -> GateResult:
    return GateResult("", "", GateStage.DATA, GateStatus.FAIL, detail=detail, evidence=evidence)


def skip(reason: str) -> GateResult:
    return GateResult("", "", GateStage.DATA, GateStatus.SKIP, detail=reason)


def require_art(ctx: GateContext, key: str) -> Any:
    """取产物；不存在则跳过该闸门（说明对应 Phase 尚未执行）。"""
    if not ctx.has_art(key):
        raise GateSkipped(f"缺少产物 {key!r}，对应阶段未执行")
    return ctx.art(key)


def contract_violations(values: Iterable[TypedValue]) -> list[str]:
    out: list[str] = []
    for v in values:
        for issue in v.validate():
            if issue.severity is Severity.ERROR:
                out.append(f"{v.semantic}: {issue.code} {issue.message}")
    return out
