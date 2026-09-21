"""闸门规则集。

编号约定：``GATE-{阶段}{序号}``。阶段编号 1-5 对应五阶段质控。

每条规则是一个纯函数：``GateContext -> GateResult``。
规则只读上下文，不做副作用 —— 这保证闸门可以被单测覆盖、被评测集回归。

本文件实现的是**开源核心集**（25 道）。编号在 ``docs/engineering/gate-catalog.md``
中预留了扩展位，新增规则请遵循 CONTRIBUTING 的五步流程。
"""

from __future__ import annotations

from typing import Any

from zisu.datasources.fallback import FetchOutcome
from zisu.gates.engine import (
    GateContext,
    GateEngine,
    GateResult,
    GateSkipped,
    GateStage,
    contract_violations,
    fail,
    ok,
    require_art,
)

__all__ = ["build_engine", "ALL_RULES"]


# ==========================================================================
# 阶段 1 · 数据采集质量
# ==========================================================================


def gate_01_source_registered(ctx: GateContext) -> GateResult:
    """GATE-01 数据源登记门禁。未登记或越权 → 阻断。"""
    if ctx.manifest is None:
        return fail("未产出能力清单，分析不得开始")
    if ctx.registry is None:
        return fail("未提供数据源注册表")
    issues = ctx.registry.verify_manifest(ctx.manifest)
    if not issues:
        return ok(f"{len(ctx.manifest.claims)} 个数据源全部合规")
    hard = [i for i in issues if i.blocking]
    detail = "；".join(f"{i.code} {i.source_id}:{i.semantic}" for i in hard[:5])
    more = f"（另 {len(hard) - 5} 项）" if len(hard) > 5 else ""
    return fail(f"{len(hard)} 项违规：{detail}{more}")


def gate_02_contract_compliance(ctx: GateContext) -> GateResult:
    """GATE-02 类型化数值契约：七属性完整性。"""
    if not ctx.values:
        return fail("上下文中没有任何数值，无法校验契约")
    violations = contract_violations(ctx.values.values())
    if violations:
        return fail(
            f"{len(violations)} 项契约违反：{'; '.join(violations[:4])}",
            evidence="\n".join(violations),
        )
    return ok(f"{len(ctx.values)} 个数值全部携带七属性")


def gate_03_freshness(ctx: GateContext) -> GateResult:
    """GATE-03 数据时效性。超期不阻断，但必须披露。"""
    if ctx.registry is None or not ctx.values:
        raise GateSkipped("缺少注册表或无可用数值")
    stale: list[str] = []
    for v in ctx.values.values():
        if v.is_missing:
            continue
        issue = ctx.registry.check_freshness(v.source, v.as_of)
        if issue is not None:
            stale.append(f"{v.semantic}({v.as_of.isoformat()})")
    if stale:
        return fail(f"{len(stale)} 项数据超期：{', '.join(stale[:5])}", evidence="; ".join(stale))
    return ok("全部数值在时效窗口内")


def gate_04_degradation_rate(ctx: GateContext) -> GateResult:
    """GATE-04 主源命中率。降级率过高说明数据底座不稳。"""
    audit = ctx.audit()
    if not audit:
        raise GateSkipped("无取数审计")
    exhausted = [a for a in audit if a.outcome is FetchOutcome.EXHAUSTED]
    if exhausted:
        sems = sorted({a.semantic for a in exhausted})
        return fail(f"降级链彻底耗尽：{', '.join(sems)}")
    hits = [a for a in audit if a.outcome is FetchOutcome.HIT]
    if not hits:
        return fail("无任何成功取数记录")
    l0 = len([a for a in hits if a.tier == "L0"])
    rate = l0 / len(hits)
    if rate < 0.5:
        return fail(f"主源命中率仅 {rate:.0%}，大量依赖备份源", evidence=f"hits={len(hits)}")
    return ok(f"主源命中率 {rate:.0%}")


def gate_05_required_semantics(ctx: GateContext) -> GateResult:
    """GATE-05 必需语义覆盖。核心口径缺失则无法得出结论。"""
    required = {"revenue", "net_income"}
    missing = sorted(s for s in required if s in ctx.values and ctx.values[s].is_missing)
    absent = sorted(s for s in required if s not in ctx.values)
    if missing:
        return fail(f"必需语义缺失：{', '.join(missing)}")
    if absent:
        return fail(f"必需语义未采集：{', '.join(absent)}")
    return ok("营收与净利均已取得")


# ==========================================================================
# 阶段 2 · 分析深度质量
# ==========================================================================


def gate_10_one_line_definition(ctx: GateContext) -> GateResult:
    """GATE-10 一句话公司定义。说不清就不该继续。"""
    one = require_art(ctx, "phase0.one_liner")
    if not isinstance(one, str) or len(one.strip()) < 10:
        return fail("一句话定义过短或缺失")
    jargon = ["赋能", "生态化", "全链路", "一站式", "闭环"]
    hit = [w for w in jargon if w in one]
    if hit:
        return fail(f"定义中使用了非外行词汇：{hit}。请改为外行能懂的表达")
    return ok(one.strip())


def gate_11_business_breakdown(ctx: GateContext) -> GateResult:
    """GATE-11 分业务拆解完整性与加权验证。"""
    lines = require_art(ctx, "phase0.business_lines")
    if not isinstance(lines, list) or len(lines) < 2:
        return fail(f"业务线条数 {len(lines) if isinstance(lines, list) else 0} < 2，拆解不足")

    shares = [float(x.get("revenue_share", 0)) for x in lines]
    total = sum(shares)
    if abs(total - 1.0) > 0.02:
        return fail(f"各业务线收入占比合计 {total:.4f}，偏离 1.0 超过容差")

    # 加权验证：Σ(占比 × 毛利率) ≈ 整体毛利率
    gm_company = ctx.num("gross_margin")
    if gm_company is None:
        return fail("缺少公司整体毛利率，无法做加权验证")

    weighted = sum(
        float(x.get("revenue_share", 0)) * float(x.get("gross_margin", 0)) for x in lines
    )
    diff = abs(weighted - gm_company)
    if diff > 2.0:  # 百分点容差
        return fail(
            f"加权毛利率 {weighted:.2f}% 与整体毛利率 {gm_company:.2f}% 相差 {diff:.2f}pct，"
            "拆解口径不自洽"
        )
    return ok(f"{len(lines)} 条业务线，加权毛利率偏差 {diff:.2f}pct")


def gate_12_bom_depth(ctx: GateContext) -> GateResult:
    """GATE-12 产业链工序级深度。"""
    layers = require_art(ctx, "phase2.bom_layers")
    if not isinstance(layers, list) or len(layers) < 7:
        return fail(f"产业链层级 {len(layers) if isinstance(layers, list) else 0} < 7，未达工序级")

    vague = [
        x.get("name", "")
        for x in layers
        if any(k in str(x.get("name", "")) for k in ["行业", "领域", "板块"])
    ]
    if vague:
        return fail(f"以下层级停留在行业口号而非具体工序：{vague[:3]}")

    missing_val = [x.get("name") for x in layers if not x.get("unit_value")]
    if missing_val:
        return fail(f"以下工序缺少单台/单件价值量：{missing_val[:3]}")
    return ok(f"{len(layers)} 层工序级拆解，均含价值量")


def gate_13_competitor_exclusion(ctx: GateContext) -> GateResult:
    """GATE-13 竞争者排除矩阵。只列名字不证明不算数。"""
    rows = require_art(ctx, "phase2.excluded_competitors")
    if not isinstance(rows, list) or len(rows) < 5:
        return fail(f"排除矩阵仅 {len(rows) if isinstance(rows, list) else 0} 家，要求 ≥5 家")
    weak = [
        r.get("name")
        for r in rows
        if not str(r.get("reason", "")).strip() or len(str(r.get("reason", ""))) < 10
    ]
    if weak:
        return fail(f"以下玩家的排除理由不充分：{weak[:3]}")
    return ok(f"{len(rows)} 家逐家给出排除理由")


def gate_14_capacity_bridge(ctx: GateContext) -> GateResult:
    """GATE-14 产能 → 收入量化桥梁。"""
    bridge = require_art(ctx, "phase2.capacity_bridge")
    required = {"equipment_units", "asp", "delivery_ratio", "acceptance_ratio", "unit"}
    missing = sorted(required - set(bridge or {}))
    if missing:
        return fail(f"量化桥梁缺少字段：{missing}", evidence=str(bridge))
    implied = (
        float(bridge["equipment_units"])
        * float(bridge["asp"])
        * float(bridge["delivery_ratio"])
        * float(bridge["acceptance_ratio"])
    )
    if implied <= 0:
        return fail("推导收入非正，桥梁不成立")
    return ok(f"设备台数 × ASP × 交付 × 验收 → 隐含收入 {implied:,.0f} {bridge['unit']}")


def gate_15_nonconsensus(ctx: GateContext) -> GateResult:
    """GATE-15 强制发现非共识 ≥2 条。"""
    items = require_art(ctx, "phase4.nonconsensus")
    if not isinstance(items, list):
        return fail("非共识清单格式非法")
    valid = [x for x in items if isinstance(x, str) and len(x.strip()) >= 15]
    if len(valid) < 2:
        return fail(f"有效非共识仅 {len(valid)} 条，要求 ≥2 条")
    return ok(f"{len(valid)} 条非共识论点")


def gate_16_bear_strength(ctx: GateContext) -> GateResult:
    """GATE-16 魔鬼代言人强度。空头论证必须不弱于多头。"""
    bear = require_art(ctx, "phase4.bear_arguments")
    bull = ctx.art("phase4.bull_arguments", [])

    strong_bear = [a for a in (bear or []) if str(a.get("evidence_grade", "")).upper() in {"L1", "L2"}]
    strong_bull = [a for a in (bull or []) if str(a.get("evidence_grade", "")).upper() in {"L1", "L2"}]

    if len(strong_bear) < len(strong_bull):
        return fail(
            f"高证据等级空头论据 {len(strong_bear)} 条 < 多头 {len(strong_bull)} 条，"
            "空头写得太弱，属于自我确认"
        )
    if len(strong_bear) < 2:
        return fail(f"高证据等级空头论据仅 {len(strong_bear)} 条，要求 ≥2 条")
    return ok(f"强空头论据 {len(strong_bear)} 条 ≥ 强多头 {len(strong_bull)} 条")


# ==========================================================================
# 阶段 3 · 逻辑一致性质量
# ==========================================================================


def gate_20_statement_tie_out(ctx: GateContext) -> GateResult:
    """GATE-20 三表勾稽。"""
    stmts = require_art(ctx, "phase3.statements")
    years = stmts.get("years", []) if isinstance(stmts, dict) else []
    if len(years) < 5:
        return fail(f"预测年数 {len(years)} < 5")

    bad: list[str] = []
    for row in stmts.get("rows", []):
        assets = float(row.get("total_assets", 0))
        liab = float(row.get("total_liabilities", 0))
        equity = float(row.get("total_equity", 0))
        if abs(assets - (liab + equity)) > max(1.0, assets * 0.005):
            bad.append(f"{row.get('year')}: 资产 {assets:,.0f} ≠ 负债+权益 {liab + equity:,.0f}")
    if bad:
        return fail(f"{len(bad)} 个年度勾稽不平：{bad[:2]}")
    return ok(f"{len(years)} 年三表勾稽平衡")


def gate_21_segment_sum(ctx: GateContext) -> GateResult:
    """GATE-21 分业务收入加总 = 整体收入。"""
    lines = require_art(ctx, "phase0.business_lines")
    total_rev = ctx.num("revenue")
    if total_rev is None:
        return fail("缺少整体营收，无法校验分业务加总")

    seg_sum = sum(float(x.get("revenue", 0)) for x in lines)
    if seg_sum <= 0:
        return fail("分业务收入合计非正")
    diff = abs(seg_sum - total_rev) / total_rev
    if diff > 0.02:
        return fail(
            f"分业务加总 {seg_sum:,.0f} 与整体营收 {total_rev:,.0f} 偏差 {diff:.1%}，超过 2%"
        )
    return ok(f"分业务加总偏差 {diff:.2%}")


def gate_22_scale_priority(ctx: GateContext) -> GateResult:
    """GATE-22 时间尺度冲突裁决声明。"""
    decl = require_art(ctx, "phase6.scale_declaration")
    horizon = str(decl.get("horizon", ""))
    primary = str(decl.get("primary_module", ""))
    if horizon not in {"short", "medium", "long"}:
        return fail(f"持有周期声明非法：{horizon!r}")
    if not primary:
        return fail("未声明主导决策模块，尺度冲突无法裁决")
    conflicts = decl.get("conflicts", [])
    unresolved = [c for c in conflicts if not c.get("resolved")]
    if unresolved:
        return fail(f"{len(unresolved)} 处尺度冲突未裁决")
    return ok(f"尺度={horizon}，主导模块={primary}")


def gate_23_counterfactual(ctx: GateContext) -> GateResult:
    """GATE-23 反事实推理。必须回答「如果核心假设不成立会怎样」。"""
    items = require_art(ctx, "phase4.counterfactuals")
    if not isinstance(items, list) or len(items) < 1:
        return fail("缺少反事实推理")
    for item in items:
        if not item.get("if") or not item.get("then"):
            return fail("反事实条目缺少 if/then 结构")
        if not item.get("observable"):
            return fail(f"反事实「{item.get('if')}」缺少可观测的验证指标")
    return ok(f"{len(items)} 条反事实推理，均含可观测指标")


# ==========================================================================
# 阶段 4 · 格式与合规质量
# ==========================================================================


def gate_40_state_declaration(ctx: GateContext) -> GateResult:
    """GATE-40 状态声明存在。无声明不得发布。"""
    decl = ctx.art("report.declaration")
    if decl is None:
        return fail("报告缺少三态状态声明")
    if not hasattr(decl, "state"):
        return fail("状态声明格式非法")
    return ok(f"状态={decl.state.value}；阻断 {len(decl.blockers)} 项，提示 {len(decl.warnings)} 项")


def gate_41_no_zero_fill(ctx: GateContext) -> GateResult:
    """GATE-41 缺失数据禁止零值填充。"""
    suspects: list[str] = []
    for v in ctx.values.values():
        if v.is_missing:
            continue
        if v.value == 0.0 and v.semantic not in _LEGITIMATE_ZERO:
            suspects.append(f"{v.semantic}(src={v.source})")
    if suspects:
        return fail(f"以下数值为 0 且非合法零值，疑似用零填充了缺失：{suspects[:5]}")
    return ok("未发现零值填充迹象")


#: 这些语义的 0 是合法业务值
_LEGITIMATE_ZERO: frozenset[str] = frozenset(
    {"net_income", "capex", "pledge_ratio", "volume", "market_share", "inventory"}
)


def gate_42_full_provenance(ctx: GateContext) -> GateResult:
    """GATE-42 数值全量溯源。"""
    untraceable = [
        v.semantic
        for v in ctx.values.values()
        if not v.source or v.source == "unresolved"
    ]
    if untraceable:
        return fail(f"{len(untraceable)} 个数值无来源：{untraceable[:5]}")
    return ok(f"{len(ctx.values)} 个数值全部可溯源")


def gate_43_valuation_method_tagged(ctx: GateContext) -> GateResult:
    """GATE-43 估值方法必须显式标注。"""
    anchors = require_art(ctx, "phase5.anchors")
    if not anchors:
        return fail("未标注任何估值锚")
    for name, spec in anchors.items():
        if not spec.get("method"):
            return fail(f"估值锚 {name!r} 未注明方法")
    return ok(f"估值锚：{', '.join(anchors)}")


# ==========================================================================
# 阶段 5 · 投资判断质量
# ==========================================================================


def gate_50_reverse_dcf_converged(ctx: GateContext) -> GateResult:
    """GATE-50 反向 DCF 收敛。不收敛说明市场隐含预期无法解释。"""
    rd = require_art(ctx, "phase5.reverse_dcf")
    if not rd.get("converged", False):
        return fail(f"反向 DCF 未收敛：{rd.get('note', '无说明')}")
    g = rd.get("implied_g")
    wacc = rd.get("implied_wacc")
    if g is None or wacc is None:
        return fail("反解结果缺少隐含增速或隐含折现率")
    if wacc <= g:
        return fail(f"隐含 WACC {wacc:.2%} ≤ 隐含增速 {g:.2%}，永续假设不成立")
    return ok(f"隐含 g={g:.2%}，隐含 WACC={wacc:.2%}（不产出目标价，仅作校验）")


def gate_51_multi_anchor(ctx: GateContext) -> GateResult:
    """GATE-51 估值多锚交叉验证。单锚结论不予采信。"""
    anchors = require_art(ctx, "phase5.anchors")
    if len(anchors) < 2:
        return fail(f"仅 {len(anchors)} 个估值锚，要求 ≥2 个（主锚 + 交叉验证锚）")
    vals = [float(a.get("value", 0)) for a in anchors.values() if a.get("value")]
    if len(vals) >= 2:
        spread = (max(vals) - min(vals)) / (sum(vals) / len(vals))
        if spread > 0.8:
            return fail(f"各锚估值离散度 {spread:.0%} 过大，结论不可靠")
    return ok(f"{len(anchors)} 个锚交叉验证，离散度 {spread:.0%}" if len(vals) >= 2 else "多锚就位")


def gate_52_position_limit(ctx: GateContext) -> GateResult:
    """GATE-52 仓位上限约束。"""
    pos = require_art(ctx, "phase6.position")
    max_pct = float(pos.get("max_pct", 0))
    if max_pct <= 0:
        return fail("未给出仓位上限")
    if max_pct > 0.25:
        return fail(f"单标的上限 {max_pct:.0%} 超过 25% 硬顶")
    env = str(pos.get("environment", "")).upper()
    env_cap = {"A": 1.0, "B": 0.7, "C": 0.3, "D": 0.1}.get(env)
    if env_cap is None:
        return fail(f"环境评级非法：{env!r}")
    if env_cap <= 0.1 and pos.get("open_new"):
        return fail("D 级环境下禁止开新仓")
    return ok(f"上限 {max_pct:.0%}，环境 {env}（总仓上限 {env_cap:.0%}）")


def gate_53_stop_loss_defined(ctx: GateContext) -> GateResult:
    """GATE-53 止损必须定义且与入场价有距离。"""
    pos = require_art(ctx, "phase6.position")
    entry = pos.get("entry_price")
    stop = pos.get("stop_loss")
    if entry is None or stop is None:
        return fail("缺少入场价或止损价")
    entry, stop = float(entry), float(stop)
    if stop >= entry:
        return fail(f"止损 {stop} 不低于入场 {entry}，不构成止损")
    risk = (entry - stop) / entry
    if risk > 0.20:
        return fail(f"单笔风险 {risk:.1%} 超过 20%，与 1% 资金风险原则冲突")
    return ok(f"止损距离 {risk:.1%}")


def gate_54_target_range(ctx: GateContext) -> GateResult:
    """GATE-54 目标价必须给区间而非单一数字。"""
    summary = require_art(ctx, "phase0.exec_summary")
    target = summary.get("target_range")
    if not isinstance(target, (list, tuple)) or len(target) != 2:
        return fail("目标价不是区间形式（低, 高）")
    low, high = float(target[0]), float(target[1])
    if low >= high:
        return fail(f"目标区间非法：{low} → {high}")
    return ok(f"目标区间 {low} → {high}")


# ==========================================================================
# 注册
# ==========================================================================

ALL_RULES: list[tuple[str, str, GateStage, Any, bool]] = [
    # 阶段 1
    ("GATE-01", "数据源登记门禁", GateStage.DATA, gate_01_source_registered, True),
    ("GATE-02", "类型化数值契约", GateStage.DATA, gate_02_contract_compliance, True),
    ("GATE-03", "数据时效性", GateStage.DATA, gate_03_freshness, False),
    ("GATE-04", "主源命中率", GateStage.DATA, gate_04_degradation_rate, False),
    ("GATE-05", "必需语义覆盖", GateStage.DATA, gate_05_required_semantics, True),
    # 阶段 2
    ("GATE-10", "一句话公司定义", GateStage.DEPTH, gate_10_one_line_definition, True),
    ("GATE-11", "分业务拆解完整性", GateStage.DEPTH, gate_11_business_breakdown, True),
    ("GATE-12", "产业链工序级深度", GateStage.DEPTH, gate_12_bom_depth, True),
    ("GATE-13", "竞争者排除矩阵", GateStage.DEPTH, gate_13_competitor_exclusion, True),
    ("GATE-14", "产能→收入量化桥梁", GateStage.DEPTH, gate_14_capacity_bridge, True),
    ("GATE-15", "非共识论证", GateStage.DEPTH, gate_15_nonconsensus, True),
    ("GATE-16", "魔鬼代言人强度", GateStage.DEPTH, gate_16_bear_strength, True),
    # 阶段 3
    ("GATE-20", "三表勾稽", GateStage.LOGIC, gate_20_statement_tie_out, True),
    ("GATE-21", "分业务加总一致性", GateStage.LOGIC, gate_21_segment_sum, True),
    ("GATE-22", "时间尺度裁决", GateStage.LOGIC, gate_22_scale_priority, True),
    ("GATE-23", "反事实推理", GateStage.LOGIC, gate_23_counterfactual, False),
    # 阶段 4
    ("GATE-40", "三态状态声明", GateStage.FORMAT, gate_40_state_declaration, True),
    ("GATE-41", "缺失零填充检测", GateStage.FORMAT, gate_41_no_zero_fill, True),
    ("GATE-42", "数值全量溯源", GateStage.FORMAT, gate_42_full_provenance, True),
    ("GATE-43", "估值方法标注", GateStage.FORMAT, gate_43_valuation_method_tagged, True),
    # 阶段 5
    ("GATE-50", "反向 DCF 收敛", GateStage.JUDGMENT, gate_50_reverse_dcf_converged, True),
    ("GATE-51", "估值多锚交叉", GateStage.JUDGMENT, gate_51_multi_anchor, True),
    ("GATE-52", "仓位上限约束", GateStage.JUDGMENT, gate_52_position_limit, True),
    ("GATE-53", "止损定义", GateStage.JUDGMENT, gate_53_stop_loss_defined, True),
    ("GATE-54", "目标价区间", GateStage.JUDGMENT, gate_54_target_range, False),
]


def build_engine() -> GateEngine:
    """构造装载全部开源规则的引擎。"""
    engine = GateEngine()
    for gate_id, name, stage, rule, blocking in ALL_RULES:
        engine.register(gate_id, name, stage, rule, blocking=blocking)
    return engine
