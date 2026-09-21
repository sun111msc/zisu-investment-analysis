#!/usr/bin/env bash
# 紫苏投资分析 — 一键脚本（Unix / macOS / Git Bash）
#
# 用法：
#   ./run.sh check          全量检查（lint + test + eval）
#   ./run.sh demo           演示八类错误如何被拦截
#   ./run.sh quickstart     跑一次完整分析
#   ./run.sh analyze <文件>  分析指定场景
#   ./run.sh gates          列出全部闸门
#   ./run.sh eval           跑评测
#   ./run.sh docs           本地启动文档站
#   ./run.sh clean          清理缓存

set -euo pipefail

PY="${PY:-python}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

banner() { printf '\n\033[1;36m▸ %s\033[0m\n' "$1"; }

ensure_deps() {
  if ! "$PY" -c "import pytest" >/dev/null 2>&1; then
    banner "安装开发依赖"
    "$PY" -m pip install -e ".[dev]" --quiet
  fi
}

cmd="${1:-help}"

case "$cmd" in
  check)
    ensure_deps
    banner "静态检查 (ruff)"
    "$PY" -m ruff check src tests evals
    banner "测试 (pytest)"
    "$PY" -m pytest -q
    banner "评测 (eval --strict)"
    PYTHONPATH=src "$PY" evals/run_eval.py --strict
    banner "全部通过"
    ;;

  quickstart)
    banner "完整分析演示"
    PYTHONPATH=src "$PY" examples/quickstart.py
    ;;

  demo)
    banner "闸门拦截演示"
    PYTHONPATH=src "$PY" examples/gate_demo.py
    ;;

  analyze)
    shift || true
    if [ -z "${1:-}" ]; then
      echo "用法: ./run.sh analyze <场景.json> [--json] [--out 文件]"
      exit 1
    fi
    PYTHONPATH=src "$PY" -m zisu.cli analyze "$@"
    ;;

  gates)
    PYTHONPATH=src "$PY" -m zisu.cli gates
    ;;

  eval)
    ensure_deps
    banner "运行评测"
    PYTHONPATH=src "$PY" evals/run_eval.py --json --out evals/reports/latest.md
    ;;

  docs)
    ensure_deps
    banner "启动文档站（http://127.0.0.1:8000）"
    "$PY" -m mkdocs serve
    ;;

  clean)
    banner "清理缓存"
    rm -rf .pytest_cache .ruff_cache .coverage htmlcov build dist site
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
    echo "完成"
    ;;

  help|*)
    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
    ;;
esac
