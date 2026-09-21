<div align="center">

# Zisu Investment Analysis

**An equity research methodology anchored on supply-chain physical bottlenecks**

*Chain penetration · Inverse valuation · Market microstructure · Disciplined execution*

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/methodology-15%20documents-informational.svg)](docs/00-体系总纲.md)
[![Gates](https://img.shields.io/badge/discipline%20gates-25-important.svg)](docs/engineering/gate-catalog.md)
[![Tests](https://img.shields.io/badge/tests-140%20passed-brightgreen.svg)](tests)
[![CI](https://github.com/sun111msc/zisu-investment-analysis/actions/workflows/ci.yml/badge.svg)](https://github.com/sun111msc/zisu-investment-analysis/actions/workflows/ci.yml)

[中文说明](README.md)

</div>

---

## What problem this solves

Equity analysis rarely fails because someone couldn't find a good company.
It fails because of three specific self-deceptions:

**One: mistaking sector tailwind for company skill.** A company growing revenue 40%
looks strong — until you notice the whole sector grew 45% and it actually lagged.
Hence: analyze the industry first, the company second.

**Two: treating narrative as fact.** "Trillion-dollar TAM" and "globally leading
technology" cannot be falsified. They aren't opinions — they're postures. Hence:
every core conclusion must be writable as a sentence that facts could overturn.

**Three: dressing assumptions as conclusions.** A price target precise to two
decimals draws 70% of its value from an assumed perpetual growth rate. That's your
own assumption wearing the costume of objectivity. Hence **reverse DCF**: instead
of asking "what is it worth", ask *"what must it achieve for today's price to be
justified"*.

---

## Three first principles

Every downstream rule derives from these. When a rule conflicts with a principle,
change the rule.

### 1. Profit is the only truth

The long-run anchor of price is a company's ability to generate cash. Narrative,
theme, and concept must ultimately land on profit and cash flow.

The moat test is **multiplicative**, not a weighted average — if any factor
approaches zero, the whole approaches zero:

```
Moat = Gross-margin stability × Cash conversion × Customer irreplaceability
```

| Factor | Criterion | Red line |
|---|---|---|
| Gross-margin stability | 5-yr std-dev / mean | > 15% |
| Cash conversion | Operating cash flow / Net income | Persistently < 0.5 |
| Customer irreplaceability | Largest customer share | > 30% |

**Why stability rather than level**: a company with a stable 20% gross margin for a
decade usually has a stronger moat than one that went from 60% to 35% in three years.
The former holds pricing power at this level; the latter once did.

### 2. No egg survives an overturned nest

Position ceiling is set by market environment, not by individual asset quality.
In a systemic decline all correlations converge to 1, diversification fails, and
low exposure is the only protection.

| Environment | Total ceiling | Open new |
|---|---|---|
| A Offensive | ≤100% | ✅ |
| B Neutral | ≤70% | ✅ |
| C Cautious | ≤30% | ⚠️ skip unless bottleneck grade sufficient |
| D Defensive | ≤10% | 🛑 prohibited |

### 3. A good stock without a catalyst is stagnant water

Capital needs a reason to enter. A cheap, high-quality asset with no trigger can
stay cheap for a long time.

```
No identifiable catalyst within 60 days      → downgrade one notch
All catalysts realized, none remaining       → mark "vacuum", reduce
Catalyst thesis falsified                    → exit unconditionally
```

---

## The core anchor: supply-chain physical bottlenecks

This is where the entire method converges. Multi-dimensional evidence collection,
then a single judgment:

> **Does this company occupy an irreplaceable physical stage in the supply chain?**

### Definition

A **bottleneck** is a stage where "remove it and the whole chain stops."
Three characteristics must hold simultaneously:

| Characteristic | Meaning | Counter-case |
|---|---|---|
| Irreplaceable | No equivalent substitute | Two or more suppliers → not a bottleneck |
| Concentrated supply | Extremely few global suppliers | Many suppliers → not a bottleneck |
| Certification barrier | Switching cost is very high | Freely switchable → not a bottleneck |

**Critical distinction: bottleneck ≠ market leader.** A leader has the largest share.
A bottleneck is a stage you cannot technically route around. A company can lead a
stage (40% share) that ten others can also serve — that makes it the biggest
competitor, not a bottleneck.

### Five-tier grading

Grading rests on **objectively verifiable facts**, not subjective impression:

| Tier | Criterion | Position ceiling |
|---|---|---|
| 🍃🍃🍃🍃🍃 | Sole global supplier + ≥2-yr certification | 25% |
| 🍃🍃🍃🍃 | 2 global suppliers + ≥2-yr certification | 20% |
| 🍃🍃🍃 | 2-3 global suppliers + proprietary process/material | 15% |
| 🍃🍃 | 3-4 global suppliers + single-product lead | 8% |
| 🍃 | 4+ suppliers but differentiated | 3% |

**"Global supplier" must be defined strictly**: mass production plus a customer
certification record. Lab samples, announced-but-unbuilt capacity, and
technically-capable-but-low-yield don't count.

Relax this definition and every company becomes a bottleneck.

### Automatic downgrade triggers

A bottleneck is a **state**, not an **attribute**:

```
□ A mass-producible substitute appears, or a second supplier scales
□ Customer contract expires without renewal
□ Controlling shareholder sells down, or pledge ratio exceeds 40%
□ Industry capex grows > 50% YoY (capacity race warning)
```

→ Full method: [04 · Supply-Chain Bottleneck Methodology](docs/04-产业链瓶颈方法论.md) *(Chinese)*

---

## The eight-phase pipeline

```
        ┌──────────────────┐
        │ P7 Final verdict │  ← one falsifiable sentence
        ├──────────────────┤
        │ P6 Execution     │  ← size, price, exit
        ├──────────────────┤
        │ P5 Valuation     │  ← implied-expectation solve + multi-anchor
        ├──────────────────┤
        │ P4 Market view   │  ← where might the market be wrong (questions only)
        ├──────────────────┤
        │ P3 Financials    │  ← three-statement model + earnings quality
        ├──────────────────┤
        │ P2 Penetration   │  ← which chain layer captures the profit
        ├──────────────────┤
        │ P1 Industry      │  ← how big, what structure
        ├──────────────────┤
        │ P0 Company       │  ← what it actually does
        └──────────────────┘
          factual substrate
```

**Why an upright pyramid**: an earlier version put "market mispricing" first. Every
subsequent chapter then got anchored to that opening judgment — you involuntarily
hunt for confirming evidence. With facts first, P4's "is the market wrong" becomes
**independent** of the preceding analysis.

### Five depth rules

"Depth" is the most abused and least verifiable word in research. So it is turned
into checkable conditions:

| Rule | Requirement | Verification |
|---|---|---|
| **Zero** Facts first | Business breakdown presented in full, once | Weighted margin deviation < 2pp |
| **One** Questions only | No conclusive phrasing in P4 | Search for "we believe" |
| **Two** Process-level × value × exclusion | ≥7 process layers + value + ≥5 exclusions | Layer named "industry" fails |
| **Three** Capacity→revenue bridge | Units × ASP × delivery × acceptance | All five fields present |
| **Four** Forced non-consensus | ≥2 falsifiable non-consensus claims | Disagrees with mainstream |
| **Five** Valuation switch triggers | Implied assumptions + ≥2 triggers | Not circular reasoning |

### Five termination points

Not every asset deserves a full analysis:

| Point | Trigger | Meaning |
|---|---|---|
| **T0** | Can't explain the business to a layperson in one paragraph | Not understanding = not investing |
| **T1** | Cycle assessment = "reflexivity premium" | Valuation detached from fundamentals |
| **T2** | Fatal chokepoint with no alternative | Uncontrollable systemic risk |
| **T3** | Bear case: ≥5 questions cannot be rebutted | Counter-argument dominates |
| **T4** | Margin of safety < 10% | No risk compensation at this price |

**Termination ≠ rejection.** Each point carries conditions that would restart the
analysis.

→ Full flow: [02 · Analysis Pipeline](docs/02-分析流程-八阶段正金字塔.md) *(Chinese)*

---

## Four distinctive methods

### 1. Reverse DCF — not "what is it worth" but "what must it achieve"

A forward DCF output is a price, but 60-85% of it comes from an assumed perpetual
growth rate. Dressing that assumption as a number produces false precision and
unfalsifiability.

```
Forward:  "I think it's worth 41.2"          → opinion, untestable
Reverse:  "Today's price implies 3.5% perpetual growth"  → factual constraint, testable
```

The second immediately generates a **testable sub-question**: is 3.5% credible?
Against history, peers, and capacity plans — that question has an answer.

**Three hard constraints**:

```
① No price target (outputs implied growth and discount rate; no price field)
② Non-convergence IS the conclusion (price exceeds value under any reasonable
   parameters = cash-flow assumptions cannot explain it)
③ No pseudo-solution (hitting the iteration limit returns "not converged",
   never an approximation)
```

### 2. Market structure — how price actually forms

Fundamentals answer "what is it worth". This layer answers "why isn't the price that".

**Miller pricing framework**: when disagreement is high, shorting is constrained,
and float is thin, price is **systematically** set by the most optimistic buyer
rather than by an equilibrium.

**Five-layer sell-side decomposition** — tradable shares sorted by likelihood of sale:

| Layer | Composition | Typical share | Predictability |
|---|---|---|---|
| 🏔️ Non-selling | Controlling holders, state holders, pre-IPO | 25-55% | ★★★★★ |
| 🔒 Locked | Passive index funds, placements, restricted shares | 5-20% | ★★★★ |
| 🧊 Long-hold | Long-only institutions, foreign holders | 5-15% | ★★★ |
| 🌫️ Float | Active funds, traders, quants, retail | 15-40% | ★★ |

```
Float < 20%   → 💀 near-total dormancy; price detached from supply/demand
Float 20-40%  → 🔴 very thin; small capital moves large moves
```

**Recognition staircase**: institutional adoption proceeds in three steps, each
with a different risk-return profile.

| Step | Characteristic | Action |
|---|---|---|
| 1 Probing | 2-3x up, <50 funds holding | ✅ enter |
| 2 Recognition | 5-10x up, 200-500 funds | ⚠️ slow down |
| 3 Crowded | 20-50x up, top-10 holding | ⛔ stop adding |

**Marginal buyer succession**: long bull runs are completed by successive waves of
different buyers — the previous wave usually exits before the next arrives. Tracked
by reviewing the top-10 float shareholder list across three consecutive periods.

→ Full method: [10 · Market Structure and Pricing](docs/10-市场结构与定价机制.md) *(Chinese)*

### 3. Cycle assessment — detecting the growth-to-cycle inflection

The same company graded as growth vs. cycle yields entirely different valuation
methods — results can differ by 2x.

**Three-dimensional test**:

| Dimension | Criterion | True growth |
|---|---|---|
| Industry penetration | S-curve position | 5-30% (acceleration) |
| Capex intensity | Capex / Revenue | < 20% |
| Barrier type | Nature of the moat | Technology or certification |

**Five warning signals (≥3 → growth becoming cyclical, exit immediately)**:

```
① Penetration > 30% and revenue growth decelerating for 2 quarters
② Industry capacity +20% YoY
③ Gross margin declining for 2 consecutive years
④ Capex / Revenue > 15%
⑤ Gross margin down > 1pp YoY
```

**Signal ⑤ is the earliest**: a new competitor enters → price is affected first
(margin) → then share (revenue) → then profit. Gross margin is the leading indicator.

→ Full method: [05 · Cycle vs Growth](docs/05-周期与成长判定.md) *(Chinese)*

### 4. Execution discipline — right call, wrong size = wrong call

```
 1%  — no single trade risks more than 1% of capital
2:1  — minimum risk-reward ratio
 3   — cut size after 3 consecutive losses, stop after 5
15%  — drawdown warning line
20%  — single position ceiling
70%  — total exposure ceiling
 ∞   — don't predict, only respond; missing out costs nothing
```

**Position size takes the MINIMUM of multiple constraints, not a weighted average**:

```
size = min(
    Kelly × 0.25,          ← never full Kelly
    volatility-adjusted,
    drawdown-scaled,
    1%-risk-limit,
    single-position cap 20%,
    environment ceiling
)
```

**Why never full Kelly**: at 60% win rate and 2:1 reward, Kelly = 40% — but five
consecutive losses would erase 92% of capital. Quarter-Kelly is the default.

→ Full method: [12 · Execution and Risk](docs/12-执行体系与风控纪律.md) *(Chinese)*

---

## Methodology documents

15 documents, Chinese primary. Each covers one layer of the framework.

| # | Document | Content |
|---|---|---|
| 00 | [System Overview](docs/00-体系总纲.md) | Framework, six-layer funnel, eleven modules, boundaries |
| 01 | [Philosophy and First Principles](docs/01-分析哲学与第一性原理.md) | Principles, cognitive-bias introspection, three prohibitions |
| 02 | [Analysis Pipeline](docs/02-分析流程-八阶段正金字塔.md) | Phase-by-phase + five termination points |
| 03 | [Five Depth Rules](docs/03-深度穿透五铁律.md) | Verifiable standards for depth |
| 04 | [Bottleneck Methodology](docs/04-产业链瓶颈方法论.md) | Grading, BOM decomposition, exclusion matrix |
| 05 | [Cycle vs Growth](docs/05-周期与成长判定.md) | Three-dimensional test, five warning signals |
| 06 | [Valuation](docs/06-估值方法论.md) | Reverse DCF, multi-anchor, SOTP, relative value |
| 07 | [Financial Truth](docs/07-财务真相与盈余质量.md) | Three-statement model, forensic accounting |
| 08 | [Management and Governance](docs/08-管理层与治理评估.md) | Five-dimension scorecard, capital allocation |
| 09 | [Industry Structure](docs/09-行业结构与护城河.md) | Five forces, moat scoring, life cycle |
| 10 | [Market Structure](docs/10-市场结构与定价机制.md) | Miller pricing, sell-side depth, staircase |
| 11 | [A-Share Ecosystem](docs/11-A股市场生态洞察.md) | Liquidity dimensions, sentiment cycle, rules |
| 12 | [Execution and Risk](docs/12-执行体系与风控纪律.md) | Six-layer risk control, position math |
| 13 | [Report Standards](docs/13-研究报告标准与自检清单.md) | 14-chapter template, pre-publication checklist |
| 14 | [End-to-End Flow](docs/14-端到端决策流程.md) | From screening to position management |

---

## Engineering implementation (supporting material)

The parts of the methodology most easily violated — not "couldn't think of it" but
"thought of it and couldn't hold to it" — are implemented as executable checks.

**For example**:

> I once estimated a trailing P/E via generic web search. The result deviated from
> structured data by **+76% to +265%**. Post-mortem: the prompt clearly said
> "valuation data must come from the database" — the constraint was explicit, but
> it was a **reminder**, not a **gate**.

After the rewrite, source constraints became compile-time registration: unregistered
sources are rejected before analysis starts.

```
$ python examples/gate_demo.py

✅ unauthorized_source   news source authorized to supply valuation → GATE-01
✅ unregistered_source   unregistered data source introduced        → GATE-01
✅ zero_fill             missing data filled with 0                 → GATE-41
✅ single_line           business breakdown skipped                 → GATE-11
✅ weak_bear             token bear argument                        → GATE-16
✅ no_market_cap         valuation without market cap               → GATE-50
✅ shallow_chain         chain reduced to sector labels             → GATE-12
✅ zero_peers            single-anchor valuation                    → GATE-51

Result: 8/8 blocked
```

| Item | Detail |
|---|---|
| Gates | 25, across five quality stages (mapping to the rules above) |
| Tests | 140 covering contracts, gates, valuation math, pipeline |
| Evaluation | 8 fault injections, 8/8 catch rate; CI runs `--strict` |
| Dependencies | Zero runtime third-party dependencies |

**Technical documentation**: [architecture](docs/engineering/architecture.md) ·
[gate catalogue](docs/engineering/gate-catalog.md) ·
[value contracts](docs/engineering/contract-spec.md) ·
[engineering principles](docs/engineering/principles.md) ·
[quickstart](docs/engineering/quickstart.md) ·
[ADRs](docs/engineering/adr/)

```bash
git clone https://github.com/sun111msc/zisu-investment-analysis.git
pip install -e ".[dev]"
python examples/quickstart.py    # run a full analysis
python examples/gate_demo.py     # watch eight failures get caught
make check                       # lint + test + eval
```

---

## Scope and boundaries

**An explicit boundary is more valuable than vague universality.**

| Dimension | Applies to |
|---|---|
| Market | A-shares primarily; Hong Kong and US by reference |
| Sector | Tech manufacturing: semiconductors, optical, new energy, robotics, advanced materials |
| Holding period | 1 month – 2 years |
| Precondition | An identifiable supply-chain bottleneck exists |

**Does not apply to**:

| Type | Reason |
|---|---|
| Short supply chains (consumer brands, financials, platforms) | Bottleneck concept doesn't hold |
| Futures, FX, crypto | No corporate fundamentals |
| High-frequency strategies | Wrong time scale |
| Names with < ¥5M average daily turnover | Insufficient liquidity; no framework applies |

**That last row matters**: a name trading ¥3M a day cannot support establishing or
exiting a meaningful position, however good the fundamentals. It should be skipped
*before* analysis begins.

---

## Disclaimer

**This project is open-source software for research and engineering demonstration.
It does not constitute investment advice of any kind.**

The repository contains no real accounts, holdings, capital, or trade orders; all
example data is fictional placeholder content. Thresholds and parameters in the
methodology illustrate judgment logic and are not recommendations on any specific
security. See [DISCLAIMER.md](DISCLAIMER.md) for the full statement.

---

<div align="center">

Apache-2.0 · 15 methodology documents · 25 discipline gates · [中文](README.md)

</div>
