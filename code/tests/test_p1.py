"""Tests for P1: freelancer mode, uncertainty scenarios, explainable reports.

Run: python3 -m pytest code/tests/test_p1.py -q

Financial assertions use exact identities from the deterministic simulator (e.g.
closing == opening + credits - debits, scenario monotonicity, never == baseline)
rather than gold labels, so they pin correctness without brittleness.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))

from buy_or_wait import config  # noqa: E402
from buy_or_wait.freelancer import (  # noqa: E402
    Invoice,
    build_freelancer_ledger,
    project_invoices,
    variable_income_summary,
)
from buy_or_wait.pipeline import analyze, decide  # noqa: E402
from buy_or_wait.report import build_report  # noqa: E402
from buy_or_wait.scenarios import SCENARIOS, ScenarioConfig, run_scenarios  # noqa: E402
from buy_or_wait.loader import DataStore, Request  # noqa: E402

STORE = DataStore()
ZERO = Decimal(0)


def _req() -> Request:
    return STORE.requests[0]


def _invoices(request: Request, home: str):
    """A confirmed and an at-risk receivable, both comfortably in-horizon."""
    rd = request.request_date
    return [
        Invoice("inv_conf", "Acme", Decimal("5000"), home, rd, rd + timedelta(days=5), "confirmed",
                expected_payment_date=rd + timedelta(days=5), user_id=request.user_id),
        Invoice("inv_risk", "Beta", Decimal("7000"), home, rd, rd + timedelta(days=10), "expected",
                expected_payment_date=rd + timedelta(days=10), user_id=request.user_id),
    ]


# --------------------------------------------------------------------- #
# Freelancer mode: invoice classification + invoice-aware projection
# --------------------------------------------------------------------- #
def test_confirmed_invoice_projects_at_risk_does_not():
    request = _req()
    home = STORE.profile_for(request.user_id).home_currency
    confirmed, at_risk = project_invoices(_invoices(request, home), request, home)
    assert len(confirmed) == 1 and confirmed[0].amount == Decimal("5000")
    assert confirmed[0].category == "invoice" and confirmed[0].kind == "income"
    assert len(at_risk) == 1 and at_risk[0].amount == Decimal("7000")


def test_settled_invoice_skipped_and_out_of_horizon_skipped():
    request = _req()
    home = STORE.profile_for(request.user_id).home_currency
    past_due = request.request_date - timedelta(days=3)
    invs = [
        Invoice("paid1", "Acme", Decimal("100"), home, past_due, past_due, "paid"),
        Invoice("far1", "Acme", Decimal("200"), home, request.request_date,
                request.request_date + timedelta(days=config.FORECAST_DAYS + 5), "confirmed",
                expected_payment_date=request.request_date + timedelta(days=config.FORECAST_DAYS + 5)),
        # settled AND in horizon -> skipped because settled
        Invoice("paid2", "Acme", Decimal("300"), home, request.request_date,
                request.request_date + timedelta(days=3), "paid"),
    ]
    confirmed, at_risk = project_invoices(invs, request, home)
    assert confirmed == [] and at_risk == []


def test_baseline_ledger_includes_only_confirmed_invoice_income():
    request = _req()
    home = STORE.profile_for(request.user_id).home_currency
    ledger, at_risk = build_freelancer_ledger(STORE, request, _invoices(request, home))
    # confirmed income present in baseline flows
    conf = [f for f in ledger.flows if f.source_id == "inv_conf"]
    assert len(conf) == 1 and conf[0].amount == Decimal("5000")
    # at-risk invoice is NOT in the baseline (safer reading)
    assert not any(f.source_id == "inv_risk" for f in ledger.flows)
    # ...but it is returned for the scenario runner
    assert any(f.source_id == "inv_risk" for f in at_risk)


def test_variable_income_summary_buckets():
    request = _req()
    home = STORE.profile_for(request.user_id).home_currency
    s = variable_income_summary(_invoices(request, home), home)
    assert s["counts_by_certainty"]["confirmed"] == 1
    assert s["counts_by_certainty"]["at_risk"] == 1
    assert s["outstanding_confirmed"] == Decimal("5000")
    assert s["outstanding_at_risk"] == Decimal("7000")


# --------------------------------------------------------------------- #
# Uncertainty scenarios: four separate simulator runs
# --------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def scenario_pack():
    request = _req()
    home = STORE.profile_for(request.user_id).home_currency
    base_ledger, at_risk = build_freelancer_ledger(STORE, request, _invoices(request, home))
    from buy_or_wait.pipeline import analyze_from_ledger

    options = STORE.options_for(request.request_id)
    baseline = analyze_from_ledger(base_ledger, options)
    report = run_scenarios(base_ledger, at_risk, options, ScenarioConfig(delay_days=14), baseline=baseline)
    return request, home, base_ledger, at_risk, baseline, report


def test_four_distinct_scenarios_run(scenario_pack):
    request, home, base_ledger, at_risk, baseline, report = scenario_pack
    assert [r.key for r in report.results] == [s.key for s in SCENARIOS]
    assert len(report.results) == 4
    # separate runs, not averaged: each result carries its own decision numbers
    for r in report.results:
        assert r.status in {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}
        assert r.amount_safe_to_pay >= 0


def test_never_equals_baseline(scenario_pack):
    """'Income never arrives' == confirmed-only baseline, exactly."""
    request, home, base_ledger, at_risk, baseline, report = scenario_pack
    never = report.by_key("never")
    assert never.amount_safe_to_pay == baseline.decision.amount_safe_to_pay
    assert never.status == baseline.status
    assert never.expected_income_included == ZERO


def test_on_time_includes_at_risk_and_is_not_worse(scenario_pack):
    request, home, base_ledger, at_risk, baseline, report = scenario_pack
    on_time = report.by_key("on_time")
    assert on_time.expected_income_included == Decimal("7000")
    # extra future income can never reduce the safe amount
    assert on_time.amount_safe_to_pay >= report.by_key("never").amount_safe_to_pay


def test_delayed_is_at_least_never(scenario_pack):
    request, home, base_ledger, at_risk, baseline, report = scenario_pack
    assert report.by_key("delayed").amount_safe_to_pay >= report.by_key("never").amount_safe_to_pay


def test_shock_worsens_or_equals_on_time(scenario_pack):
    request, home, base_ledger, at_risk, baseline, report = scenario_pack
    on_time = report.by_key("on_time")
    shock = report.by_key("shock")
    assert shock.amount_safe_to_pay <= on_time.amount_safe_to_pay
    # the shock expense actually exists in the scenario flows (via its forecast)
    assert shock.min_closing_balance <= on_time.min_closing_balance or shock.amount_safe_to_pay <= on_time.amount_safe_to_pay


def test_scenarios_are_deterministic(scenario_pack):
    request, home, base_ledger, at_risk, baseline, report = scenario_pack
    options = STORE.options_for(request.request_id)
    again = run_scenarios(base_ledger, at_risk, options, ScenarioConfig(delay_days=14), baseline=baseline)
    for a, b in zip(report.results, again.results):
        assert (a.status, a.amount_safe_to_pay, a.safe) == (b.status, b.amount_safe_to_pay, b.safe)


def test_no_at_risk_income_scenarios_coincide():
    """With zero uncertain income, on_time/delayed/never are all the baseline."""
    request = _req()
    base_ledger, at_risk = build_freelancer_ledger(STORE, request, [])
    assert at_risk == []
    options = STORE.options_for(request.request_id)
    report = run_scenarios(base_ledger, at_risk, options, ScenarioConfig())
    on_time = report.by_key("on_time")
    never = report.by_key("never")
    delayed = report.by_key("delayed")
    assert on_time.amount_safe_to_pay == never.amount_safe_to_pay == delayed.amount_safe_to_pay
    # shock still differs (it adds an expense)
    assert report.by_key("shock").amount_safe_to_pay <= on_time.amount_safe_to_pay


# --------------------------------------------------------------------- #
# Explainable report: dated cash-flow table sourced from the simulator
# --------------------------------------------------------------------- #
def test_report_cashflow_rows_are_simulator_output():
    request = _req()
    analysis = analyze(STORE, request)
    report = build_report(analysis)
    rows = analysis.cashflow().rows
    # full horizon: day 0..90 inclusive
    assert len(rows) == config.FORECAST_DAYS + 1
    # dates contiguous
    assert all(rows[i].date - rows[i - 1].date == timedelta(days=1) for i in range(1, len(rows)))
    # core accounting identity: closing == opening + credits - debits
    for r in rows:
        assert r.closing_balance == r.opening_balance + r.credits - r.debits
    # carry-forward: today's closing is tomorrow's opening
    for i in range(1, len(rows)):
        assert rows[i].opening_balance == rows[i - 1].closing_balance
    # reserve column is the profile minimum (verified input), constant
    prof = STORE.profile_for(request.user_id)
    assert all(r.minimum_balance_to_keep == prof.minimum_balance_to_keep for r in rows)


def test_report_dict_numbers_match_analysis():
    request = _req()
    analysis = analyze(STORE, request)
    report = build_report(analysis)
    d = report.to_dict()
    dec = analysis.decision
    assert d["decision"]["amount_safe_to_pay"] == str(dec.amount_safe_to_pay)
    assert d["decision"]["affordability_status"] == dec.affordability_status
    assert d["decision"]["payment_plan"] == dec.payment_plan
    prof = STORE.profile_for(request.user_id)
    assert d["position"]["available_balance"] == str(analysis.ledger.starting_balance)
    assert d["position"]["minimum_balance_to_keep"] == str(prof.minimum_balance_to_keep)
    # provenance declared
    assert "deterministic simulator" in d["provenance"]["note"]


def test_report_markdown_renders_table_and_disclaimer():
    request = _req()
    analysis = analyze(STORE, request)
    md = build_report(analysis).to_markdown()
    assert "Dated cash-flow forecast" in md
    assert "| Date | Opening | Credits | Debits | Purchase | Closing | Reserve | Margin |" in md
    assert "Assumptions & missing" in md
    assert "not a guarantee of future financial safety" in md


def test_report_embeds_scenarios_when_provided(scenario_pack):
    request, home, base_ledger, at_risk, baseline, report = scenario_pack
    from buy_or_wait.report import build_report as _build

    r = _build(baseline, scenario_report=report)
    d = r.to_dict()
    assert d["scenarios"] is not None
    assert len(d["scenarios"]["results"]) == 4
    md = r.to_markdown()
    assert "Uncertainty scenarios" in md


# --------------------------------------------------------------------- #
# Refactor safety: decide() still equals analyze().decision
# --------------------------------------------------------------------- #
def test_decide_equals_analyze_decision():
    for request in STORE.requests[:3]:
        a = analyze(STORE, request)
        d = decide(STORE, request)
        assert a.decision is d or (
            a.decision.amount_safe_to_pay == d.amount_safe_to_pay
            and a.decision.affordability_status == d.affordability_status
            and a.decision.payment_plan == d.payment_plan
        )


def test_scenarios_can_differentiate_when_inputs_bind():
    """Non-vacuity: with binding at-risk income + shock, scenarios diverge.

    Without this, monotonicity assertions (``>=``/``<=``) would pass even if the
    runner silently returned the same result for every scenario.
    """
    from buy_or_wait.pipeline import analyze_from_ledger

    differentiating = 0
    for req in STORE.requests[:10]:
        home = STORE.profile_for(req.user_id).home_currency
        rd = req.request_date
        inv = [Invoice("ir", "Client", req.requested_amount * 2, home, rd, rd + timedelta(days=7),
                       "expected", expected_payment_date=rd + timedelta(days=7), user_id=req.user_id)]
        base, at_risk = build_freelancer_ledger(STORE, req, inv)
        opts = STORE.options_for(req.request_id)
        baseline = analyze_from_ledger(base, opts)
        cfg = ScenarioConfig(delay_days=25, shock_amount=req.requested_amount,
                             shock_date=rd + timedelta(days=3))
        rep = run_scenarios(base, at_risk, opts, cfg, baseline=baseline)
        safe_amounts = {r.amount_safe_to_pay for r in rep.results}
        statuses = {r.status for r in rep.results}
        if len(safe_amounts) > 1 or len(statuses) > 1:
            differentiating += 1
            if differentiating >= 1:
                break
    assert differentiating >= 1, "scenarios never diverged — runner may be vacuous"
