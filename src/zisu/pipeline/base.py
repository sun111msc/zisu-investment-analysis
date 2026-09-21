"""流水线基础设施：阶段协议与共享上下文。

设计要点：**阶段是纯函数式的**。

每个阶段声明自己需要什么（``requires``）、产出什么（``provides``），
输入输出都是普通的字典结构。这样做的好处：

1. 阶段之间没有隐式耦合，任何一个阶段都可以单测；
2. 缺产物时编排器能立刻发现，而不是等跑到后面才发现数据没了；
3. 阶段可以单独重跑，不需要重跑整条链。

阶段只负责**确定性部分**：结构校验、量化计算、契约装配。
需要生成自然语言的部分由上层 Agent 填充到已被严格定义的槽位里 ——
框架管纪律，模型管表达，两者不混。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from zisu.contracts import TypedValue
from zisu.datasources.fallback import FallbackChain, FetchResult
from zisu.datasources.registry import CapabilityManifest, DataSourceRegistry
from zisu.gates.engine import GateContext
from zisu.observability.audit import Tracer

__all__ = ["PhaseStatus", "PhaseResult", "PipelineContext", "Phase"]


class PhaseStatus(str, Enum):
    OK = "OK"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"


@dataclass
class PhaseResult:
    phase_id: str
    name: str
    status: PhaseStatus = PhaseStatus.OK
    artifacts: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status is PhaseStatus.OK


@dataclass
class PipelineContext:
    """贯穿全流程的共享状态。

    约定：阶段**只通过 ``artifacts`` 通信**，不互相引用对象。
    所有数值必须来自 ``values``（已通过契约校验）。
    """

    symbol: str
    values: dict[str, TypedValue] = field(default_factory=dict)
    fetch_results: dict[str, FetchResult] = field(default_factory=dict)
    registry: DataSourceRegistry | None = None
    manifest: CapabilityManifest | None = None
    chain: FallbackChain | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    tracer: Tracer = field(default_factory=Tracer)
    manifest_issues: list[Any] = field(default_factory=list)

    # ---- 数值 ----

    def num(self, semantic: str, default: float | None = None) -> float | None:
        v = self.values.get(semantic)
        if v is None or v.is_missing:
            return default
        return v.value

    def value(self, semantic: str) -> TypedValue | None:
        return self.values.get(semantic)

    def require(self, *semantics: str) -> list[str]:
        """返回缺失的语义清单。"""
        return [
            s for s in semantics if s not in self.values or self.values[s].is_missing
        ]

    # ---- 产物 ----

    def put(self, key: str, value: Any) -> None:
        self.artifacts[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.artifacts.get(key, default)

    def has(self, key: str) -> bool:
        return key in self.artifacts

    # ---- 桥接闸门 ----

    def to_gate_context(self) -> GateContext:
        return GateContext(
            symbol=self.symbol,
            values=self.values,
            fetch_results=self.fetch_results,
            manifest=self.manifest,
            registry=self.registry,
            manifest_issues=list(self.manifest_issues),
            artifacts=self.artifacts,
        )


class Phase(ABC):
    """阶段基类。"""

    phase_id: str = "P?"
    name: str = "unnamed"

    #: 依赖的 artifact 键。缺失时该阶段被标记为 SKIPPED 而非崩溃
    requires: tuple[str, ...] = ()

    #: 产出的 artifact 键
    provides: tuple[str, ...] = ()

    @abstractmethod
    def run(self, ctx: PipelineContext) -> PhaseResult:
        """执行阶段。实现中不应抛异常 —— 无法完成时返回 SKIPPED/BLOCKED。"""

    # ---- 辅助 ----

    def missing_requires(self, ctx: PipelineContext) -> list[str]:
        return [k for k in self.requires if not ctx.has(k)]

    def blocked(self, ctx: PipelineContext, reason: str) -> PhaseResult:
        ctx.tracer.note(f"{self.phase_id} 阻断", reason)
        return PhaseResult(
            phase_id=self.phase_id,
            name=self.name,
            status=PhaseStatus.BLOCKED,
            notes=[reason],
        )

    def skipped(self, ctx: PipelineContext, reason: str) -> PhaseResult:
        ctx.tracer.note(f"{self.phase_id} 跳过", reason)
        return PhaseResult(
            phase_id=self.phase_id,
            name=self.name,
            status=PhaseStatus.SKIPPED,
            notes=[reason],
        )
