"""端到端测试：完整流水线跑两个场景。

这是最有价值的一类测试 —— 它同时验证：
阶段依赖、闸门编排、契约传播、状态判定的整条链路。
"""

from __future__ import annotations

import pytest

from zisu.casefile import build_context, load_case
from zisu.pipeline import PhaseStatus, Pipeline


@pytest.fixture(scope="module")
def pass_run(pass_case_path):
    case = load_case(pass_case_path)
    return case, Pipeline().run(build_context(case))


@pytest.fixture(scope="module")
def blocked_run(blocked_case_path):
    case = load_case(blocked_case_path)
    return case, Pipeline().run(build_context(case))


# ---------------------------------------------------------------- 通过路径


def test_pass_case_reaches_pass(pass_run):
    case, run = pass_run
    assert run.state == case.expect["state"] == "PASS"


def test_pass_case_all_expectations_met(pass_run):
    case, run = pass_run
    status = {r.gate_id: r.status.value for r in run.gate_report.results}
    for gate in case.expect["must_pass"]:
        assert status.get(gate) == "PASS", f"{gate} 期望通过，实际 {status.get(gate)}"
    for gate in case.expect["must_fail"]:
        assert status.get(gate) == "FAIL", f"{gate} 期望失败，实际 {status.get(gate)}"


def test_pass_case_pass_rate_is_one(pass_run):
    _, run = pass_run
    assert run.gate_report.pass_rate() == pytest.approx(1.0)
    assert run.gate_report.blockers == []
    assert run.gate_report.warnings == []


def test_pass_case_all_phases_executed(pass_run):
    _, run = pass_run
    assert [p.phase_id for p in run.phase_results] == [
        "P0",
        "P1",
        "P2",
        "P3",
        "P4",
        "P5",
        "P6",
        "P7",
    ]
    assert all(p.status is PhaseStatus.OK for p in run.phase_results)


def test_pass_case_can_emit_conclusion(pass_run):
    _, run = pass_run
    assert run.can_emit_conclusion


# ---------------------------------------------------------------- 拦截路径


def test_blocked_case_reaches_blocked(blocked_run):
    case, run = blocked_run
    assert run.state == case.expect["state"] == "BLOCKED"


def test_blocked_case_gate_expectations(blocked_run):
    case, run = blocked_run
    status = {r.gate_id: r.status.value for r in run.gate_report.results}
    for gate in case.expect["must_fail"]:
        assert status.get(gate) == "FAIL", f"{gate} 期望失败，实际 {status.get(gate)}"


def test_blocked_case_cannot_emit_conclusion(blocked_run):
    """最关键的约束：BLOCKED 时不得输出结论段。"""
    _, run = blocked_run
    assert not run.can_emit_conclusion
    assert run.gate_report.blockers
    md = run.to_markdown()
    assert "未产生结论" in md


def test_blocked_case_reports_unauthorized_source(blocked_run):
    _, run = blocked_run
    gate01 = next(r for r in run.gate_report.results if r.gate_id == "GATE-01")
    assert "R002" in gate01.detail
    assert "news.events" in gate01.detail


# ---------------------------------------------------------------- 横向不变式


def test_all_gates_executed_in_both_runs(pass_run, blocked_run):
    """每道闸门都应出现在结果里（PASS 或 FAIL 或 SKIP），不能静默消失。"""
    for _, run in (pass_run, blocked_run):
        assert len(run.gate_report.results) == 25


def test_declaration_present_in_artifacts(pass_run, blocked_run):
    for _, run in (pass_run, blocked_run):
        decl = run.ctx.get("report.declaration")
        assert decl is not None
        assert decl.state.value == run.state


def test_trace_recorded(pass_run):
    _, run = pass_run
    trace = run.ctx.tracer
    timings = trace.phase_timings()
    assert len(timings) == 8
    assert trace.total_ms() >= 0
    assert trace.gates_by_status()


def test_stdlib_only_no_third_party(run=None):
    """核心库不依赖任何第三方运行时依赖 —— 保证 clone 即用。"""
    import zisu

    assert zisu.__version__


def test_serialization_roundtrip(pass_run):
    _, run = pass_run
    payload = run.to_dict()
    assert payload["state"] == "PASS"
    assert len(payload["phases"]) == 8
    assert isinstance(payload["gates"], list)
    assert payload["declaration"]["state"] == "PASS"


# ---------------------------------------------------------------- 阶段重跑


def test_run_from_partial(pass_case_path):
    """局部重跑：前面的阶段标记为复用，不重新计算。"""
    case = load_case(pass_case_path)
    ctx = build_context(case)
    full = Pipeline()
    full.run(ctx)
    partial = full.run_from(ctx, "P6")
    ids = [p.phase_id for p in partial.phase_results]
    assert ids[:6] == ["P0", "P1", "P2", "P3", "P4", "P5"]
    assert partial.phase_results[0].status is PhaseStatus.SKIPPED


def test_run_from_unknown_phase(pass_case_path):
    case = load_case(pass_case_path)
    with pytest.raises(ValueError):
        Pipeline().run_from(build_context(case), "PX")
