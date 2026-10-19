"""Probe 2: annotate gold samples with candidate recurring-anchor flows.

For each sample, derive from settled history:
- salary: amount, payday, and projected paydays in [rd+1, rd+90]
- rent: amount + anchor day, occurrences in horizon
- utilities: median of last 3, occurrences
- debt_payment / fixed subscriptions: occurrences
Then compare (slack + salary*count - recurring) against the gold safe amount.
"""

from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from buy_or_wait.loader import DataStore, load_samples  # noqa: E402
from buy_or_wait.messages import extract_facts  # noqa: E402

ZERO = Decimal(0)


def median_amount(values: List[Decimal]) -> Decimal:
    return Decimal(str(statistics.median([float(v) for v in values])))


def next_month(d: date, day: int) -> date:
    month = d.month + 1
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return date(year, month, min(day, 28))


def occurrences(start: date, end: date, anchor_day: int, after: date) -> List[date]:
    result = []
    first = date(start.year, start.month, min(anchor_day, 28))
    if first <= after:
        first = next_month(first, anchor_day)
    while first <= end:
        result.append(first)
        first = next_month(first, anchor_day)
    return result


def main() -> None:
    store = DataStore()
    samples = load_samples()
    for sample in samples:
        request = sample.request
        profile = store.profile_for(request.user_id)
        events = store.events_for_user(request.user_id)
        rd = request.request_date
        horizon = rd + timedelta(days=90)
        slack = profile.current_available_balance - profile.minimum_balance_to_keep

        groups: Dict[Tuple[str, str], List] = defaultdict(list)
        for event in events:
            if event.status == "settled" and event.direction in {"debit", "credit"}:
                groups[(event.event_type, event.category)].append(event)

        # salary
        salary_events = groups.get(("income", "salary"), [])
        salary_amount = ZERO
        pay_day = 15
        if salary_events:
            amounts = [e.amount for e in salary_events if e.amount is not None]
            if amounts:
                salary_amount = median_amount(amounts[-3:])
            pay_day = statistics.mode([e.event_date.day for e in salary_events])

        # message amendments
        salary_override = None
        date_override = None
        stop_income = False
        one_time = []
        childcare = []
        rent_factor = Decimal(1)
        for message in store.messages_for_user(request.user_id):
            if message.sent_at.date() > rd:
                continue
            for fact in extract_facts(message.message_text, message.message_id, message.related_event_id):
                if fact.amendment == "replace_amount" and fact.amount is not None and fact.fact_type in {"salary_change", "salary_date_change"}:
                    salary_override = fact.amount
                    if fact.effective_date:
                        date_override = date.fromisoformat(fact.effective_date)
                elif fact.fact_type == "contract_ended":
                    if fact.action == "reduce_income_to" and fact.amount is not None:
                        salary_override = fact.amount
                    else:
                        stop_income = True
                elif fact.fact_type == "invoice_confirmed" and fact.amount and fact.effective_date:
                    one_time.append((date.fromisoformat(fact.effective_date), fact.amount))
                elif fact.fact_type == "recurring_commitment" and fact.amount is not None and fact.effective_date:
                    start = date.fromisoformat(fact.effective_date)
                    childcare.append((start, fact.amount))
                elif fact.fact_type == "expense_change" and fact.amendment == "rent_increase_12pct":
                    rent_factor = Decimal("1.12")

        if salary_override is not None:
            salary_amount = salary_override
        salary_dates = []
        if salary_amount > 0 and not stop_income:
            salary_dates = occurrences(rd, horizon, pay_day, rd)
            if date_override is not None and date_override <= horizon:
                if salary_dates:
                    salary_dates[0] = date_override
                else:
                    salary_dates = [date_override]

        # fixed recurring debit anchors
        rows = []
        for (etype, category), items in groups.items():
            if etype == "income":
                continue
            amounts = [e.amount for e in items if e.amount is not None]
            if not amounts:
                continue
            items_sorted = sorted(items, key=lambda e: e.event_date)
            anchor = statistics.mode([e.event_date.day for e in items_sorted])
            med = median_amount(amounts[-3:])
            occ = occurrences(rd, horizon, anchor, rd)
            rows.append((category, etype, med, anchor, len(occ), items_sorted[-1].flexibility))

        salary_total = salary_amount * len(salary_dates)
        extra_income = sum((amount for _, amount in one_time), ZERO)
        childcare_total = ZERO
        for start, amount in childcare:
            count = len([m for m in range(4) if start + timedelta(days=30 * m) <= horizon])
            childcare_total += amount * count

        recurring_total = ZERO
        for category, etype, med, anchor, count, flexibility in rows:
            factor = rent_factor if category == "rent" else Decimal(1)
            recurring_total += med * count * factor

        slack_plus = slack + salary_total + extra_income
        safe_estimate = slack_plus - recurring_total - childcare_total

        gold = Decimal(sample.gold["amount_safe_to_pay"] or "0")
        flag = "=" if safe_estimate == gold else "X"
        print(
            f"{request.request_id} {flag} slack={slack} salary={salary_amount}x{len(salary_dates)} "
            f"recur={recurring_total} childcare={childcare_total} one_time={extra_income} "
            f"=> est_safe={safe_estimate} gold={gold}"
        )
        for category, etype, med, anchor, count, flexibility in rows:
            print(f"      {etype}/{category}: {med} on day {anchor} x{count} [{flexibility}]")


if __name__ == "__main__":
    main()
