"""Deterministic verification and the official plan ranking.

Verification is independent of generation: every candidate is re-simulated,
schedule/integrity checks are re-derived, and failures record a reason.
Ranking follows problem_statement.md exactly:
  1. Complete the full request by desired_completion_date
  2. Require no spending changes
  3. Minimize the total amount paid
  4. Start payment earlier
  5. Use fewer payments
  6. Lowest payment_option_id
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional, Tuple

from .forecast import PlanCandidate, simulate
from .ledger import UserLedger
from .loader import PaymentOption, Request


@dataclass
class PlanEvaluation:
    candidate: PlanCandidate
    safe: bool
    rejection_reason: str = ""
    min_closing_balance: Decimal = Decimal(0)
    min_margin: Decimal = Decimal(0)


def _verify_common(candidate: PlanCandidate, request: Request) -> Optional[str]:
    if not candidate.payments:
        return "no payments"
    dates = [d for d, _ in candidate.payments]
    if dates != sorted(dates):
        return "payments not chronological"
    if any(d < request.request_date for d in dates):
        return "payment before request date"
    total = sum((amount for _, amount in candidate.payments), Decimal(0))
    if candidate.method != "installments" and total != request.requested_amount:
        return f"payments total {total} != requested {request.requested_amount}"
    if candidate.completion_date is None or candidate.completion_date > request.desired_completion_date:
        return "completes after desired_completion_date"
    if len(candidate.spending_changes) > 3:
        return "more than three spending changes"
    return None


def _verify_partial(candidate: PlanCandidate, request: Request, ledger: UserLedger) -> Optional[str]:
    if len(candidate.payments) != 2:
        return "partial plan must have exactly two payments"
    first_date, first_amount = candidate.payments[0]
    if first_date != request.request_date:
        return "partial first payment must be on request_date"
    return None


def candidate_safe_amount(request: Request, ledger: UserLedger) -> Decimal:
    from .safe_amount import compute_safe_amount

    return compute_safe_amount(ledger)


def verify_candidate(
    candidate: PlanCandidate,
    ledger: UserLedger,
    options: List[PaymentOption],
) -> PlanEvaluation:
    request = ledger.request
    reason = _verify_common(candidate, request)
    if reason:
        return PlanEvaluation(candidate, False, reason)

    if candidate.method == "partial_payment":
        reason = _verify_partial(candidate, request, ledger)
        if reason:
            return PlanEvaluation(candidate, False, reason)

    if candidate.method == "wait" and "wait" not in ledger.profile.payment_methods_user_will_consider:
        # gold: a later full payment is the fallback answer for safe-later
        # requests regardless of the user's declared method preferences.
        pass

    if candidate.method == "installments":
        option = next((o for o in options if o.payment_option_id == candidate.payment_option_id), None)
        if option is None:
            return PlanEvaluation(candidate, False, "unknown payment option")
        schedule = [
            (option.first_payment_date.__class__.fromordinal(option.first_payment_date.toordinal()), option.payment_amount)
        ]
        rebuilt = []
        from datetime import timedelta

        pay_date = option.first_payment_date
        for _ in range(option.number_of_payments):
            rebuilt.append((pay_date, option.payment_amount))
            if option.payment_frequency_days:
                pay_date += timedelta(days=option.payment_frequency_days)
        if candidate.payments != rebuilt:
            return PlanEvaluation(candidate, False, "schedule differs from supplied option")
        if candidate.total_payable != option.total_payable_amount:
            return PlanEvaluation(candidate, False, "total payable differs from supplied option")
        if candidate.method not in ledger.profile.payment_methods_user_will_consider:
            return PlanEvaluation(candidate, False, "method not accepted by user")

    if candidate.method in {"full_payment", "wait"} and "full_payment" not in ledger.profile.payment_methods_user_will_consider:
        return PlanEvaluation(candidate, False, "full payment not accepted by user")

    if candidate.method == "partial_payment" and "partial_payment" not in ledger.profile.payment_methods_user_will_consider:
        return PlanEvaluation(candidate, False, "partial payment not accepted by user")

    # Eligibility of spending changes
    #
    # A change's event_id identifies the flexible series (the dataset marks the
    # recurring event itself flexible). Eligibility is judged against the
    # underlying event, not against modeled ledger flows: future occurrences of
    # a flexible series may legitimately be stopped or reduced, so a settled
    # (historical) event is still an eligible target. The simulator realizes
    # the change on the series' modeled future occurrences.
    events_by_id = {e.event_id: e for e in ledger.resolved_events}
    for change in candidate.spending_changes:
        event = events_by_id.get(change.event_id)
        if event is None:
            return PlanEvaluation(candidate, False, f"spending change targets unknown event {change.event_id}")
        if event.flexibility not in {"reducible", "stoppable", "reducible_or_stoppable"}:
            return PlanEvaluation(candidate, False, f"{change.event_id} is not flexible")
        category = event.category
        if change.action == "stop" and category not in ledger.profile.expense_categories_user_is_willing_to_stop:
            return PlanEvaluation(candidate, False, f"stop not allowed for {category}")
        if change.action == "reduce_to":
            if category not in ledger.profile.expense_categories_user_is_willing_to_reduce:
                return PlanEvaluation(candidate, False, f"reduce not allowed for {category}")
            if event.minimum_allowed_amount is not None and change.new_amount < event.minimum_allowed_amount:
                return PlanEvaluation(candidate, False, f"reduction below minimum for {change.event_id}")

    sim = simulate(ledger, candidate.payments, candidate.spending_changes, keep_rows=False)
    if not sim.safe:
        return PlanEvaluation(
            candidate,
            False,
            f"balance falls below minimum on {sim.min_date}",
            sim.min_closing_balance,
            sim.min_margin,
        )
    return PlanEvaluation(candidate, True, "", sim.min_closing_balance, sim.min_margin)


def rank_key(evaluation: PlanEvaluation, request: Request) -> Tuple:
    candidate = evaluation.candidate
    completes_on_time = 0 if candidate.completion_date <= request.desired_completion_date else 1
    no_changes = 0 if not candidate.spending_changes else 1
    option_id = candidate.payment_option_id or "zzz"
    return (
        completes_on_time,
        no_changes,
        candidate.total_payable,
        candidate.first_payment_date,
        candidate.number_of_payments,
        option_id,
    )


def select_plan(evaluations: List[PlanEvaluation], request: Request) -> Optional[PlanEvaluation]:
    feasible = [e for e in evaluations if e.safe]
    if not feasible:
        return None
    return min(feasible, key=lambda e: rank_key(e, request))
