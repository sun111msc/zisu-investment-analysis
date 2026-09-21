"""紫苏投资分析 —— 以契约与闸门约束 LLM 在股票深度分析中的幻觉。

设计主线只有一条：**让每个数字都可追溯、每个结论都可证伪、每次失格都可见。**

三层结构：

- ``zisu.contracts``   —— 类型化数值契约 + 三态输出。任何数值进入链路前必须携带
  七属性（value / unit / currency / frequency / semantic / as_of / source）。
- ``zisu.datasources`` —— 数据源登记门禁。未登记的源直接拒绝进入计划；
  非结构化源无权提供估值类语义。
- ``zisu.gates``       —— 24 道程序化闸门，分五个阶段执行，失败即失败关闭。

之上是 ``zisu.pipeline``（八阶段，业务拆解先行）、``zisu.valuation``
（正向 DCF 仅作参考，核心是反向 DCF 反解市场隐含预期）、
``zisu.forensic``（四个公开法务会计模型）与 ``zisu.chains``（产业链 BOM 瓶颈分级）。

::

    from zisu import Pipeline, PipelineContext, build_registry

    ctx = PipelineContext(symbol="EXAMPLE.SZ", values={...}, registry=build_registry())
    run = Pipeline().run(ctx)
    print(run.state)          # PASS / DRAFT_REVIEW / BLOCKED
    print(run.to_markdown())

本项目不提供投资建议。见 DISCLAIMER.md。
"""

from zisu.chains import (
    BomLayer,
    BottleneckGrade,
    EnvironmentGrade,
    GovernanceGrade,
    position_cap,
    rank_bottlenecks,
)
from zisu.contracts import (
    OutputState,
    StateDeclaration,
    TypedValue,
    Unit,
    build_declaration,
    sum_values,
)
from zisu.datasources import (
    CapabilityManifest,
    DataSourceRegistry,
    DataSourceSpec,
    FallbackChain,
    StaticDataSource,
    build_registry,
)
from zisu.forensic import FinancialSnapshot, run_all
from zisu.gates import ALL_RULES, GateContext, GateReport, build_engine
from zisu.pipeline import (
    Pipeline,
    PipelineContext,
    PipelineRun,
    default_phases,
)
from zisu.valuation import (
    solve_implied_g,
    solve_implied_wacc,
)

__version__ = "1.0.0"

__all__ = [
    "ALL_RULES",
    "BomLayer",
    "BottleneckGrade",
    "CapabilityManifest",
    "DataSourceRegistry",
    "DataSourceSpec",
    "EnvironmentGrade",
    "FallbackChain",
    "FinancialSnapshot",
    "GateContext",
    "GateReport",
    "GovernanceGrade",
    "OutputState",
    "Pipeline",
    "PipelineContext",
    "PipelineRun",
    "StateDeclaration",
    "StaticDataSource",
    "TypedValue",
    "Unit",
    "__version__",
    "build_declaration",
    "build_engine",
    "build_registry",
    "default_phases",
    "position_cap",
    "rank_bottlenecks",
    "run_all",
    "solve_implied_g",
    "solve_implied_wacc",
    "sum_values",
]
