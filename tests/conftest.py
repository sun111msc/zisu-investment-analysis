"""pytest 共享夹具。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CASES_DIR = ROOT / "examples" / "cases"


@pytest.fixture(scope="session")
def pass_case_path() -> Path:
    return CASES_DIR / "pass_case.json"


@pytest.fixture(scope="session")
def blocked_case_path() -> Path:
    return CASES_DIR / "blocked_case.json"


@pytest.fixture
def registry():
    from zisu.datasources import build_registry

    return build_registry()


@pytest.fixture
def manifest():
    from zisu.datasources import CapabilityManifest

    m = CapabilityManifest(symbol="TEST.SZ")
    m.declare("market.quote.primary", {"price", "market_cap", "pe_ttm"})
    m.declare("financials.statements.primary", {"revenue", "net_income"})
    return m
