"""Safe-to-pay amount and earliest safe full-payment date.

Both are computed BEFORE optional spending changes, independently of the
user's payment-method preferences, by binary search over the currency quantum
through the deterministic simulator.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from . import config
from .forecast import fmt_amount, simulate
from .ledger import UserLedger
from .loader import Request

ZERO = Decimal(0)


def _quantum(currency: str) -> Decimal:
    return Decimal("0.01") if currency in {"USD", "EUR"} else Decimal("1")


def can_pay_today(ledger: UserLedger, amount: Decimal) -> bool:
    """True when paying ``amount`` on request_date keeps the 90-day horizon safe."""
    if amount <= 0:
        return True
    result = simulate(
        ledger,
        [(ledger.request.request_date, amount)],
        horizon_days=config.FORECAST_DAYS,
    )
    return result.safe


def compute_safe_amount(ledger: UserLedger) -> Decimal:
    """Largest amount payable on request_date that passes the 90-day safety test."""
    request = ledger.request
    cap = request.requested_amount
    if cap <= 0:
        return ZERO
    if can_pay_today(ledger, cap):
        return cap
    # A hard upper bound: balance slack above the minimum today, floored at zero.
    slack = ledger.starting_balance - ledger.minimum_balance
    high = min(cap, slack) if slack > 0 else ZERO
    if high <= 0:
        return ZERO
    if not can_pay_today(ledger, high):
        # Even the slack breaks the horizon (upcoming obligations); bisect down.
        low = ZERO
        high_slack = high
        quantum = _quantum(ledger.profile.home_currency)
        while high_slack - low > quantum:
            mid = (low + high_slack) / 2
            mid = mid.quantize(quantum)
            if mid <= low:
                break
            if can_pay_today(ledger, mid):
                low = mid
            else:
                high_slack = mid
        return low
    low = high
    high = cap
    quantum = _quantum(ledger.profile.home_currency)
    while high - low > quantum:
        mid = ((low + high) / 2).quantize(quantum)
        if mid <= low:
            break
        if can_pay_today(ledger, mid):
            low = mid
        else:
            high = mid
    return low


def compute_earliest_full_payment_date(
    ledger: UserLedger, max_days: Optional[int] = None
) -> Optional[date]:
    """Earliest date a single full payment passes the 90-day safety test.

    ``offset`` is the number of whole days after request_date; the search over
    integer offsets is exact because every projected flow lands on a specific
    day. The safety test for a payment on day D covers D..D+90.
    """
    request = ledger.request
    horizon = max_days or config.FORECAST_DAYS
    amount = request.requested_amount

    for offset in range(horizon + 1):
        candidate_date = request.request_date + timedelta(days=offset)
        result = simulate(ledger, [(candidate_date, amount)], horizon_days=offset + 1)
        if result.safe:
            return candidate_date
    return None
