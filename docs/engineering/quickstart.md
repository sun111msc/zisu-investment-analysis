# 快速上手

## 安装

```bash
git clone https://github.com/sun111msc/zisu-investment-analysis.git
cd zisu-investment-analysis
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

核心库**零第三方运行时依赖**，只用标准库。

## 第一步：看一次完整分析

```bash
PYTHONPATH=src python examples/quickstart.py
```

输出包含：能力清单、八个阶段的执行情况、市场隐含预期、最终三态状态。

## 第二步：看闸门如何拦截错误

```bash
PYTHONPATH=src python examples/gate_demo.py
```

这是本项目最值得看的一段输出。它拿一个能通过的样本，注入八类典型错误，
观察是否被拦截、由哪道闸门拦截：

```
✅ unauthorized_source   非结构化源被授权提供 pe_ttm → GATE-01 拦截
✅ zero_fill             应收账款缺失填成 0        → GATE-41 拦截
✅ single_line           两条业务线并成一条        → GATE-11 拦截
✅ weak_bear             空头论据敷衍             → GATE-16 拦截
...
拦截结果：8/8 全部挡下
```

## 第三步：命令行

```bash
# 跑一个场景
zisu analyze examples/cases/pass_case.json

# JSON 输出（供程序消费）
zisu analyze examples/cases/blocked_case.json --json

# 列出全部闸门
zisu gates

# BLOCKED 时以退出码 2 结束（供 CI 使用）
zisu analyze case.json --fail-on-block
```

## 第四步：写自己的场景

一个场景就是一个 JSON 文件。最小结构：

```json
{
  "symbol": "DEMO.SZ",
  "sources": {
    "market.quote.primary": ["price", "market_cap", "shares_outstanding"],
    "financials.statements.primary": ["revenue", "net_income", "gross_margin"]
  },
  "records": {
    "market.quote.primary": {
      "price|DEMO.SZ": [28.4, "TODAY", "CNY"],
      "market_cap|DEMO.SZ": [200.0, "TODAY", "CNY"],
      "shares_outstanding|DEMO.SZ": [7.04, "TODAY", null]
    },
    "financials.statements.primary": {
      "revenue|DEMO.SZ": [100.0, "TODAY", "CNY"],
      "net_income|DEMO.SZ": [12.0, "TODAY", "CNY"],
      "gross_margin|DEMO.SZ": [37.0, "TODAY", null]
    }
  },
  "meta": { "...": "各阶段的输入" }
}
```

要点：

- `records` 的键是 `语义|标的`，值是 `[数值, 时点, 币种]`
- 时点支持 ISO 日期或 `TODAY` 占位符（后者让评测集不随时间漂移）
- `sources` 里声明的语义必须属于该数据源的授权范围，否则 `GATE-01` 会拦截
- 未在 `sources` 中声明的语义不会被采集，对应闸门会报缺失

完整字段说明见 `examples/cases/pass_case.json`（含注释性 description）。

## 第五步：接入自己的数据源

实现两个方法即可：

```python
from datetime import date
from zisu.contracts import TypedValue, Unit, Frequency
from zisu.datasources import DataSourceSpec


class MyDataSource:
    def __init__(self, source_id: str, semantics: frozenset[str]):
        self._id = source_id
        self._semantics = semantics

    @property
    def source_id(self) -> str:
        return self._id

    @property
    def semantics(self) -> frozenset[str]:
        return self._semantics

    def supports(self, semantic: str) -> bool:
        return semantic in self._semantics

    def available(self) -> bool:
        return True   # 健康探针

    def fetch(self, semantic, symbol, *, as_of=None):
        raw = self._call_upstream(semantic, symbol, as_of)
        if raw is None:
            return None          # 不覆盖该语义 → 降级链继续
        return TypedValue(
            value=float(raw["value"]),
            unit=Unit.CNY,
            semantic=semantic,
            as_of=date.fromisoformat(raw["date"]),
            source=self._id,
            currency="CNY",
            frequency=Frequency.ANNUAL,
        )
```

然后在注册表登记，并绑定到降级链：

```python
from zisu.datasources import build_registry, DataSourceSpec, FallbackChain

reg = build_registry()
reg.register(DataSourceSpec(
    source_id="my.vendor.primary",
    kind="financials",
    description="自建财务数据源",
    allowed_semantics=frozenset({"revenue", "net_income"}),
    priority=0,
    ttl_days=120,
))

chain = FallbackChain(reg)
chain.bind("my.vendor.primary", MyDataSource("my.vendor.primary", frozenset({"revenue"})))
```

**注意**：`fetch` 返回 `None` 表示「本源不覆盖此语义」，
由降级链去试下一个源；**不要返回 0** —— 那会被契约层拒绝，
因为它无法区分「真的是 0」与「查不到」。

## 第六步：加一道闸门

```python
# src/zisu/gates/rules.py
def gate_44_unit_scale_anomaly(ctx):
    """GATE-44 同一语义跨期量级跳变检测。"""
    hist = ctx.art("phase3.statements", {}).get("rows", [])
    ...
    return ok("无异常") or fail("...")
```

然后在 `ALL_RULES` 登记、更新 `docs/engineering/gate-catalog.md`、加正反两个单测。
具体步骤见 [CONTRIBUTING.md](../../CONTRIBUTING.md)。

## 第七步：跑评测

```bash
make eval                    # 跑全部样本
make eval-out                # 输出到 evals/reports/
PYTHONPATH=src python evals/run_eval.py --strict   # 劣化即失败
```

指标定义见 [evals/README.md](../../evals/README.md)。
