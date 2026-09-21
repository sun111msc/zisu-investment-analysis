"""命令行入口。

::

    zisu analyze examples/cases/pass_case.json
    zisu analyze examples/cases/blocked_case.json --json
    zisu gates
    zisu version
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from zisu import __version__
from zisu.casefile import build_context, load_case
from zisu.gates import ALL_RULES
from zisu.pipeline import Pipeline

__all__ = ["main"]


def _cmd_analyze(args: argparse.Namespace) -> int:
    case = load_case(args.input)
    ctx = build_context(
        case,
        audit_path=(Path(args.audit) if args.audit else None),
    )
    run = Pipeline().run(ctx)

    if args.json:
        payload = run.to_dict()
        payload["case"] = {"title": case.title, "description": case.description}
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        header = [
            f"# 紫苏投资分析 · {case.symbol}",
            "",
            f"> {case.title}" if case.title else "",
            f"> {case.description}" if case.description else "",
            "",
        ]
        text = "\n".join(x for x in header if x is not None) + "\n" + run.to_markdown()

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"已写入 {args.out}")
    else:
        print(text)

    if args.fail_on_block and run.state == "BLOCKED":
        return 2
    return 0


def _cmd_gates(_: argparse.Namespace) -> int:
    print(f"已装载闸门 {len(ALL_RULES)} 道\n")
    print("| 编号 | 名称 | 阶段 | 阻断 |")
    print("|---|---|---|---|")
    for gate_id, name, stage, _rule, blocking in ALL_RULES:
        print(f"| {gate_id} | {name} | {stage.value} | {'是' if blocking else '否'} |")
    return 0


def _cmd_version(_: argparse.Namespace) -> int:
    print(f"zisu-investment-analysis {__version__}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zisu",
        description="紫苏投资分析 —— 契约驱动、失败关闭的股票深度分析流水线",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="执行一次分析")
    p_analyze.add_argument("input", help="场景 JSON 文件路径")
    p_analyze.add_argument("--out", help="输出文件路径（默认打印到标准输出）")
    p_analyze.add_argument("--json", action="store_true", help="以 JSON 输出完整结果")
    p_analyze.add_argument("--audit", help="取数审计日志写入路径")
    p_analyze.add_argument(
        "--fail-on-block",
        action="store_true",
        help="状态为 BLOCKED 时以退出码 2 结束（供 CI 使用）",
    )
    p_analyze.set_defaults(func=_cmd_analyze)

    p_gates = sub.add_parser("gates", help="列出全部闸门")
    p_gates.set_defaults(func=_cmd_gates)

    p_ver = sub.add_parser("version", help="打印版本")
    p_ver.set_defaults(func=_cmd_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
