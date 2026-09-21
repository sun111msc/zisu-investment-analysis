.PHONY: help install check lint test cov eval eval-out demo docs clean

PY ?= python

help:
	@echo "make install  安装开发依赖"
	@echo "make check    lint + test + eval 全量检查"
	@echo "make lint     ruff 静态检查"
	@echo "make test     单元与集成测试"
	@echo "make cov      带覆盖率测试"
	@echo "make eval     运行评测并输出报告"
	@echo "make eval-out 评测并写入 evals/reports/"
	@echo "make demo     运行闸门拦截演示"
	@echo "make docs     本地启动文档站"
	@echo "make clean    清理缓存"

install:
	$(PY) -m pip install -e ".[dev]"

check: lint test eval

lint:
	$(PY) -m ruff check src tests evals

test:
	$(PY) -m pytest

cov:
	$(PY) -m pytest --cov=zisu --cov-report=term-missing

eval:
	PYTHONPATH=src $(PY) evals/run_eval.py

eval-out:
	PYTHONPATH=src $(PY) evals/run_eval.py --json --out evals/reports/latest.md

demo:
	PYTHONPATH=src $(PY) examples/gate_demo.py

docs:
	$(PY) -m mkdocs serve

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov build dist
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
