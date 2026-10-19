"""Financial uncertainty scenarios — separate simulator runs, never averaged.

Implements the four required scenarios for irregular (freelancer) income by
perturbing only the *at-risk* expected income and/or adding a one-off shock, then
re-running the **full** decision pipeline on each resulting ledger:

1. ``on_time``  – expected client income arrives on its expected date.
2. ``delayed``  – expected income arrives ``delay_days`` later.
3. ``never``    – expected income does not arrive within the forecast horizon.
4. ``shock``    – expected income on time **and** an unexpected expense occurs.

Each scenario is an independent ``analyze_from_ledger`` run, so its safe amount,
status, plan, and dated forecast are all produced by the same deterministic
simulator as the baseline. Results are kept separate — material risk is never
smoothed into an average.

Confirmed income (e.g. confirmed invoices, projected salary) is present in every
scenario; only *at-risk* income is varied, matching the engine's safer reading.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional

from . import config
from .ledger import ProjectedFlow, UserLedger
from .loader import PaymentOption
from .pipeline import Analysis, analyze_from_ledger

ZERO = Decimal(0)


@dataclass(frozen=True)
class ScenarioSpec:
    key: str
    label: str
    description: str


SCENARIOS: List[ScenarioSpec] = [
    ScenarioSpec("on_time", "Income on time", "Expected client income arrives on its expected date."),
    ScenarioSpec("delayed", "Income delayed", "Expected client income arrives later than expected."),
    ScenarioSpec("never", "Income never arrives", "Expected client income does not arrive inside the forecast horizon."),
    ScenarioSpec("shock", "Unexpected expense", "Expected income arrives on time and an unexpected expense occurs."),
]


@dataclass
class ScenarioConfig:
    """Explicit, documented scenario assumptions (surfaced in the report)."""

    delay_days: int = 14
    shock_amount: Optional[Decimal] = None  # default: 15% of requested_amount
    shock_date: Optional[date] = None  # default: request_date + 15 days

    def resolve(self, request) -> "ScenarioConfig":
        shock_amount = self.shock_amount
        if shock_amount is None:
            shock_amount = (request.requested_amount * Decimal("0.15")).quantize(Decimal("1"))
        shock_date = self.shock_date
        if shock_date is None:
            shock_date = request.request_date + timedelta(days=15)
        return replace(self, shock_amount=shock_amount, shock_date=shock_date)


@dataclass
class ScenarioResult:
    key: str
    label: str
    description: str
    status: str
    amount_safe_to_pay: Decimal
    recommended_method: str
    payment_plan: str
    earliest_date: str
    safe: bool
    min_closing_balance: Decimal
    min_margin: Decimal
    breach_date: Optional[date]
    expected_income_included: Decimal  # in-horizon at-risk income added by this scenario
    status_changed: bool  # differs from baseline
    safe_amount_delta: Decimal  # scenario safe amount - baseline safe amount
    explanation: str


@dataclass
class ScenarioReport:
    request_id: str
    home_currency: str
    baseline_status: str
    baseline_safe_amount: Decimal
    at_risk_income_total: Decimal
    confirmed_income_in_baseline: Decimal
    config: ScenarioConfig
    results: List[ScenarioResult] = field(default_factory=list)

    def by_key(self, key: str) -> ScenarioResult:
        for r in self.results:
            if r.key == key:
                return r
        raise KeyError(key)


def _in_horizon(flows: List[ProjectedFlow], request) -> Decimal:
    end = request.request_date + timedelta(days=config.FORECAST_DAYS)
    return sum((f.amount for f in flows if request.request_date <= f.date <= end), ZERO)


def _scenario_flows(base_flows, at_risk, key, cfg, request):
    """Return (all_flows, at_risk_flows_used) for one scenario. Pure transform."""
    if key == "never":
        used: List[ProjectedFlow] = []
    elif key == "delayed":
        used = [replace(f, date=f.date + timedelta(days=cfg.delay_days)) for f in at_risk]
    else:  # on_time, shock
        used = list(at_risk)

    flows = list(base_flows) + used
    if key == "shock":
        flows.append(
            ProjectedFlow(
                date=cfg.shock_date,
                amount=-(cfg.shock_amount or ZERO),
                kind="expense",
                category="emergency",
                description="unexpected expense (scenario)",
                source_id="scenario_shock",
            )
        )
    return flows, used


def run_scenarios(
    base_ledger: UserLedger,
    at_risk_flows: List[ProjectedFlow],
    options: List[PaymentOption],
    config_: Optional[ScenarioConfig] = None,
    baseline: Optional[Analysis] = None,
) -> ScenarioReport:
    """Run all four scenarios as independent simulations and compare to baseline.

    ``base_ledger`` is the confirmed-only baseline ledger (freelancer mode builds
    it with confirmed invoices folded in). ``at_risk_flows`` are the uncertain
    receivables to perturb. With no at-risk income, scenarios 1–3 coincide with
    the baseline (an honest result) while the shock scenario still differs.
    """
    request = base_ledger.request
    cfg = (config_ or ScenarioConfig()).resolve(request)

    if baseline is None:
        baseline = analyze_from_ledger(base_ledger, options)

    at_risk_total = _in_horizon(at_risk_flows, request)
    confirmed_in_baseline = _in_horizon(
        [f for f in base_ledger.flows if f.kind == "income" and f.category in {"invoice", "salary"}],
        request,
    )

    report = ScenarioReport(
        request_id=request.request_id,
        home_currency=base_ledger.profile.home_currency,
        baseline_status=baseline.status,
        baseline_safe_amount=baseline.decision.amount_safe_to_pay,
        at_risk_income_total=at_risk_total,
        confirmed_income_in_baseline=confirmed_in_baseline,
        config=cfg,
    )

    for spec in SCENARIOS:
        flows, used = _scenario_flows(base_ledger.flows, at_risk_flows, spec.key, cfg, request)
        scenario_ledger = replace(base_ledger, flows=flows)
        analysis = analyze_from_ledger(scenario_ledger, options)
        cf = analysis.cashflow()
        included = _in_horizon(used, request)
        safe = cf.safe
        report.results.append(
            ScenarioResult(
                key=spec.key,
                label=spec.label,
                description=spec.description,
                status=analysis.status,
                amount_safe_to_pay=analysis.decision.amount_safe_to_pay,
                recommended_method=analysis.decision.recommended_payment_method,
                payment_plan=analysis.decision.payment_plan,
                earliest_date=analysis.decision.earliest_date_for_full_payment,
                safe=safe,
                min_closing_balance=cf.min_closing_balance,
                min_margin=cf.min_margin,
                breach_date=None if safe else cf.min_date,
                expected_income_included=included,
                status_changed=analysis.status != baseline.status,
                safe_amount_delta=analysis.decision.amount_safe_to_pay
                - baseline.decision.amount_safe_to_pay,
                explanation=analysis.decision.decision_explanation,
            )
        )
    return report
