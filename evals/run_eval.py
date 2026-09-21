#!/usr/bin/env python
"""评测执行器。

::

    PYTHONPATH=src python evals/run_eval.py
    PYTHONPATH=src python evals/run_eval.py --out evals/reports/latest.md
    PYTHONPATH=src python evals/run_eval.py --update-baseline
    PYTHONPATH=src python evals/run_eval.py --strict   # 劣化则退出码 1

评测集 = 基线样本 + 故障注入变体。基线样本证明「能跑」，
注入样本证明「跑错时会挡住」。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "evals"))

from injections import INJECTIONS, apply_injection  # noqa: E402
from rubric import (  # noqa: E402
    EvalResult,
    evaluate,
    load_baseline,
    save_baseline,
    summarize,
)

from zisu.casefile import CaseFile, build_context, load_case  # noqa: E402
from zisu.pipeline import Pipeline  # noqa: E402

CASES_DIR = ROOT / "examples" / "cases"
BASELINE_PATH = ROOT / "evals" / "baselines.json"
REPORTS_DIR = ROOT / "evals" / "reports"

BASELINE_CASES = ["pass_case", "blocked_case"]


def _run_case(case: CaseFile):
    ctx = build_context(case)
    return Pipeline().run(ctx)


def _run_from_raw(raw: dict) -> object:
    """把内存中的样本写成临时文件后执行 —— 复用同一条加载路径，避免两套逻辑。"""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False)
        tmp = Path(fh.name)
    try:
        return _run_case(load_case(tmp))
    finally:
        tmp.unlink(missing_ok=True)


def run_all() -> list[EvalResult]:
    results: list[EvalResult] = []

    base_raw = (CASES_DIR / "pass_case.json").read_text(encoding="utf-8")
    base_dict = json.loads(base_raw)

    # 1) 基线样本
    for name in BASELINE_CASES:
        case = load_case(CASES_DIR / f"{name}.json")
        run = _run_case(case)
        results.append(evaluate(name, case.expect, run, kind="baseline"))

    # 2) 故障注入
    for name in INJECTIONS:
        mutated, note, expected_gates = apply_injection(base_dict, name)
        run = _run_from_raw(mutated)
        expected = {"state": "BLOCKED", "must_pass": [], "must_fail": expected_gates}
        res = evaluate(f"inject:{name}", expected, run, kind="injection")
        res.note = note
        results.append(res)

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运行紫苏投资分析评测")
    parser.add_argument("--out", help="报告输出路径")
    parser.add_argument("--update-baseline", action="store_true", help="把当前指标写为基线")
    parser.add_argument("--strict", action="store_true", help="任何指标劣化即以退出码 1 结束")
    parser.add_argument("--json", action="store_true", help="同时输出机器可读结果")
    args = parser.parse_args(argv)

    results = run_all()
    summary = summarize(results)
    metrics = summary.metrics()
    baseline = load_baseline(BASELINE_PATH)

    report = ["# 紫苏投资分析 · 评测报告", ""]
    report.append(f"样本数：{len(results)}（基线 {len(BASELINE_CASES)} + 注入 {len(INJECTIONS)}）")
    report.append("")
    report.append(summary.to_markdown(baseline or None))

    degradations = summary.compare(baseline) if baseline else []
    if baseline:
        report.append("")
        if degradations:
            report.append("## ⚠️ 基线劣化")
            report.append("")
            report.extend(f"- {d}" for d in degradations)
        else:
            report.append("## ✅ 无基线劣化")
        report.append("")

    text = "\n".join(report)
    print(text)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"\n报告已写入 {out}")

    if args.json:
        payload = {
            "metrics": metrics,
            "results": [r.to_dict() for r in results],
            "degradations": degradations,
        }
        (REPORTS_DIR / "latest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if args.update_baseline:
        save_baseline(BASELINE_PATH, metrics)
        print(f"基线已更新：{BASELINE_PATH}")
        return 0

    if args.strict and degradations:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
