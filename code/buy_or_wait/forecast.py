"""90-day forecast engine and deterministic candidate verification.

Every candidate plan is simulated through ``simulate`` — the verifier never
trusts the generator. The safety invariant: the projected available balance
never falls below ``minimum_balance_to_keep`` at any point in the horizon.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from . import config
from .ledger import UserLedger
from .loader import PaymentOption, Request

ZERO = Decimal(0)


@dataclass
class CashFlowRow:
    date: date
    opening_balance: Decimal
    credits: Decimal
    debits: Decimal
    candidate_request_payments: Decimal
    closing_balance: Decimal
    minimum_balance_to_keep: Decimal
    remaining_safety_margin: Decimal


@dataclass
class ForecastResult:
    safe: bool
    min_closing_balance: Decimal
    min_margin: Decimal
    min_date: Optional[date]
    rows: List[CashFlowRow] = field(default_factory=list)


@dataclass
class SpendingChange:
    action: str  # stop | reduce_to
    event_id: str
    new_amount: Optional[Decimal] = None

    def render(self) -> str:
        if self.action == "stop":
            return f"stop:{self.event_id}"
        return f"reduce_to:{self.event_id}:{self.new_amount.normalize()}"


@dataclass
class PlanCandidate:
    method: str  # full_payment | partial_payment | installments | wait | not_recommended
    payments: List[Tuple[date, Decimal]] = field(default_factory=list)
    total_payable: Decimal = ZERO
    payment_option_id: Optional[str] = None
    spending_changes: List[SpendingChange] = field(default_factory=list)
    first_payment_date: Optional[date] = None
    completion_date: Optional[date] = None
    number_of_payments: int = 0
    feasibility_note: str = ""

    def payment_plan(self) -> str:
        if not self.payments:
            return "none"
        return "|".join(f"{d.isoformat()}:{fmt_amount(a)}" for d, a in self.payments)

    def spending_changes_needed(self) -> str:
        if not self.spending_changes:
            return "none"
        return "|".join(change.render() for change in self.spending_changes)


def fmt_amount(amount: Decimal) -> str:
    """Plain decimal string without trailing zeros (currencies with cents keep 2dp)."""
    text = format(amount, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
        if "." not in text:
            return text
        decimals = len(text.split(".")[1])
        if decimals == 1:
            text = f"{text}0"
    return text


def apply_spending_changes(ledger: UserLedger, changes: List[SpendingChange]) -> List:
    """Return ledger flows with the permitted spending changes applied."""
    stops = {c.event_id for c in changes if c.action == "stop"}
    reductions = {c.event_id: c.new_amount for c in changes if c.action == "reduce_to"}
    adjusted = []
    for flow in ledger.flows:
        key = flow.source_id
        if key in stops:
            continue
        if key in reductions and flow.amount < 0:
            old = -flow.amount
            new = reductions[key]
            delta = old - new
            flow = type(flow)(
                date=flow.date,
                amount=-(old - delta),
                kind=flow.kind,
                category=flow.category,
                description=flow.description,
                source_id=flow.source_id,
                recurring_key=flow.recurring_key,
                flexible=flow.flexible,
                minimum_allowed_amount=flow.minimum_allowed_amount,
            )
        adjusted.append(flow)
    return adjusted


def simulate(
    ledger: UserLedger,
    payments: List[Tuple[date, Decimal]],
    spending_changes: Optional[List[SpendingChange]] = None,
    horizon_days: Optional[int] = None,
    keep_rows: bool = False,
) -> ForecastResult:
    """Deterministically simulate the ledger plus candidate payments."""
    horizon_days = horizon_days or config.FORECAST_DAYS
    start = ledger.request.request_date
    end = start + timedelta(days=horizon_days)  # inclusive of day 90 via <=

    flows = apply_spending_changes(ledger, spending_changes or [])
    by_date: Dict[date, List] = {}
    for flow in flows:
        if start <= flow.date <= end:
            by_date.setdefault(flow.date, []).append(flow)
    payments_by_date: Dict[date, Decimal] = {}
    for pay_date, amount in payments:
        payments_by_date[pay_date] = payments_by_date.get(pay_date, ZERO) + amount

    balance = ledger.starting_balance
    minimum = ledger.minimum_balance
    safe = True
    min_balance: Optional[Decimal] = None
    min_margin: Optional[Decimal] = None
    min_date: Optional[date] = None
    rows: List[CashFlowRow] = []

    for offset in range(horizon_days + 1):
        day = start + timedelta(days=offset)
        opening = balance
        credits = ZERO
        debits = ZERO
        for flow in sorted(by_date.get(day, []), key=lambda f: f.amount):
            if flow.amount >= 0:
                credits += flow.amount
            else:
                debits += -flow.amount
        candidate_payment = payments_by_date.get(day, ZERO)
        if candidate_payment > 0:
            debits += candidate_payment
        closing = opening + credits - debits
        margin = closing - minimum
        if min_balance is None or closing < min_balance:
            min_balance = closing
            min_margin = margin
            min_date = day
        if closing < minimum:
            safe = False
        if keep_rows:
            rows.append(
                CashFlowRow(
                    date=day,
                    opening_balance=opening,
                    credits=credits,
                    debits=debits,
                    candidate_request_payments=candidate_payment,
                    closing_balance=closing,
                    minimum_balance_to_keep=minimum,
                    remaining_safety_margin=margin,
                )
            )
        balance = closing

    return ForecastResult(
        safe=safe,
        min_closing_balance=min_balance if min_balance is not None else ZERO,
        min_margin=min_margin if min_margin is not None else ZERO,
        min_date=min_date,
        rows=rows,
    )
