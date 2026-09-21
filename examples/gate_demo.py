#!/usr/bin/env python
"""闸门拦截演示 —— 这是本项目最值得看的一段输出。

    PYTHONPATH=src python examples/gate_demo.py

做法：拿一个**本来能够通过全部闸门**的样本，依次往里面注入八类典型错误，
观察系统是否拦截、由哪道闸门拦截。

这些错误都对应真实发生过的场景。其中最典型的一条：
用通用网页检索去估计滚动市盈率，得到的口径与结构化数据库相差
+76% ~ +265%。事后复盘发现根因不在模型能力，而在约束的性质 ——
写在提示词里的约束是「提醒」，不是「门禁」。
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "evals"))

from injections import INJECTIONS, apply_injection  # noqa: E402

from zisu.casefile import build_context, load_case  # noqa: E402
from zisu.pipeline import Pipeline  # noqa: E402


def run_raw(raw: dict):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False)
        tmp = Path(fh.name)
    try:
        return Pipeline().run(build_context(load_case(tmp)))
    finally:
        tmp.unlink(missing_ok=True)


def main() -> int:
    base_path = ROOT / "examples" / "cases" / "pass_case.json"
    base = json.loads(base_path.read_text(encoding="utf-8"))

    print("=" * 74)
    print("对照：未注入任何错误时的状态")
    print("=" * 74)
    clean = run_raw(base)
    print(f"  状态 = {clean.state}   闸门通过率 = {clean.gate_report.pass_rate():.0%}")
    print()

    print("=" * 74)
    print("故障注入：八类真实事故，看能否挡住")
    print("=" * 74)
    print()

    caught = 0
    for name in INJECTIONS:
        mutated, note, expected = apply_injection(base, name)
        run = run_raw(mutated)

        status = {r.gate_id: r.status.value for r in run.gate_report.results}
        hit = [g for g in expected if status.get(g) == "FAIL"]
        missed = [g for g in expected if status.get(g) != "FAIL"]

        ok = run.state == "BLOCKED" and not missed
        caught += int(ok)

        print(f"{'✅' if ok else '❌'} {name}")
        print(f"   注入内容：{note}")
        print(f"   预期拦截：{', '.join(expected)}")
        print(f"   实际状态：{run.state}")
        if hit:
            for g in hit:
                gate = next(r for r in run.gate_report.results if r.gate_id == g)
                print(f"   {g} {gate.name} → {gate.detail[:84]}")
        if missed:
            print(f"   ⚠️ 未触发：{', '.join(missed)}")
        print()

    print("=" * 74)
    print(f"拦截结果：{caught}/{len(INJECTIONS)} 全部挡下")
    print("=" * 74)
    return 0 if caught == len(INJECTIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
