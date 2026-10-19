"""Decision pipeline: one request in, one AffordabilityDecision out.

Pipeline stages: retrieve context -> reconstruct ledger -> forecast ->
safe amount -> earliest full date -> generate candidates -> verify -> rank ->
derive status -> explain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional

from .forecast import ForecastResult, PlanCandidate, fmt_amount, simulate
from .images import ImageEvidenceStore
from .ledger import LedgerBuilder, UserLedger
from .loader import DataStore, PaymentOption, Request
from .plan_generator import CandidateGenerator
from .plan_ranker import PlanEvaluation, select_plan, verify_candidate
from .safe_amount import compute_earliest_full_payment_date, compute_safe_amount


@dataclass
class AffordabilityDecision:
    request_id: str
    amount_safe_to_pay: Decimal
    affordability_status: str
    recommended_payment_method: str
    payment_plan: str
    earliest_date_for_full_payment: str
    spending_changes_needed: str
    decision_explanation: str


def _fmt_dmy(date_obj: date) -> str:
    """Portable 'D Month YYYY' without leading zero (Windows lacks %-d)."""
    return f"{date_obj.day} {date_obj.strftime('%B %Y')}"


def _money(amount: Decimal) -> str:
    text = f"{amount:,.2f}"
    if text.endswith(".00"):
        text = text[:-3]
    return text


def derive_status(
    request: Request,
    safe_amount: Decimal,
    earliest_full_date: Optional[date],
    best: Optional[PlanEvaluation],
    methods: List[str],
) -> str:
    if safe_amount >= request.requested_amount and "full_payment" in methods:
        return "affordable_now"
    if best is not None and best.candidate.method in {"partial_payment", "installments", "full_payment"}:
        return "affordable_with_plan"
    if earliest_full_date is not None and earliest_full_date <= request.desired_completion_date and "full_payment" in methods:
        return "affordable_later"
    return "not_affordable"


def build_explanation(
    ledger: UserLedger,
    request: "object",
    best: Optional[PlanEvaluation],
    status: str,
    safe_amount: Decimal,
    earliest_full_date: Optional[date],
) -> str:
    home = ledger.profile.home_currency
    minimum = ledger.minimum_balance
    min_text = f"{home} {minimum:,.2f}".replace(".00", "")

    if status == "not_affordable" or best is None:
        return (
            f"Do not make this payment by {_fmt_dmy(request.desired_completion_date)}. "
            f"None of the available options keeps the {min_text} minimum protected."
        )

    candidate = best.candidate
    changes_phrase = ""
    if candidate.spending_changes:
        parts = []
        for change in candidate.spending_changes:
            if change.action == "stop":
                parts.append(f"stop {change.event_id}")
            else:
                parts.append(f"reduce {change.event_id} to {home} {change.new_amount:,.2f}".replace(".00", ""))
        changes_phrase = " ".join(parts) + ", then "

    if candidate.method == "full_payment":
        day = _fmt_dmy(candidate.first_payment_date)
        if status == "affordable_now":
            return (
                f"{changes_phrase}Pay {home} {_money(request.requested_amount)} today. "
                f"This leaves at least {min_text} available."
            )
        return (
            f"{changes_phrase}Pay {home} {_money(request.requested_amount)} today via permitted spending changes. "
            f"This keeps at least {min_text} available."
        )

    if candidate.method == "partial_payment":
        first_d, first_a = candidate.payments[0]
        second_d, second_a = candidate.payments[1]
        return (
            f"Pay {home} {_money(first_a)} today and {home} {_money(second_a)} on {_fmt_dmy(second_d)}. "
            f"This completes the full request and keeps the {min_text} minimum protected."
        )

    if candidate.method == "installments":
        per = candidate.payments[0][1]
        start = candidate.payments[0][0]
        return (
            f"Use {len(candidate.payments)} installments of {home} {_money(per)}, starting {_fmt_dmy(start)}. "
            f"This leaves at least {min_text} available."
        )

    if candidate.method == "wait":
        day = _fmt_dmy(candidate.first_payment_date)
        return (
            f"Pay {home} {_money(request.requested_amount)} in full on {day}. "
            f"Paying earlier would take the balance below the {min_text} minimum."
        )

    return f"Recommended method: {candidate.method}. Keeps at least {min_text} available."


@dataclass
class Analysis:
    """Everything the decision produced, so reports/scenarios can reuse it.

    ``decide()`` returns only the row; ``analyze()`` keeps the ledger, candidates,
    and the selected plan so a report can render a dated cash-flow table (and a
    scenario runner can re-run the same decision on a modified ledger) without
    recomputing or inventing any number.
    """

    request: Request
    ledger: UserLedger
    options: List[PaymentOption]
    safe_amount: Decimal
    earliest_full_date: Optional[date]
    candidates: List[PlanCandidate]
    evaluations: List[PlanEvaluation]
    best: Optional[PlanEvaluation]
    status: str
    decision: "AffordabilityDecision"
    _forecast_cache: Optional[ForecastResult] = field(default=None, repr=False)

    def cashflow(self) -> ForecastResult:
        """Deterministic dated forecast for the recommended plan (computed once).

        Every row is produced by ``simulate`` — the report never derives a balance
        itself, so displayed numbers can only originate from the simulator.
        """
        if self._forecast_cache is None:
            payments = list(self.best.candidate.payments) if self.best else []
            changes = list(self.best.candidate.spending_changes) if self.best else []
            self._forecast_cache = simulate(self.ledger, payments, changes, keep_rows=True)
        return self._forecast_cache


def analyze_from_ledger(ledger: UserLedger, options: List[PaymentOption]) -> Analysis:
    """Run the decision pipeline against an already-built (possibly modified) ledger.

    This is the single place the decision is computed; ``decide`` and the
    uncertainty-scenario runner both funnel through it, so a scenario is a true
    separate simulator run rather than an approximation.
    """
    request = ledger.request

    generator = CandidateGenerator(ledger, options)
    safe_amount = generator.safe_amount
    earliest_full_date = generator.earliest_full_date

    candidates = generator.generate()
    evaluations = [verify_candidate(c, ledger, options) for c in candidates]
    best = select_plan(evaluations, request)

    status = derive_status(
        request,
        safe_amount,
        earliest_full_date,
        best,
        ledger.profile.payment_methods_user_will_consider,
    )

    # ---- output field assembly ----
    if status == "affordable_now":
        earliest_out = request.request_date.isoformat()
    elif earliest_full_date is not None:
        earliest_out = earliest_full_date.isoformat()
    else:
        earliest_out = ""

    if best is None:
        method = "not_recommended"
        plan = "none"
        changes_out = "none"
    else:
        method = best.candidate.method
        plan = best.candidate.payment_plan()
        changes_out = best.candidate.spending_changes_needed()

    # not_affordable rows use no plan
    if status == "not_affordable":
        method = "not_recommended"
        plan = "none"
        changes_out = "none"

    explanation = build_explanation(ledger, request, best, status, safe_amount, earliest_full_date)

    decision = AffordabilityDecision(
        request_id=request.request_id,
        amount_safe_to_pay=safe_amount,
        affordability_status=status,
        recommended_payment_method=method,
        payment_plan=plan,
        earliest_date_for_full_payment=earliest_out,
        spending_changes_needed=changes_out,
        decision_explanation=explanation,
    )
    return Analysis(
        request=request,
        ledger=ledger,
        options=options,
        safe_amount=safe_amount,
        earliest_full_date=earliest_full_date,
        candidates=candidates,
        evaluations=evaluations,
        best=best,
        status=status,
        decision=decision,
    )


def analyze(store: DataStore, request: Request) -> Analysis:
    """Build the ledger for a request and run the full decision, keeping context."""
    builder = LedgerBuilder(store)
    ledger = builder.build(request)
    options = store.options_for(request.request_id)
    return analyze_from_ledger(ledger, options)


def decide(store: DataStore, request: Request) -> AffordabilityDecision:
    """One request in, one decision out (thin wrapper over ``analyze``)."""
    return analyze(store, request).decision
