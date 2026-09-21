#!/usr/bin/env python
"""最小可运行示例。

    PYTHONPATH=src python examples/quickstart.py

演示三件事：
1. 如何声明能力清单（哪些数据源、覆盖哪些语义）；
2. 如何跑完八个阶段；
3. 如何读取三态结果。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from zisu.casefile import build_context, load_case  # noqa: E402
from zisu.pipeline import Pipeline  # noqa: E402


def main() -> int:
    case = load_case(ROOT / "examples" / "cases" / "pass_case.json")

    print("=" * 68)
    print(f"标的：{case.symbol}")
    print(f"场景：{case.title}")
    print("=" * 68)
    print()
    print("能力清单（分析前声明，未登记者禁止进入计划）：")
    for source_id, semantics in case.sources.items():
        print(f"  · {source_id}")
        print(f"      覆盖语义：{', '.join(semantics)}")
    print()

    ctx = build_context(case)
    run = Pipeline().run(ctx)

    print(f"状态：{run.state}")
    print(f"闸门通过率：{run.gate_report.pass_rate():.1%}")
    print()
    print("阶段执行：")
    for phase in run.phase_results:
        mark = {"OK": "OK  ", "SKIPPED": "SKIP", "BLOCKED": "BLK "}[phase.status.value]
        print(f"  [{mark}] {phase.phase_id} {phase.name}")
        for note in phase.notes[:2]:
            print(f"           └ {note}")
    print()
    print("市场隐含预期：")
    rd = run.ctx.get("phase5.reverse_dcf") or {}
    print(f"  {rd.get('interpretation', '—')}")
    print()

    if run.can_emit_conclusion:
        print("结论可输出。")
    else:
        print("结论被阻断，以下为阻断项：")
        for blocker in (run.declaration.blockers if run.declaration else []):
            print(f"  - {blocker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
