"""故障注入。

评测的核心手法：**不测「正常情况能不能跑」，测「出错时能不能挡住」。**

每个注入都对应一类真实发生过或极易发生的错误，并声明期望被哪道闸门拦截。
如果注入后系统仍然给出结论，就说明闸门存在漏洞 —— 这类漏洞在正常路径下
永远暴露不出来。

::

    from injections import INJECTIONS, apply_injection
    raw = json.loads(Path("examples/cases/pass_case.json").read_text())
    mutated, note = apply_injection(raw, "zero_fill")
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

__all__ = ["INJECTIONS", "apply_injection", "list_injections"]


def _unauthorized_source(raw: dict[str, Any]) -> str:
    """让通用检索源去提供估值语义。

    模拟事故：模型为省事，用网页检索估了一个滚动市盈率。
    """
    raw.setdefault("sources", {})["news.events"] = ["pe_ttm", "market_cap"]
    raw.setdefault("records", {})["news.events"] = {}
    return "非结构化源被授权提供 pe_ttm / market_cap"


def _unregistered_source(raw: dict[str, Any]) -> str:
    """使用一个从未登记的数据源。"""
    raw.setdefault("sources", {})["generic.web.search"] = ["pe_ttm"]
    raw.setdefault("records", {})["generic.web.search"] = {
        "pe_ttm|DEMO.SZ": [64.2, "TODAY", None]
    }
    return "引入未登记数据源 generic.web.search"


def _zero_fill(raw: dict[str, Any]) -> str:
    """查不到的科目用 0 顶上。"""
    recs = raw["records"]["financials.statements.primary"]
    recs["accounts_receivable|DEMO.SZ"] = [0, "TODAY", "CNY"]
    return "把应收账款缺失填成了 0"


def _single_line(raw: dict[str, Any]) -> str:
    """跳过业务拆解，只留一条业务线。"""
    lines = raw["meta"]["profile"]["business_lines"]
    merged = {
        "name": "主营业务",
        "revenue": sum(x["revenue"] for x in lines),
        "revenue_share": 1.0,
        "gross_margin": 37.0,
    }
    raw["meta"]["profile"]["business_lines"] = [merged]
    return "把两条业务线并成一条，跳过拆解"


def _weak_bear(raw: dict[str, Any]) -> str:
    """空头论证敷衍了事 —— 典型的自我确认。"""
    raw["meta"]["market"]["bear_arguments"] = [
        {"claim": "估值偏高", "evidence_grade": "L4"}
    ]
    return "空头论据替换为无证据等级的敷衍表述"


def _no_market_cap(raw: dict[str, Any]) -> str:
    """缺市值，仍试图给出估值结论。"""
    raw["sources"]["market.quote.primary"] = [
        s for s in raw["sources"]["market.quote.primary"] if s != "market_cap"
    ]
    raw["records"]["market.quote.primary"].pop("market_cap|DEMO.SZ", None)
    return "移除市值字段"


def _shallow_chain(raw: dict[str, Any]) -> str:
    """产业链只拆到行业口号层。"""
    raw["meta"]["chain"]["layers"] = [
        {
            "level": 1,
            "name": "上游材料行业",
            "process": "聚合",
            "unit_value": 1.0,
            "unit": "元",
            "global_suppliers": 12,
            "certification_years": 0.5,
        },
        {
            "level": 2,
            "name": "中游制造领域",
            "process": "加工",
            "unit_value": 2.0,
            "unit": "元",
            "global_suppliers": 8,
            "certification_years": 0.5,
        },
    ]
    return "产业链退化为两层行业口号"


def _zero_peers(raw: dict[str, Any]) -> str:
    """没有可比样本，仍给出相对估值结论。"""
    raw["meta"]["valuation"]["peers"] = []
    return "清空可比公司样本"


#: 注入名 → (变换函数, 期望拦截的闸门, 说明)
INJECTIONS: dict[str, tuple[Callable[[dict[str, Any]], str], list[str]]] = {
    "unauthorized_source": (_unauthorized_source, ["GATE-01"]),
    "unregistered_source": (_unregistered_source, ["GATE-01"]),
    "zero_fill": (_zero_fill, ["GATE-41"]),
    "single_line": (_single_line, ["GATE-11"]),
    "weak_bear": (_weak_bear, ["GATE-16"]),
    "no_market_cap": (_no_market_cap, ["GATE-50"]),
    "shallow_chain": (_shallow_chain, ["GATE-12"]),
    "zero_peers": (_zero_peers, ["GATE-51"]),
}


def apply_injection(raw: dict[str, Any], name: str) -> tuple[dict[str, Any], str, list[str]]:
    """对样本施加一次注入，返回 (变换后的副本, 说明, 期望拦截的闸门)。"""
    if name not in INJECTIONS:
        raise KeyError(f"未知注入 {name!r}，可用：{sorted(INJECTIONS)}")
    fn, expected_gates = INJECTIONS[name]
    mutated = copy.deepcopy(raw)
    note = fn(mutated)
    mutated["expect"] = {"state": "BLOCKED", "must_pass": [], "must_fail": list(expected_gates)}
    mutated["title"] = f"[注入] {name}"
    mutated["description"] = note
    return mutated, note, expected_gates


def list_injections() -> list[dict[str, Any]]:
    return [
        {"name": name, "expect_gates": gates, "description": fn.__doc__}
        for name, (fn, gates) in INJECTIONS.items()
    ]
