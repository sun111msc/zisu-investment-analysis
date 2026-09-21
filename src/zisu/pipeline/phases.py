"""八个分析阶段的实现。

流水线顺序（正金字塔：**业务拆解先行，市场认知后置**）：

::

    P0 公司画像   → 这家公司靠什么赚钱？
    P1 行业定位   → 它在什么赛道、赛道多大？
    P2 深度穿透   → 钱被产业链哪一层赚走了？
    P3 财务预测   → 三表联动五年 + 盈余质量
    P4 市场认知   → 市场在哪里可能错了？（只提问）
    P5 估值定价   → 隐含预期反解 + 多锚交叉
    P6 执行方案   → 买多少、什么价、何时退
    P7 最终裁决   → 可证伪的一句话结论

为什么是「业务先行」而不是「市场认知先行」：如果先讨论市场共识，
后续所有分析都会被这个共识锚定，形成循环论证。先建立独立的业务事实，
再去问「市场是不是错了」，这两个判断才互相独立。

阶段只做确定性计算；需要自然语言的部分从 ``ctx.meta`` 读取草稿并校验。
"""

from __future__ import annotations

from typing import Any

from zisu.chains import (
    BomLayer,
    BottleneckGrade,
    EnvironmentGrade,
    GovernanceGrade,
    position_cap,
    rank_bottlenecks,
)
from zisu.forensic import FinancialSnapshot, run_all
from zisu.pipeline.base import Phase, PhaseResult, PipelineContext
from zisu.valuation import (
    DCFInput,
    PeerMetrics,
    equity_value,
    interpret,
    peer_valuation,
    solve_implied_g,
)

__all__ = [
    "Phase0Profile",
    "Phase1Industry",
    "Phase2Penetration",
    "Phase3Financials",
    "Phase4Market",
    "Phase5Valuation",
    "Phase6Execution",
    "Phase7Verdict",
    "default_phases",
]


# ==========================================================================
# P0 · 公司画像
# ==========================================================================


class Phase0Profile(Phase):
    """建立业务事实底座。所有后续判断都从这里出发。"""

    phase_id = "P0"
    name = "公司画像"
    provides = (
        "phase0.one_liner",
        "phase0.business_lines",
        "phase0.peak_count",
        "phase0.exec_summary",
    )

    def run(self, ctx: PipelineContext) -> PhaseResult:
        profile: dict[str, Any] = ctx.meta.get("profile") or {}
        notes: list[str] = []

        one_liner = profile.get("one_liner", "")
        if not one_liner:
            rev = ctx.num("revenue")
            one_liner = (
                f"（自动占位）{ctx.symbol} 是一家营业收入 {rev:,.0f} 的公司，业务描述待补。"
                if rev is not None
                else "（自动占位）业务描述缺失。"
            )
            notes.append("meta.profile.one_liner 缺失，已生成占位内容，GATE-10 将不通过")

        lines: list[dict[str, Any]] = list(profile.get("business_lines") or [])
        if not lines:
            rev = ctx.num("revenue")
            gm = ctx.num("gross_margin")
            if rev is not None:
                lines = [
                    {
                        "name": "未拆分",
                        "revenue": rev,
                        "revenue_share": 1.0,
                        "gross_margin": gm if gm is not None else 0.0,
                    }
                ]
                notes.append("未提供分业务拆解，已退化为单一业务线，GATE-11 将不通过")

        exec_summary: dict[str, Any] = dict(profile.get("exec_summary") or {})
        target = exec_summary.get("target_range")
        if not isinstance(target, (list, tuple)) or len(target) != 2:
            price = ctx.num("price")
            if price is not None:
                exec_summary["target_range"] = [round(price * 0.9, 2), round(price * 1.2, 2)]
                notes.append("目标价区间缺失，已用当前价 ±10%/20% 占位，GATE-54 将提示")

        ctx.put("phase0.one_liner", one_liner)
        ctx.put("phase0.business_lines", lines)
        ctx.put("phase0.peer_count", len(profile.get("peers") or []))
        ctx.put("phase0.exec_summary", exec_summary)

        return PhaseResult(self.phase_id, self.name, artifacts=dict(ctx.artifacts), notes=notes)


# ==========================================================================
# P1 · 行业定位
# ==========================================================================


class Phase1Industry(Phase):
    phase_id = "P1"
    name = "行业定位"
    requires = ("phase0.one_liner",)
    provides = ("phase1.industry",)

    def run(self, ctx: PipelineContext) -> PhaseResult:
        missing = self.missing_requires(ctx)
        if missing:
            return self.skipped(ctx, f"缺少前置产物：{missing}")

        industry: dict[str, Any] = dict(ctx.meta.get("industry") or {})
        notes: list[str] = []

        tam = industry.get("tam")
        sam = industry.get("sam")
        som = industry.get("som")
        if not all(isinstance(x, (int, float)) for x in (tam, sam, som)):
            notes.append("TAM/SAM/SOM 不完整，行业空间测算不可用")
        elif not (tam >= sam >= som):
            notes.append(f"空间层级倒挂：TAM={tam} SAM={sam} SOM={som}，请核对口径")

        cagr = industry.get("cagr")
        penetration = industry.get("penetration")
        lifecycle = industry.get("lifecycle", "unknown")

        ctx.put(
            "phase1.industry",
            {
                "tam": tam,
                "sam": sam,
                "som": som,
                "cagr": cagr,
                "penetration": penetration,
                "lifecycle": lifecycle,
                "peer_count": ctx.get("phase0.peer_count", 0),
            },
        )
        return PhaseResult(self.phase_id, self.name, artifacts=dict(ctx.artifacts), notes=notes)


# ==========================================================================
# P2 · 深度穿透
# ==========================================================================


class Phase2Penetration(Phase):
    phase_id = "P2"
    name = "深度穿透"
    requires = ("phase0.one_liner",)
    provides = (
        "phase2.bom_layers",
        "phase2.bottleneck_ranking",
        "phase2.excluded_competitors",
        "phase2.capacity_bridge",
    )

    def run(self, ctx: PipelineContext) -> PhaseResult:
        missing = self.missing_requires(ctx)
        if missing:
            return self.skipped(ctx, f"缺少前置产物：{missing}")

        chain: dict[str, Any] = dict(ctx.meta.get("chain") or {})
        raw_layers = chain.get("layers") or []
        notes: list[str] = []

        layers: list[BomLayer] = []
        for item in raw_layers:
            try:
                layers.append(BomLayer(**item))
            except (TypeError, ValueError) as exc:
                notes.append(f"层级定义非法被丢弃：{item.get('name', '?')} — {exc}")

        ranking = []
        if layers:
            ranking = rank_bottlenecks(layers, triggers=chain.get("triggers"))
            top = ranking[0]
            notes.append(
                f"瓶颈最强层级：{top.layer_name}（{top.grade.value} {top.grade.label}）"
            )

        ctx.put("phase2.bom_layers", [layer.__dict__ for layer in layers])
        ctx.put(
            "phase2.bottleneck_ranking",
            [
                {
                    "layer": a.layer_name,
                    "grade": a.grade.value,
                    "leaves": a.grade.leaves,
                    "evidence": a.evidence,
                    "disqualifiers": a.disqualifiers,
                }
                for a in ranking
            ],
        )
        ctx.put("phase2.excluded_competitors", list(chain.get("excluded_competitors") or []))
        ctx.put("phase2.capacity_bridge", dict(chain.get("capacity_bridge") or {}))

        return PhaseResult(self.phase_id, self.name, artifacts=dict(ctx.artifacts), notes=notes)


# ==========================================================================
# P3 · 财务预测
# ==========================================================================


class Phase3Financials(Phase):
    """三表联动五年预测 + 盈余质量诊断。

    预测用显式假设驱动，报表之间主动配平 ——
    权益由「资产 − 负债」倒算，因此勾稽恒等式天然成立，
    这样任何不平衡都指向真实的建模错误，而不是舍入误差。
    """

    phase_id = "P3"
    name = "财务预测与盈余质量"
    provides = ("phase3.statements", "phase3.forensic", "phase3.fcff")

    def run(self, ctx: PipelineContext) -> PhaseResult:
        notes: list[str] = []
        rev0 = ctx.num("revenue")
        ni0 = ctx.num("net_income")
        if rev0 is None or ni0 is None:
            return self.blocked(ctx, "缺少营收或净利，无法建模")

        assumptions = dict(ctx.meta.get("assumptions") or {})
        g = float(assumptions.get("revenue_growth", 0.12))
        attrition = float(assumptions.get("growth_decay", 0.85))  # 增速逐年衰减系数
        net_margin = ni0 / rev0
        target_margin = float(assumptions.get("net_margin_target", net_margin))
        margin_step = (target_margin - net_margin) / 5
        asset_turnover = float(assumptions.get("asset_turnover", 1.0))
        leverage = float(assumptions.get("leverage", 0.45))
        cash_conversion = float(assumptions.get("cash_conversion", 1.05))
        capex_ratio = float(assumptions.get("capex_ratio", 0.07))
        da_ratio = float(assumptions.get("da_ratio", 0.05))
        tax_rate = float(assumptions.get("tax_rate", 0.15))

        rows: list[dict[str, Any]] = []
        fcff: list[float] = []
        rev = rev0
        margin = net_margin
        growth = g

        for year in range(1, 6):
            rev = rev * (1 + growth)
            margin = margin + margin_step
            ni = rev * margin
            assets = rev / asset_turnover
            liabilities = assets * leverage
            equity = assets - liabilities

            da = rev * da_ratio
            capex = rev * capex_ratio
            cfo = ni * cash_conversion
            ebit = ni / (1 - tax_rate) if tax_rate < 1 else ni
            nopat = ebit * (1 - tax_rate)
            delta_wc = (rev - rev / (1 + growth)) * 0.10
            fcf = nopat + da - capex - delta_wc

            rows.append(
                {
                    "year": year,
                    "revenue": round(rev, 2),
                    "net_income": round(ni, 2),
                    "net_margin": round(margin, 4),
                    "ebit": round(ebit, 2),
                    "total_assets": round(assets, 2),
                    "total_liabilities": round(liabilities, 2),
                    "total_equity": round(equity, 2),
                    "cfo": round(cfo, 2),
                    "capex": round(capex, 2),
                    "da": round(da, 2),
                    "fcff": round(fcf, 2),
                }
            )
            fcff.append(fcf)
            growth *= attrition

        ctx.put(
            "phase3.statements",
            {"years": [r["year"] for r in rows], "rows": rows, "unit": "本币"},
        )
        ctx.put("phase3.fcff", fcff)
        notes.append(f"五年预测：营收 CAGR {((rows[-1]['revenue'] / rev0) ** 0.2 - 1):.1%}")

        # 盈余质量：用当前年度快照
        snapshot = self._snapshot(ctx)
        if snapshot is not None:
            prior = self._prior_snapshot(ctx)
            scores = run_all(snapshot, prior)
            ctx.put("phase3.forensic", {k: v.to_dict() for k, v in scores.items()})
            for res in scores.values():
                notes.append(f"{res.model}：{res.verdict}")
        else:
            ctx.put("phase3.forensic", {})
            notes.append("缺少资产负债表科目，法务会计模型未执行")

        return PhaseResult(self.phase_id, self.name, artifacts=dict(ctx.artifacts), notes=notes)

    @staticmethod
    def _snapshot(ctx: PipelineContext) -> FinancialSnapshot | None:
        rev = ctx.num("revenue")
        ni = ctx.num("net_income")
        ta = ctx.num("total_assets")
        if rev is None or ni is None or ta is None:
            return None
        tl = ctx.num("total_liabilities", ta * 0.45) or ta * 0.45
        return FinancialSnapshot(
            year=0,
            revenue=rev,
            cogs=rev - (ctx.num("gross_margin", 0.3) or 0.3) * rev,
            net_income=ni,
            cfo=ctx.num("operating_cash_flow", ni * 1.05) or ni * 1.05,
            total_assets=ta,
            current_assets=ctx.num("current_assets", ta * 0.5) or ta * 0.5,
            current_liabilities=ctx.num("current_liabilities", ta * 0.25) or ta * 0.25,
            long_term_debt=ctx.num("long_term_debt", tl * 0.4) or tl * 0.4,
            total_liabilities=tl,
            total_equity=ta - tl,
            retained_earnings=ctx.num("retained_earnings", ta * 0.2) or ta * 0.2,
            ebit=ctx.num("ebit", ni * 1.2) or ni * 1.2,
            depreciation=ctx.num("depreciation", rev * 0.05) or rev * 0.05,
            sga=ctx.num("sga", rev * 0.12) or rev * 0.12,
            receivables=ctx.num("accounts_receivable", rev * 0.15) or rev * 0.15,
            ppe=ctx.num("ppe", ta * 0.35) or ta * 0.35,
            market_value_equity=ctx.num("market_cap"),
            shares_outstanding=ctx.num("shares_outstanding"),
        )

    @staticmethod
    def _prior_snapshot(ctx: PipelineContext) -> FinancialSnapshot | None:
        """由上一年度数值构造。缺失则返回 None（跳过两期模型）。"""
        rev = ctx.num("revenue_prior")
        ni = ctx.num("net_income_prior")
        ta = ctx.num("total_assets_prior")
        if rev is None or ni is None or ta is None:
            return None
        return FinancialSnapshot(
            year=-1,
            revenue=rev,
            cogs=rev * 0.7,
            net_income=ni,
            cfo=ni * 1.0,
            total_assets=ta,
            current_assets=ta * 0.5,
            current_liabilities=ta * 0.25,
            long_term_debt=ta * 0.18,
            total_liabilities=ta * 0.45,
            total_equity=ta * 0.55,
            retained_earnings=ta * 0.18,
            ebit=ni * 1.2,
            depreciation=rev * 0.05,
            sga=rev * 0.12,
            receivables=rev * 0.14,
            ppe=ta * 0.35,
            shares_outstanding=ctx.num("shares_outstanding"),
        )


# ==========================================================================
# P4 · 市场认知
# ==========================================================================


class Phase4Market(Phase):
    """只提问，不给结论。这是防止自我确认的关键约束。"""

    phase_id = "P4"
    name = "市场认知与定价假设"
    requires = ("phase0.one_liner", "phase3.statements")
    provides = (
        "phase4.nonconsensus",
        "phase4.bear_arguments",
        "phase4.bull_arguments",
        "phase4.counterfactuals",
        "phase4.cycles",
    )

    def run(self, ctx: PipelineContext) -> PhaseResult:
        missing = self.missing_requires(ctx)
        if missing:
            return self.skipped(ctx, f"缺少前置产物：{missing}")

        market: dict[str, Any] = dict(ctx.meta.get("market") or {})
        notes: list[str] = []

        nonconsensus = list(market.get("nonconsensus") or [])
        bear = list(market.get("bear_arguments") or [])
        bull = list(market.get("bull_arguments") or [])
        counterfactuals = list(market.get("counterfactuals") or [])

        ctx.put("phase4.nonconsensus", nonconsensus)
        ctx.put("phase4.bear_arguments", bear)
        ctx.put("phase4.bull_arguments", bull)
        ctx.put("phase4.counterfactuals", counterfactuals)
        ctx.put("phase4.cycles", dict(market.get("cycles") or {}))

        stage = (market.get("cycles") or {}).get("stage")
        if stage == "reflexivity":
            notes.append(
                "周期判定为反身性溢价：按漏斗终止规则，此处应停止分析并输出终止报告"
            )
        if len(nonconsensus) < 2:
            notes.append(f"非共识论点仅 {len(nonconsensus)} 条，GATE-15 将不通过")
        if len(bear) < len(bull):
            notes.append("空头论据少于多头，GATE-16 将不通过")

        return PhaseResult(self.phase_id, self.name, artifacts=dict(ctx.artifacts), notes=notes)


# ==========================================================================
# P5 · 估值定价
# ==========================================================================


class Phase5Valuation(Phase):
    """多锚交叉 + 反向反解。**不输出单一目标价。**"""

    phase_id = "P5"
    name = "估值与定价"
    requires = ("phase3.fcff",)
    provides = ("phase5.dcf", "phase5.reverse_dcf", "phase5.anchors", "phase5.peer")

    def run(self, ctx: PipelineContext) -> PhaseResult:
        missing = self.missing_requires(ctx)
        if missing:
            return self.skipped(ctx, f"缺少前置产物：{missing}")

        fcff: list[float] = list(ctx.get("phase3.fcff") or [])
        if not fcff:
            return self.blocked(ctx, "预测期现金流为空")

        val = dict(ctx.meta.get("valuation") or {})
        wacc = float(val.get("wacc", 0.10))
        terminal_g = float(val.get("terminal_g", 0.03))
        notes: list[str] = []

        # ---- 正向 DCF（仅作参考，不产目标价） ----
        shares = ctx.num("shares_outstanding")
        net_debt = float(val.get("net_debt", 0.0))
        res = equity_value(
            DCFInput(
                fcff_forecast=tuple(fcff),
                wacc=wacc,
                terminal_g=terminal_g,
                net_debt=net_debt,
                shares_outstanding=shares,
            )
        )
        ctx.put(
            "phase5.dcf",
            {
                "enterprise_value": res.enterprise_value,
                "equity_value": res.equity_value,
                "per_share": res.per_share,
                "terminal_share": res.terminal_share,
                "valid": res.valid,
                "note": res.note,
            },
        )
        if res.note:
            notes.append(res.note)

        # ---- 反向 DCF（核心） ----
        market_cap = ctx.num("market_cap")
        reverse_payload: dict[str, Any]
        if market_cap is None:
            reverse_payload = {
                "converged": False,
                "implied_g": None,
                "implied_wacc": None,
                "note": "缺少市值，无法反解（GATE-50 将不通过）",
            }
            notes.append("缺少市值字段，反向 DCF 未执行")
        else:
            target_ev = market_cap + net_debt
            rd = solve_implied_g(target_ev, fcff, wacc)
            growth_ref = val.get("growth_reference")
            reverse_payload = rd.to_gate_payload()
            reverse_payload["target_ev"] = target_ev
            reverse_payload["achieved_ev"] = rd.achieved_ev
            reverse_payload["interpretation"] = interpret(rd, growth_reference=growth_ref)
            notes.append(reverse_payload["interpretation"])
        ctx.put("phase5.reverse_dcf", reverse_payload)

        # ---- 多锚 ----
        anchors: dict[str, dict[str, Any]] = {}
        if res.per_share:
            anchors["正向DCF"] = {
                "method": "FCFF 折现",
                "value": round(res.per_share, 2),
                "role": "交叉验证",
            }
        peer_rows = list(val.get("peers") or [])
        if peer_rows and ctx.num("eps"):
            target = PeerMetrics(name=ctx.symbol, pe=ctx.num("pe_ttm"), is_target=True)
            peers = [
                PeerMetrics(
                    name=p.get("name", "?"),
                    pe=p.get("pe"),
                    pb=p.get("pb"),
                    ps=p.get("ps"),
                    roic=p.get("roic"),
                )
                for p in peer_rows
            ]
            pv = peer_valuation(target, peers, "pe")
            ctx.put("phase5.peer", pv.to_dict())
            if pv.peer_median:
                anchors["可比PE"] = {
                    "method": "同业中位数倍数",
                    "value": round(pv.peer_median * (ctx.num("eps") or 0), 2),
                    "role": "交叉验证",
                    "percentile": pv.percentile,
                }
            notes.extend(pv.warnings)
            notes.append(pv.note)

        ctx.put("phase5.anchors", anchors)

        return PhaseResult(self.phase_id, self.name, artifacts=dict(ctx.artifacts), notes=notes)


# ==========================================================================
# P6 · 执行方案
# ==========================================================================


class Phase6Execution(Phase):
    phase_id = "P6"
    name = "投资执行方案"
    requires = ("phase5.anchors",)
    provides = ("phase6.position", "phase6.scale_declaration")

    def run(self, ctx: PipelineContext) -> PhaseResult:
        missing = self.requires
        if any(not ctx.has(k) for k in missing):
            return self.skipped(ctx, f"缺少前置产物：{[k for k in missing if not ctx.has(k)]}")

        notes: list[str] = []
        exec_cfg = dict(ctx.meta.get("execution") or {})

        # 瓶颈等级与治理等级 → 仓位上限
        ranking = list(ctx.get("phase2.bottleneck_ranking") or [])
        grade = BottleneckGrade(ranking[0]["grade"]) if ranking else BottleneckGrade.L0_NONE
        if not ranking:
            notes.append("缺少瓶颈分级，仓位上限按无瓶颈处理")

        gov_raw = str(exec_cfg.get("governance", "C")).upper()
        gov = GovernanceGrade(gov_raw if gov_raw in {"A", "B", "C", "D"} else "C")
        env_raw = str(exec_cfg.get("environment", "B")).upper()
        env = EnvironmentGrade(env_raw if env_raw in {"A", "B", "C", "D"} else "B")

        cap = position_cap(grade, gov, env)
        entry = ctx.num("price")
        stop_pct = float(exec_cfg.get("stop_loss_pct", 0.12))
        stop = round(entry * (1 - stop_pct), 2) if entry else None

        position = {
            "bottleneck_grade": grade.value,
            "governance": gov.value,
            "environment": env.value,
            "max_pct": cap,
            "entry_price": entry,
            "stop_loss": stop,
            "open_new": env.allow_new,
            "targets": (ctx.get("phase0.exec_summary") or {}).get("target_range"),
        }
        ctx.put("phase6.position", position)

        horizon = str(exec_cfg.get("horizon", "medium"))
        primary = {"short": "price-action", "medium": "产业链瓶颈与盈利窗口", "long": "现金流与瓶颈等级"}[
            horizon if horizon in {"short", "medium", "long"} else "medium"
        ]
        ctx.put(
            "phase6.scale_declaration",
            {
                "horizon": horizon,
                "primary_module": primary,
                "conflicts": list(exec_cfg.get("conflicts") or []),
            },
        )

        notes.append(
            f"仓位上限 {cap:.0%}（瓶颈 {grade.value} × 治理 {gov.value} × 环境 {env.value}）"
        )
        if not env.allow_new:
            notes.append("环境评级为 D，禁止开新仓")

        return PhaseResult(self.phase_id, self.name, artifacts=dict(ctx.artifacts), notes=notes)


# ==========================================================================
# P7 · 最终裁决
# ==========================================================================


class Phase7Verdict(Phase):
    phase_id = "P7"
    name = "最终裁决"
    requires = ("phase6.position",)
    provides = ("report.verdict", "report.markdown")

    def run(self, ctx: PipelineContext) -> PhaseResult:
        missing = [k for k in self.requires if not ctx.has(k)]
        if missing:
            return self.skipped(ctx, f"缺少前置产物：{missing}")

        lines: list[str] = [f"# {ctx.symbol} 分析产出", ""]
        notes: list[str] = []

        one = ctx.get("phase0.one_liner")
        if one:
            lines.append(f"**一句话定义**：{one}")
            lines.append("")

        rank = ctx.get("phase2.bottleneck_ranking") or []
        if rank:
            top = rank[0]
            lines.append(
                f"**最强瓶颈层级**：{top['layer']}（{top['grade']}，"
                f"{len(top['evidence'])} 项证据）"
            )
            lines.append("")

        rd = ctx.get("phase5.reverse_dcf") or {}
        if rd.get("interpretation"):
            lines.append(f"**市场隐含预期**：{rd['interpretation']}")
            lines.append("")

        pos = ctx.get("phase6.position") or {}
        if pos:
            lines.append(
                f"**执行约束**：仓位上限 {pos.get('max_pct', 0):.0%}，"
                f"止损 {pos.get('stop_loss')}，环境 {pos.get('environment')}"
            )
            lines.append("")

        anchors = ctx.get("phase5.anchors") or {}
        if anchors:
            lines.append("**估值锚**")
            lines.append("")
            lines.append("| 锚 | 方法 | 数值 | 角色 |")
            lines.append("|---|---|---|---|")
            for name, spec in anchors.items():
                lines.append(
                    f"| {name} | {spec.get('method')} | {spec.get('value')} | {spec.get('role')} |"
                )

        ctx.put("report.verdict", {"bottleneck": rank[0] if rank else None, "position": pos})
        ctx.put("report.markdown", "\n".join(lines))
        notes.append("产出报告骨架；结论段落须在闸门通过后由上层填充")

        return PhaseResult(self.phase_id, self.name, artifacts=dict(ctx.artifacts), notes=notes)


def default_phases() -> list[Phase]:
    """标准八阶段序列。"""
    return [
        Phase0Profile(),
        Phase1Industry(),
        Phase2Penetration(),
        Phase3Financials(),
        Phase4Market(),
        Phase5Valuation(),
        Phase6Execution(),
        Phase7Verdict(),
    ]
