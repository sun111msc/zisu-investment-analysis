"""数据源协议定义。

刻意保持窄接口：一个数据源只需回答一个问题 ——
「给定语义标签与标的，你能在某个时点给我一个合规的 ``TypedValue`` 吗？」

返回 ``None`` 表示「我不覆盖这个语义」，由降级链去试下一个源；
**不返回零值** —— 零值会被契约层拒绝，因为它无法区分「真的是 0」和「查不到」。
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from zisu.contracts import TypedValue

__all__ = ["DataSource", "DataSourceCapability", "SourceError"]


class SourceError(RuntimeError):
    """数据源调用失败。降级链会捕获它并尝试下一级。"""

    def __init__(self, source_id: str, message: str) -> None:
        super().__init__(f"[{source_id}] {message}")
        self.source_id = source_id
        self.message = message


@runtime_checkable
class DataSourceCapability(Protocol):
    """数据源的自述能力。必须是自述，不能由调用方假设。"""

    @property
    def source_id(self) -> str: ...

    @property
    def semantics(self) -> frozenset[str]: ...

    def supports(self, semantic: str) -> bool: ...


@runtime_checkable
class DataSource(DataSourceCapability, Protocol):
    """数据源主协议。"""

    def fetch(
        self,
        semantic: str,
        symbol: str,
        *,
        as_of: date | None = None,
    ) -> TypedValue | None:
        """取一个数值。

        Args:
            semantic: 语义标签，例如 ``revenue`` / ``pe_ttm``。
            symbol: 标的代码，含市场后缀，例如 ``300285.SZ``。
            as_of: 期望时点；``None`` 表示最新可用。

        Returns:
            合规的 ``TypedValue``，或 ``None`` 表示本源不覆盖该语义。

        Raises:
            SourceError: 本应覆盖但调用失败。
        """
        ...

    def available(self) -> bool:
        """健康探针。降级链在正式调用前会先问一次。"""
        ...
