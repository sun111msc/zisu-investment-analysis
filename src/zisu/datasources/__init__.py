"""数据源层：登记门禁 + 降级链 + 适配器。"""

from zisu.datasources.adapters import StaticDataSource, TextSourceAdapter, infer_unit
from zisu.datasources.base import DataSource, DataSourceCapability, SourceError
from zisu.datasources.fallback import (
    FallbackChain,
    FetchAudit,
    FetchOutcome,
    FetchResult,
)
from zisu.datasources.registry import (
    NEWS_ALLOWED_SEMANTICS,
    VALUATION_SEMANTICS,
    CapabilityManifest,
    DataSourceRegistry,
    DataSourceSpec,
    ManifestIssue,
    build_default_registry,
    build_registry,
)

__all__ = [
    "NEWS_ALLOWED_SEMANTICS",
    "VALUATION_SEMANTICS",
    "CapabilityManifest",
    "DataSource",
    "DataSourceCapability",
    "DataSourceRegistry",
    "DataSourceSpec",
    "FallbackChain",
    "FetchAudit",
    "FetchOutcome",
    "FetchResult",
    "ManifestIssue",
    "SourceError",
    "StaticDataSource",
    "TextSourceAdapter",
    "build_default_registry",
    "build_registry",
    "infer_unit",
]
