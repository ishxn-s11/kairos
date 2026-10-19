"""Probe: hypothesis E — the gold forecast model projects ONLY:
  - salary on the history-anchored payday (median amount, message-amended)
  - explicit future-dated events (settlement_date/event_date in horizon)
  - message-derived facts (confirmed invoice income, new commitments)
and nothing else (no rent/utilities/other recurring projections).

Check the safe amount + earliest date this yields vs gold on all 25 samples.
"""

from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buy_or_wait.loader import DataStore, load_samples  # noqa: E402
from buy_or_wait.messages import extract_facts  # noqa: E402

ZERO = Decimal(0)


def med(values):
    return Decimal(str(statistics.median([float(v) for v in values])))


def next_month(d: date, day: int) -> date:
    m = d.month + 1
    y = d.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    return date(y, m, min(day, 28))


def salary_flows(store, user, rd, horizon, msgs):
    salary_events = sorted(
        [
            e
            for e in store.events_for_user(user)
            if e.event_type == "income" and e.category == "salary" and e.status == "settled"
        ],
        key=lambda e: e.event_date,
    )
    amount = ZERO
    pay_day = 15
    if salary_events:
        amounts = [e.amount for e in salary_events if e.amount is not None]
        if amounts:
            amount = med(amounts[-3:])
        pay_day = statistics.mode([e.event_date.day for e in salary_events])

    override_amount = None
    override_date = None
    stop = False
    for message in msgs:
        if message.sent_at.date() > rd:
            continue
        for fact in extract_facts(message.message_text, message.message_id, message.related_event_id):
            if fact.amendment == "replace_amount" and fact.amount is not None and fact.fact_type in {"salary_change", "salary_date_change"}:
                override_amount = fact.amount
                if fact.effective_date:
                    override_date = date.fromisoformat(fact.effective_date)
            elif fact.fact_type == "contract_ended":
                if fact.action == "reduce_income_to" and fact.amount is not None:
                    override_amount = fact.amount
                else:
                    stop = True

    if override_amount is not None:
        amount = override_amount
    dates = []
    if amount > 0 and not stop:
        first = date(rd.year, rd.month, min(pay_day, 28))
        if first <= rd:
            first = next_month(first, pay_day)
        while first <= horizon:
            dates.append(first)
            first = next_month(first, pay_day)
    if override_date is not None and override_date <= horizon and dates:
        dates[0] = override_date
    return [(d, amount) for d in dates]


def main() -> None:
    store = DataStore()
    samples = load_samples()
    safe_hits = 0
    earliest_hits = 0
    for sample in samples:
        request = sample.request
        profile = store.profile_for(request.user_id)
        rd = request.request_date
        horizon = rd + timedelta(days=90)
        msgs = [m for m in store.messages_for_user(request.user_id) if m.sent_at.date() <= rd]

        flows = []  # (date, signed amount)
        flows.extend(salary_flows(store, request.user_id, rd, horizon, msgs))

        # explicit future-dated events (exclude salary which is projected)
        for event in store.events_for_user(request.user_id):
            if event.event_type == "income" and event.category == "salary" and event.status == "settled":
                continue
            settle = event.settlement_date or event.event_date
            if not (rd <= settle <= horizon):
                continue
            if event.status in {"cancelled", "failed"}:
                continue
            if event.event_type == "investment_valuation" or event.direction == "non_cash":
                continue
            amount = event.amount
            if amount is None:
                continue
            if event.status == "pending" and event.direction == "credit":
                continue
            sign = -1 if event.direction == "debit" else 1
            flows.append((settle, sign * amount))

        by_date = defaultdict(Decimal)
        for d, a in flows:
            by_date[d] += a

        def sim(pay_date, pay_amount):
            bal = profile.current_available_balance
            for offset in range(91):
                day = rd + timedelta(days=offset)
                if day < pay_date:
                    continue
                bal += by_date.get(day, ZERO)
                if day == pay_date:
                    bal -= pay_amount
                if bal < profile.minimum_balance_to_keep:
                    return False
            return True

        def earliest_full():
            for offset in range(91):
                if sim(rd + timedelta(days=offset), request.requested_amount):
                    return rd + timedelta(days=offset)
            return None

        # safe amount = max x payable today that keeps 91-day window safe
        lo, hi = ZERO, request.requested_amount
        q = Decimal("0.01") if "." in str(request.requested_amount) else Decimal(1)
        if sim(rd, request.requested_amount):
            safe = request.requested_amount
        else:
            slack = profile.current_available_balance - profile.minimum_balance_to_keep
            hi = min(request.requested_amount, slack)
            if hi > 0 and sim(rd, hi):
                lo = hi
                hi = request.requested_amount
            else:
                hi2, hi = hi, ZERO
                lo, hi2 = ZERO, hi2
            while hi - lo > q:
                mid = ((lo + hi) / 2).quantize(q)
                if mid <= lo:
                    break
                if sim(rd, mid):
                    lo = mid
                else:
                    hi = mid
            safe = lo

        earliest = earliest_full()
        gold_safe = Decimal(sample.gold["amount_safe_to_pay"] or "0")
        gold_earliest = sample.gold["earliest_date_for_full_payment"]
        ok_s = safe == gold_safe
        ok_e = (earliest.isoformat() if earliest else "") == gold_earliest
        safe_hits += ok_s
        earliest_hits += ok_e
        print(
            f"{request.request_id}: safe={safe}{'=' if ok_s else 'X(gold ' + str(gold_safe) + ')'} "
            f"earliest={earliest}{'=' if ok_e else 'X(gold ' + gold_earliest + ')'}"
        )
    print(f"\nhypothesis E: safe {safe_hits}/25, earliest {earliest_hits}/25")


if __name__ == "__main__":
    main()
