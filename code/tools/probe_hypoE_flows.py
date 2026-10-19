"""Probe: dump hypothesis-E flows per sample and the day-by-day cumulative trace
against the gold-implied minimum, to identify exactly which events the gold
model includes/excludes."""

from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buy_or_wait.loader import DataStore, load_samples  # noqa: E402

ZERO = Decimal(0)


def med(values):
    values = list(values)
    if not values:
        return ZERO
    return Decimal(str(statistics.median([float(v) for v in values])))


def next_month(d: date, day: int) -> date:
    m = d.month + 1
    y = d.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    return date(y, m, min(day, 28))


def hypo_e_flows(store, request):
    user = request.user_id
    rd = request.request_date
    horizon = rd + timedelta(days=90)
    events = store.events_for_user(user)

    salary_events = sorted(
        [e for e in events if e.event_type == "income" and e.category == "salary" and e.status == "settled"],
        key=lambda e: e.event_date,
    )
    amount = ZERO
    pay_day = 15
    if salary_events:
        amounts = [e.amount for e in salary_events if e.amount is not None]
        if amounts:
            amount = med(amounts[-3:])
        pay_day = statistics.mode([e.event_date.day for e in salary_events])
    scheduled = sorted(
        [e for e in events if e.event_type == "income" and e.category == "salary" and e.status != "settled" and (e.settlement_date or e.event_date) >= rd],
        key=lambda e: e.event_date,
    )
    if scheduled:
        amount = scheduled[0].amount or amount
    flows = []
    if amount > 0:
        if scheduled:
            first = scheduled[0].settlement_date or scheduled[0].event_date
        else:
            first = date(rd.year, rd.month, min(pay_day, 28))
            if first <= rd:
                first = next_month(first, pay_day)
        d = first
        while d <= horizon:
            flows.append((d, amount, "salary(projected)"))
            d = next_month(d, pay_day)

    # explicit events strictly inside (rd, rd+90] (day 0 = request day handled separately)
    for e in events:
        if e.category == "salary" and e.event_type == "income":
            continue
        settle = e.settlement_date or e.event_date
        if not (rd < settle <= horizon):
            continue
        if e.status in {"cancelled", "failed"} or e.direction == "non_cash" or e.event_type == "investment_valuation":
            continue
        if e.amount is None:
            continue
        sign = -1 if e.direction == "debit" else 1
        flows.append((settle, sign * e.amount, f"{e.event_id} {e.category} {e.status}"))
    return flows


def main():
    store = DataStore()
    samples = load_samples()
    only = sys.argv[1:] or None
    for sample in samples:
        request = sample.request
        if only and request.request_id not in only:
            continue
        profile = store.profile_for(request.user_id)
        rd = request.request_date
        flows = hypo_e_flows(store, request)
        by_day = defaultdict(Decimal)
        for d, a, _ in flows:
            by_day[d] += a
        gold_safe = Decimal(sample.gold["amount_safe_to_pay"] or "0")
        bal0 = profile.current_available_balance
        mn = profile.minimum_balance_to_keep
        implied = gold_safe - bal0 + mn
        capped = gold_safe >= request.requested_amount

        cum = ZERO
        lowest = ZERO
        low_day = rd
        for offset in range(91):
            day = rd + timedelta(days=offset)
            cum += by_day.get(day, ZERO)
            if cum < lowest:
                lowest = cum
                low_day = day
        print("=" * 100)
        print(f"{request.request_id} [{request.user_id}] req={request.requested_amount} gold_safe={gold_safe} "
              f"status={sample.gold['affordability_status']} earliest={sample.gold['earliest_date_for_full_payment'] or '-'}")
        print(f"  implied min_cum = {'n/a(capped)' if capped else implied} | hypoE min_cum={lowest} on {low_day}")
        for d, a, label in sorted(flows):
            print(f"    {d} {a:>14} {label}")


if __name__ == "__main__":
    main()
