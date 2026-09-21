"""评测指标计算。

指标的设计原则：**每一项都必须能被反例推翻。**
「系统很稳健」不是指标；「六类注入全部被拦截」才是。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = ["EvalResult", "EvalSummary", "evaluate", "summarize"]


@dataclass
class EvalResult:
    name: str
    kind: str  # baseline | injection
    expected_state: str
    actual_state: str
    pass_rate: float
    gate_hits: list[str] = field(default_factory=list)
    gate_misses: list[str] = field(default_factory=list)
    unexpected_failures: list[str] = field(default_factory=list)
    blocker_count: int = 0
    note: str = ""

    @property
    def state_correct(self) -> bool:
        return self.expected_state == self.actual_state

    @property
    def gate_agreement(self) -> float:
        total = len(self.gate_hits) + len(self.gate_misses)
        return (len(self.gate_hits) / total) if total else 1.0

    @property
    def caught(self) -> bool:
        """注入型样本：被拦截（BLOCKED）且命中预期闸门，才算成功捕获。"""
        if self.kind != "baseline":
            return self.actual_state == "BLOCKED" and not self.gate_misses
        return self.state_correct and not self.gate_misses

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "expected_state": self.expected_state,
            "actual_state": self.actual_state,
            "state_correct": self.state_correct,
            "pass_rate": round(self.pass_rate, 4),
            "gate_agreement": round(self.gate_agreement, 4),
            "caught": self.caught,
            "gate_misses": self.gate_misses,
            "unexpected_failures": self.unexpected_failures,
            "blockers": self.blocker_count,
        }


@dataclass
class EvalSummary:
    results: list[EvalResult] = field(default_factory=list)

    # ---- 单项指标 ----

    def state_accuracy(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.state_correct) / len(self.results)

    def gate_agreement(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.gate_agreement for r in self.results) / len(self.results)

    def hallucination_catch_rate(self) -> float:
        """注入型样本的捕获率。无注入样本时返回 0 而不是 1 —— 不虚报。"""
        injections = [r for r in self.results if r.kind == "injection"]
        if not injections:
            return 0.0
        return sum(1 for r in injections if r.caught) / len(injections)

    def mean_pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.pass_rate for r in self.results) / len(self.results)

    def baseline_integrity(self) -> float:
        """基线样本未出现意外失败的比例。"""
        baselines = [r for r in self.results if r.kind == "baseline"]
        if not baselines:
            return 0.0
        ok = sum(1 for r in baselines if not r.unexpected_failures)
        return ok / len(baselines)

    # ---- 汇总与门禁 ----

    def metrics(self) -> dict[str, float]:
        return {
            "state_accuracy": round(self.state_accuracy(), 4),
            "gate_agreement": round(self.gate_agreement(), 4),
            "hallucination_catch_rate": round(self.hallucination_catch_rate(), 4),
            "mean_pass_rate": round(self.mean_pass_rate(), 4),
            "baseline_integrity": round(self.baseline_integrity(), 4),
        }

    def compare(self, baseline: dict[str, float], tolerance: float = 0.0) -> list[str]:
        """与基线比较，返回劣化项清单。空列表 = 未劣化。"""
        out: list[str] = []
        for key, current in self.metrics().items():
            expected = baseline.get(key)
            if expected is None:
                continue
            if current + tolerance < expected:
                out.append(f"{key}: {current:.4f} < 基线 {expected:.4f}")
        return out

    def to_markdown(self, baseline: dict[str, float] | None = None) -> str:
        m = self.metrics()
        lines = ["## 评测指标", ""]
        lines.append("| 指标 | 数值 |" + (" 基线 |" if baseline else ""))
        lines.append("|---|---|" + ("---|" if baseline else ""))
        for k, v in m.items():
            if baseline:
                b = baseline.get(k)
                delta = f"{v - b:+.4f}" if b is not None else "—"
                lines.append(f"| {k} | {v:.4f} | {b if b is not None else '—'}（{delta}） |")
            else:
                lines.append(f"| {k} | {v:.4f} |")
        lines.append("")

        lines.append("## 逐样本结果")
        lines.append("")
        lines.append("| 样本 | 类型 | 预期 | 实际 | 闸门一致 | 通过率 | 结论 |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in self.results:
            mark = "✅" if r.caught else "❌"
            lines.append(
                f"| {r.name} | {r.kind} | {r.expected_state} | {r.actual_state} | "
                f"{r.gate_agreement:.0%} | {r.pass_rate:.0%} | {mark} |"
            )
        lines.append("")

        misses = [(r.name, r.gate_misses) for r in self.results if r.gate_misses]
        if misses:
            lines.append("## 未命中的期望")
            lines.append("")
            for name, gates in misses:
                lines.append(f"- **{name}**：{', '.join(gates)}")
            lines.append("")
        return "\n".join(lines)


def evaluate(
    name: str,
    expected: dict[str, Any],
    run,
    *,
    kind: str = "baseline",
) -> EvalResult:
    """把一次流水线运行与预期比对，产出一条评测结果。"""
    status = {r.gate_id: r.status.value for r in run.gate_report.results}

    hits: list[str] = []
    misses: list[str] = []

    for gate in expected.get("must_pass", []):
        (hits if status.get(gate) == "PASS" else misses).append(gate)
    for gate in expected.get("must_fail", []):
        (hits if status.get(gate) == "FAIL" else misses).append(gate)

    unexpected = [r.gate_id for r in run.gate_report.blockers]
    if kind == "baseline" and expected.get("state") == "PASS":
        # 基线样本不应有阻断，则任何阻断都是意外
        unexpected = [r.gate_id for r in run.gate_report.blockers]
    else:
        unexpected = []

    return EvalResult(
        name=name,
        kind=kind,
        expected_state=str(expected.get("state", "?")),
        actual_state=run.state,
        pass_rate=run.gate_report.pass_rate(),
        gate_hits=hits,
        gate_misses=misses,
        unexpected_failures=unexpected,
        blocker_count=len(run.gate_report.blockers),
    )


def summarize(results: Iterable[EvalResult]) -> EvalSummary:
    return EvalSummary(results=list(results))


def load_baseline(path) -> dict[str, float]:
    import json
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("metrics", {})


def save_baseline(path, metrics: Sequence[tuple[str, float]] | dict[str, float]) -> None:
    import json
    from pathlib import Path

    data = dict(metrics) if not isinstance(metrics, dict) else metrics
    Path(path).write_text(
        json.dumps({"metrics": data}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
