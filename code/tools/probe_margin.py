"""Probe 5: deadline-respecting candidate hypothesis test.

For each sample:
- wait_until_payday: earliest projected payday P (from anchor) with
  balance + P_salary - amount >= minimum -> plan wait on P.
- best installment option (user accepts, max months, deadline) whose final
  payment keeps the running balance safe -> installments.
Compares with gold status/method/date. Also, safe amount under a simple
model: min(slack, amount) when affordable_now-ish, else gold-fitted margins.
"""

from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, getcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from buy_or_wait.loader import DataStore, load_samples  # noqa: E402
from buy_or_wait.messages import extract_facts  # noqa: E402

getcontext().prec = 40
ZERO = Decimal(0)


def med(values):
    return Decimal(str(statistics.median([float(v) for v in values]))) if values else ZERO


def next_month(d: date, day: int) -> date:
    month = d.month + 1
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return date(year, month, min(day, 28))


def salary_dates_for(store, uid, rd, horizon):
    salary_events = sorted(
        [e for e in store.events_for_user(uid) if e.event_type == "income" and e.category == "salary" and e.status == "settled"],
        key=lambda e: e.event_date,
    )
    salary_amount = ZERO
    pay_day = 15
    if salary_events:
        amounts = [e.amount for e in salary_events if e.amount is not None]
        if amounts:
            salary_amount = med(amounts[-3:])
        pay_day = statistics.mode([e.event_date.day for e in salary_events])
    override_amount = None
    override_date = None
    stop = False
    for message in store.messages_for_user(uid):
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
    if override_amount is not None and not stop:
        salary_amount = override_amount
        if override_date is not None:
            pay_dates = [override_date]
            nxt = override_date
            for _ in range(3):
                nxt = next_month(nxt, min(pay_day, 28))
                if nxt <= horizon:
                    pay_dates.append(nxt)
            return salary_amount, pay_dates, stop
    dates = []
    if salary_amount > 0 and not stop:
        first = date(rd.year, rd.month, min(pay_day, 28))
        if first <= rd:
            first = next_month(first, pay_day)
        while first <= horizon:
            dates.append(first)
            first = next_month(first, pay_day)
    return salary_amount, dates, stop


def main() -> None:
    store = DataStore()
    samples = load_samples()
    status_hits = 0
    method_hits = 0
    date_hits = 0
    for sample in samples:
        request = sample.request
        profile = store.profile_for(request.user_id)
        rd = request.request_date
        horizon = rd + timedelta(days=90)
        balance = profile.current_available_balance
        minimum = profile.minimum_balance_to_keep
        methods = set(profile.payment_methods_user_will_consider)

        salary_amount, pay_dates, stop = salary_dates_for(store, request.user_id, rd, horizon)

        # recurring outflows: category medians with anchors from settled history
        groups = defaultdict(list)
        for event in store.events_for_user(request.user_id):
            if event.status == "settled" and event.direction == "debit" and event.amount is not None:
                groups[event.category].append(event)

        flows = []  # (date, amount, category)
        for category, items in groups.items():
            if category == "refund":
                continue
            if len(items) < 3:
                continue
            med_amount = med([e.amount for e in items[-3:]])
            anchor = statistics.mode([e.event_date.day for e in items])
            first = date(rd.year, rd.month, min(anchor, 28))
            if first <= rd:
                first = next_month(first, anchor)
            while first <= horizon:
                flows.append((first, -med_amount, category))
                first = next_month(first, anchor)
        for pay_date in pay_dates:
            flows.append((pay_date, salary_amount, "salary"))
        flows.sort()

        # wait-until-payday candidate
        wait_date = None
        for pay_date in pay_dates:
            bal = balance + salary_amount - request.requested_amount
            if bal < minimum:
                continue
            # simulate remaining flows conservatively (same-month outflows after payday)
            running = bal
            ok = True
            for flow_date, amount, _cat in flows:
                if flow_date <= pay_date:
                    continue
                running += amount
                if running < minimum:
                    ok = False
                    break
            if ok:
                wait_date = pay_date
                break

        # installment candidates: all options; verify with running balance
        best_inst = None
        options = store.options_for(request.request_id)
        for option in sorted(options, key=lambda o: o.payment_option_id):
            if option.payment_method != "installments" or "installments" not in methods:
                continue
            if profile.max_installment_months is not None:
                span = (option.number_of_payments - 1) * (option.payment_frequency_days or 30)
                if span / 30.44 > profile.max_installment_months + 1:
                    continue
            # simulate
            schedule = []
            pay_date = option.first_payment_date
            for _ in range(option.number_of_payments):
                schedule.append(pay_date)
                pay_date += timedelta(days=option.payment_frequency_days or 30)
            ok = True
            for sched_date in schedule:
                if sched_date > request.desired_completion_date:
                    ok = False
                    break
                running = balance
                for flow_date, amount, _cat in flows:
                    if flow_date <= sched_date:
                        running += amount
                running -= option.payment_amount
                if running < minimum:
                    ok = False
                    break
            if ok:
                best_inst = option
                break

        # decide status/method under this simple model
        slack = balance - minimum
        full_now = balance - request.requested_amount >= minimum
        gold_status = sample.gold["affordability_status"]
        gold_method = sample.gold["recommended_payment_method"]
        gold_earliest = sample.gold["earliest_date_for_full_payment"]

        if full_now:
            status, method, earliest = "affordable_now", "full_payment", rd.isoformat()
        elif best_inst is not None:
            status, method, earliest = "affordable_with_plan", "installments", (wait_date.isoformat() if wait_date else "")
        elif wait_date is not None and wait_date <= request.desired_completion_date:
            status, method, earliest = "affordable_later", "wait", wait_date.isoformat()
        else:
            status, method, earliest = "not_affordable", "not_recommended", ""

        s_ok = status == gold_status
        m_ok = method == gold_method
        d_ok = earliest == gold_earliest
        status_hits += s_ok
        method_hits += m_ok
        date_hits += d_ok
        print(
            f"{request.request_id}: pred={status}/{method}/{earliest or '-'} "
            f"gold={gold_status}/{gold_method}/{gold_earliest or '-'} "
            f"{'S' if s_ok else 'x'}{'M' if m_ok else 'x'}{'D' if d_ok else 'x'} wait={wait_date} inst={best_inst.payment_option_id if best_inst else None}"
        )
    print(f"\nstatus {status_hits}/25  method {method_hits}/25  date {date_hits}/25")


if __name__ == "__main__":
    main()
