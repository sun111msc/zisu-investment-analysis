"""分析场景文件（case file）的加载与上下文装配。

把「一次分析需要哪些输入」变成一个显式的、可版本管理的 JSON 文件，
而不是散落在代码里的字面量。评测样本（``examples/cases/``）就是一组 case file。

这带来的直接好处：**一个新样本 = 一个新 JSON**，不需要写代码，
因此评测集可以被非工程角色扩充。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from zisu.contracts import TypedValue
from zisu.datasources import (
    CapabilityManifest,
    DataSourceRegistry,
    FallbackChain,
    StaticDataSource,
    build_registry,
)
from zisu.pipeline import PipelineContext

__all__ = ["CaseFile", "load_case", "build_context", "ExampleDataError"]


class ExampleDataError(ValueError):
    """示例数据本身有问题。"""


@dataclass
class CaseFile:
    symbol: str
    title: str = ""
    description: str = ""
    sources: dict[str, list[str]] = field(default_factory=dict)
    records: dict[str, dict[str, list[Any]]] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    expect: dict[str, Any] = field(default_factory=dict)

    @property
    def manifest(self) -> CapabilityManifest:
        m = CapabilityManifest(symbol=self.symbol)
        for source_id, semantics in self.sources.items():
            m.declare(source_id, set(semantics))
        return m

    def build_adapters(self) -> dict[str, StaticDataSource]:
        out: dict[str, StaticDataSource] = {}
        for source_id, semantics in self.sources.items():
            ds = StaticDataSource(source_id=source_id, semantics=frozenset(semantics))
            for key, triple in (self.records.get(source_id) or {}).items():
                semantic, _, symbol = key.partition("|")
                value, as_of, *rest = triple
                currency = rest[0] if rest else None
                ds.put(semantic, symbol or self.symbol, float(value), _parse_date(as_of), currency)
            out[source_id] = ds
        return out


def _parse_date(raw: Any) -> date:
    """解析时点。支持 ISO 日期，以及特殊占位符 ``TODAY``。

    ``TODAY`` 的存在是为了让评测集不随时间漂移 ——
    否则时效性闸门会在几个月后把样本从 PASS 变成 DRAFT_REVIEW，
    造成评测基线无故波动。
    """
    if isinstance(raw, date):
        return raw
    text = str(raw).strip()
    if text.upper() == "TODAY":
        return date.today()
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ExampleDataError(
            f"时点格式必须是 ISO 日期（YYYY-MM-DD）或 TODAY，收到 {raw!r}"
        ) from exc


def load_case(path: str | Path) -> CaseFile:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"找不到场景文件：{p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    if "symbol" not in raw:
        raise ExampleDataError("场景文件缺少 symbol 字段")

    return CaseFile(
        symbol=raw["symbol"],
        title=raw.get("title", ""),
        description=raw.get("description", ""),
        sources=raw.get("sources", {}),
        records=raw.get("records", {}),
        meta=raw.get("meta", {}),
        expect=raw.get("expect", {}),
    )


def build_context(
    case: CaseFile,
    *,
    registry: DataSourceRegistry | None = None,
    audit_path: str | Path | None = None,
) -> PipelineContext:
    """把场景文件装配成可执行的流水线上下文。"""
    reg = registry or build_registry()
    adapters = case.build_adapters()

    # 未绑定的已登记源用一个「不可用」的空适配器占位，保证降级链行为可预测
    for spec in reg.all_specs():
        if spec.source_id not in adapters:
            adapters[spec.source_id] = StaticDataSource(
                source_id=spec.source_id,
                semantics=spec.allowed_semantics,
                healthy=False,
            )

    chain = FallbackChain(reg, adapters, audit_path=audit_path)

    values: dict[str, TypedValue] = {}
    fetch_results = {}
    manifest = case.manifest

    wanted = sorted(manifest.all_semantics())
    for semantic in wanted:
        result = chain.fetch(semantic, case.symbol)
        fetch_results[semantic] = result
        values[semantic] = result.value

    return PipelineContext(
        symbol=case.symbol,
        values=values,
        fetch_results=fetch_results,
        registry=reg,
        manifest=manifest,
        chain=chain,
        meta=dict(case.meta),
    )
