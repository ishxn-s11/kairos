"""Candidate generation: every legal payment strategy for one request.

Candidate families (problem_statement.md):
- full payment on request_date
- every supplied installment option (schedule exactly as supplied)
- partial payment (two payments, sums to requested_amount)
- wait (single full payment on the earliest safe full-payment date)
- full payment / installments combined with permitted spending changes
- not_recommended fallback

Each candidate is verified through the deterministic simulator before ranking;
the generator is never trusted.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from . import config
from .forecast import PlanCandidate, SpendingChange, fmt_amount, simulate
from .ledger import UserLedger
from .loader import PaymentOption, Request
from .safe_amount import compute_earliest_full_payment_date, compute_safe_amount

ZERO = Decimal(0)


@dataclass
class RequestInputs:
    request: Request
    profile: "object"  # FinancialProfile
    safe_amount: Decimal
    earliest_full_date: Optional[date]
    installments_allowed: bool
    max_installment_months: Optional[int]
    payment_methods: List[str]
    flexible_flows: List  # ProjectedFlow entries eligible for changes


def _installment_schedule(option: PaymentOption) -> List[Tuple[date, Decimal]]:
    schedule = []
    pay_date = option.first_payment_date
    for index in range(option.number_of_payments):
        schedule.append((pay_date, option.payment_amount))
        if option.payment_frequency_days:
            pay_date = pay_date + timedelta(days=option.payment_frequency_days)
    return schedule


def _months_spanning(schedule: List[Tuple[date, Decimal]]) -> int:
    if len(schedule) < 2:
        return 0
    first, last = schedule[0][0], schedule[-1][0]
    months = (last.year - first.year) * 12 + (last.month - first.month)
    if last.day > first.day:
        months += 1
    return months


class CandidateGenerator:
    """Generates all legally possible candidates for one request."""

    def __init__(self, ledger: UserLedger, options: List[PaymentOption]) -> None:
        self.ledger = ledger
        self.request = ledger.request
        self.profile = ledger.profile
        self.options = options
        self.safe_amount = compute_safe_amount(ledger)
        self.earliest_full_date = compute_earliest_full_payment_date(ledger)
        self.methods = set(self.profile.payment_methods_user_will_consider)
        self.max_installment_months = self.profile.max_installment_months
        self.installments_allowed = self.max_installment_months is not None
        self.flexible_flows = self._eligible_flexible_flows()

    # ------------------------------------------------------------------ #
    def _eligible_flexible_flows(self) -> List:
        """Flexible recurring flows (by event id) whose category the user permits changing.

        The id identifies the whole series: a stop/reduce on the source event is
        realized over the series' future occurrences, so historical settled
        occurrences still qualify.
        """
        reduce_allowed = set(self.profile.expense_categories_user_is_willing_to_reduce)
        stop_allowed = set(self.profile.expense_categories_user_is_willing_to_stop)
        eligible = []
        seen = set()
        for flow in self.ledger.flows:
            if not flow.flexible or flow.amount >= 0:
                continue
            if flow.source_id in seen:
                continue
            seen.add(flow.source_id)
            if flow.category in reduce_allowed or flow.category in stop_allowed:
                eligible.append(flow)
        return eligible

    # ------------------------------------------------------------------ #
    def _full_payment_candidate(self, pay_date: date, changes=()) -> PlanCandidate:
        return PlanCandidate(
            method="full_payment",
            payments=[(pay_date, self.request.requested_amount)],
            total_payable=self.request.requested_amount,
            first_payment_date=pay_date,
            completion_date=pay_date,
            number_of_payments=1,
            spending_changes=list(changes),
        )

    def _wait_candidate(self, pay_date: date) -> PlanCandidate:
        return PlanCandidate(
            method="wait",
            payments=[(pay_date, self.request.requested_amount)],
            total_payable=self.request.requested_amount,
            first_payment_date=pay_date,
            completion_date=pay_date,
            number_of_payments=1,
        )

    def _partial_candidate(self) -> Optional[PlanCandidate]:
        request = self.request
        # The two-payment schedule is always extractable when the schedule
        # works; allows_partial_payment only requires an explicit user YES
        # (dataset semantics: False = not shown = schedule works).
        if "partial_payment" not in self.methods:
            return None
        if not (ZERO < self.safe_amount < request.requested_amount):
            return None
        if self.earliest_full_date is None or self.earliest_full_date > request.desired_completion_date:
            return None
        remaining = request.requested_amount - self.safe_amount
        payments = [
            (request.request_date, self.safe_amount),
            (self.earliest_full_date, remaining),
        ]
        return PlanCandidate(
            method="partial_payment",
            payments=payments,
            total_payable=request.requested_amount,
            first_payment_date=request.request_date,
            completion_date=self.earliest_full_date,
            number_of_payments=2,
        )

    def _installment_candidates(self, changes=()) -> List[PlanCandidate]:
        candidates = []
        if "installments" not in self.methods or not self.installments_allowed:
            return candidates
        for option in self.options:
            if option.payment_method != "installments":
                continue
            if self.max_installment_months is not None:
                schedule = _installment_schedule(option)
                span = _months_spanning(schedule)
                if span > self.max_installment_months:
                    continue
            schedule = _installment_schedule(option)
            completion = schedule[-1][0]
            if completion > self.request.desired_completion_date:
                continue
            candidates.append(
                PlanCandidate(
                    method="installments",
                    payments=schedule,
                    total_payable=option.total_payable_amount,
                    payment_option_id=option.payment_option_id,
                    first_payment_date=schedule[0][0],
                    completion_date=completion,
                    number_of_payments=len(schedule),
                    spending_changes=list(changes),
                )
            )
        return candidates

    # ------------------------------------------------------------------ #
    def generate(self) -> List[PlanCandidate]:
        candidates: List[PlanCandidate] = []
        request = self.request

        full_now_ok = (
            "full_payment" in self.methods
            and self.safe_amount >= request.requested_amount
        )
        if full_now_ok:
            candidates.append(self._full_payment_candidate(request.request_date))

        if self.earliest_full_date is not None and self.earliest_full_date > request.request_date:
            if "full_payment" in self.methods:
                wait_candidate = self._wait_candidate(self.earliest_full_date)
                if wait_candidate.completion_date <= request.desired_completion_date:
                    candidates.append(wait_candidate)

        partial = self._partial_candidate()
        if partial is not None:
            candidates.append(partial)

        candidates.extend(self._installment_candidates())

        # -------- spending-change variants (only if plain candidates fail) -------- #
        plain_methods = {c.method for c in candidates}
        need_changes_for_full = (
            "full_payment" in self.methods
            and "full_payment" not in plain_methods
        )
        need_changes_for_installments = (
            "installments" in self.methods
            and self.installments_allowed
            and "installments" not in plain_methods
        )

        if (need_changes_for_full or need_changes_for_installments) and self.flexible_flows:
            base_safe = compute_safe_amount(self.ledger)
            change_sets = self._spending_change_sets(base_safe)
            for changes in change_sets:
                if not changes:
                    continue
                adjusted = CandidateGenerator._with_ledger_changes(self.ledger, changes)
                if need_changes_for_full:
                    sim = simulate(adjusted, [(request.request_date, request.requested_amount)])
                    if sim.safe:
                        candidates.append(
                            self._full_payment_candidate(request.request_date, changes)
                        )
                        need_changes_for_full = False
                if need_changes_for_installments:
                    temp = CandidateGenerator(adjusted, self.options)
                    candidates.extend(temp._installment_candidates())
                    if candidates and any(c.method == "installments" for c in candidates[-3:]):
                        need_changes_for_installments = False
                if not need_changes_for_full and not need_changes_for_installments:
                    break

        return candidates

    # ------------------------------------------------------------------ #
    def _spending_change_sets(self, target_safe_amount: Decimal) -> List[List[SpendingChange]]:
        """Deterministic search over stop/reduce combinations, smallest first."""
        flows = self.flexible_flows
        reduce_allowed = set(self.profile.expense_categories_user_is_willing_to_reduce)
        stop_allowed = set(self.profile.expense_categories_user_is_willing_to_stop)

        options_per_flow: List[List[SpendingChange]] = []
        for flow in flows:
            choices: List[SpendingChange] = []
            monthly_total = flow.amount
            if flow.category in reduce_allowed and flow.minimum_allowed_amount is not None:
                reduction = flow.amount - flow.minimum_allowed_amount
                if reduction > 0:
                    choices.append(SpendingChange("reduce_to", flow.source_id, flow.minimum_allowed_amount))
                    # economically meaningful midpoint reduction
                    mid = (flow.amount + flow.minimum_allowed_amount) / 2
                    mid = mid.quantize(Decimal("0.01") if mid != mid.to_integral() else Decimal(1))
                    if mid > flow.minimum_allowed_amount:
                        choices.append(SpendingChange("reduce_to", flow.source_id, mid))
            if flow.category in stop_allowed:
                choices.append(SpendingChange("stop", flow.source_id))
            if choices:
                options_per_flow.append(choices)

        combos: List[List[SpendingChange]] = []
        for size in (1, 2, 3):
            for pick in itertools.combinations(range(len(options_per_flow)), size):
                for choice_set in itertools.product(*(options_per_flow[i] for i in pick)):
                    # stop and reduce on the same event are mutually exclusive
                    ids = [c.event_id for c in choice_set]
                    if len(ids) != len(set(ids)):
                        continue
                    combos.append(list(choice_set))
        return combos

    # ------------------------------------------------------------------ #
    @staticmethod
    def _with_ledger_changes(ledger: UserLedger, changes: List[SpendingChange]) -> UserLedger:
        import copy

        clone = copy.copy(ledger)
        clone.flows = [
            type(flow)(
                date=flow.date,
                amount=flow.amount,
                kind=flow.kind,
                category=flow.category,
                description=flow.description,
                source_id=flow.source_id,
                recurring_key=flow.recurring_key,
                flexible=flow.flexible,
                minimum_allowed_amount=flow.minimum_allowed_amount,
            )
            for flow in ledger.flows
        ]
        stops = {c.event_id for c in changes if c.action == "stop"}
        reductions = {c.event_id: c.new_amount for c in changes if c.action == "reduce_to"}
        new_flows = []
        for flow in clone.flows:
            if flow.source_id in stops:
                continue
            if flow.source_id in reductions and flow.amount < 0:
                flow = type(flow)(
                    date=flow.date,
                    amount=-reductions[flow.source_id],
                    kind=flow.kind,
                    category=flow.category,
                    description=flow.description,
                    source_id=flow.source_id,
                    recurring_key=flow.recurring_key,
                    flexible=flow.flexible,
                    minimum_allowed_amount=flow.minimum_allowed_amount,
                )
            new_flows.append(flow)
        clone.flows = new_flows
        return clone
