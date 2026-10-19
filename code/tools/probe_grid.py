"""Grid-search forecast-model variants scored against the 25 gold samples.

Variants combine: recurrence grouping (desc vs category), interval tolerance,
pending-debit inclusion, provision layer on/off, irregular-interval support.
Reports exact hits on amount_safe_to_pay + earliest_date and per-sample gaps
for the best variant.
"""

from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buy_or_wait.loader import DataStore, load_samples  # noqa: E402
from buy_or_wait.messages import extract_facts  # noqa: E402

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


class Variant:
    def __init__(self, name, group_by_cat=False, var_tol="0.15", interval_tol=4,
                 pending_debits=True, provision=False, irregular=False,
                 rec_last_n=3, salary_last_n=3, skip_var_check=False):
        self.name = name
        self.group_by_cat = group_by_cat
        self.var_tol = Decimal(var_tol)
        self.interval_tol = interval_tol
        self.pending_debits = pending_debits
        self.provision = provision
        self.irregular = irregular
        self.rec_last_n = rec_last_n
        self.salary_last_n = salary_last_n
        self.skip_var_check = skip_var_check


def build_flows(store, request, v: Variant):
    user = request.user_id
    rd = request.request_date
    horizon = rd + timedelta(days=90)
    profile = store.profile_for(user)
    events = store.events_for_user(user)
    msgs = [m for m in store.messages_for_user(user) if m.sent_at.date() <= rd]

    # ---- message amendments ----
    salary_override = None
    salary_date_override = None
    stop_income = False
    extra = []  # (date, signed_amount)
    for message in msgs:
        for fact in extract_facts(message.message_text, message.message_id, message.related_event_id):
            if fact.amendment == "replace_amount" and fact.amount is not None and fact.fact_type in {"salary_change", "salary_date_change"}:
                salary_override = fact.amount
                if fact.effective_date:
                    salary_date_override = date.fromisoformat(fact.effective_date)
            elif fact.fact_type == "contract_ended":
                if fact.action == "reduce_income_to" and fact.amount is not None:
                    salary_override = fact.amount
                else:
                    stop_income = True
            elif fact.fact_type == "invoice_confirmed" and fact.amount and fact.effective_date:
                extra.append((date.fromisoformat(fact.effective_date), Decimal(str(fact.amount))))
            elif fact.fact_type == "recurring_commitment" and fact.amount is not None and fact.effective_date:
                start = date.fromisoformat(fact.effective_date)
                for k in range(4):
                    d = start + timedelta(days=30 * k)
                    if d <= horizon:
                        extra.append((d, -Decimal(str(fact.amount))))

    flows: List[Tuple[date, Decimal]] = []

    # ---- salary projection ----
    salary_events = sorted(
        [e for e in events if e.event_type == "income" and e.category == "salary" and e.status == "settled" and e.event_date < rd],
        key=lambda e: e.event_date,
    )
    scheduled = sorted(
        [e for e in events if e.event_type == "income" and e.category == "salary" and e.status != "settled" and e.event_date >= rd and (e.settlement_date or e.event_date) <= horizon],
        key=lambda e: e.event_date,
    )
    amount = ZERO
    pay_day = 15
    if salary_events:
        amounts = [e.amount for e in salary_events if e.amount is not None]
        if amounts:
            amount = med(amounts[-v.salary_last_n:])
        pay_day = statistics.mode([e.event_date.day for e in salary_events])
    if salary_override is not None:
        amount = salary_override
    if scheduled and salary_override is None:
        # use scheduled event amount if it is the most recent signal
        amount = scheduled[0].amount or amount

    if amount > 0 and not stop_income:
        if scheduled:
            first = scheduled[0].settlement_date or scheduled[0].event_date
        else:
            first = date(rd.year, rd.month, min(pay_day, 28))
            if first <= rd:
                first = next_month(first, pay_day)
        if salary_date_override is not None:
            first = salary_date_override
        d = first
        while d <= horizon:
            flows.append((d, amount))
            d = next_month(d, pay_day)

    # ---- recurring debits/credits from history ----
    groups = defaultdict(list)
    key_fn = (lambda e: (e.event_type, e.category)) if v.group_by_cat else (lambda e: (e.event_type, e.category, e.description))
    for e in events:
        if e.status == "settled" and e.event_date < rd and e.event_type in {"expense", "subscription", "debt_payment", "income"} and e.category != "salary":
            groups[key_fn(e)].append(e)

    projected_keys = set()
    for key, items in groups.items():
        if len(items) < 3:
            continue
        items = sorted(items, key=lambda e: e.event_date)
        intervals = [(b.event_date - a.event_date).days for a, b in zip(items, items[1:])]
        interval = int(statistics.median(intervals))
        lo, hi = (30 - v.interval_tol, 30 + v.interval_tol)
        if v.irregular and not (lo <= interval <= hi):
            if interval < 5 or interval > 45:
                continue
        elif not (lo <= interval <= hi):
            continue
        amounts = [e.amount for e in items if e.amount is not None]
        if not amounts:
            continue
        med_amount = med(amounts[-v.rec_last_n:])
        if not v.skip_var_check and not all(abs(a - med_amount) <= med_amount * v.var_tol for a in amounts[-v.rec_last_n:]):
            continue
        last = items[-1]
        projected_keys.add(key)
        d = last.event_date
        while d < rd:
            d += timedelta(days=interval)
        if d < rd:
            d += timedelta(days=interval)
        while d <= horizon + timedelta(days=2):
            flows.append((d, -med_amount))
            d += timedelta(days=interval)

    # ---- explicit future events not covered by recurrence ----
    for e in events:
        if e.category == "salary" and e.event_type == "income":
            continue
        key = key_fn(e)
        settle = e.settlement_date or e.event_date
        if not (rd <= settle <= horizon):
            continue
        if e.status in {"cancelled", "failed"} or e.direction == "non_cash":
            continue
        if e.event_type == "investment_valuation":
            continue
        if key in projected_keys and settle >= rd and e.status == "settled":
            continue  # recurrence already projects this series forward
        if e.amount is None:
            continue
        if e.status == "pending" and e.direction == "credit":
            continue
        if e.status == "pending" and e.direction == "debit" and not v.pending_debits:
            continue
        sign = -1 if e.direction == "debit" else 1
        flows.append((settle, sign * e.amount))

    # ---- provision for protected variable essentials ----
    if v.provision:
        protected = set(profile.expense_categories_to_protect)
        var_amounts = defaultdict(list)
        for e in events:
            if e.amount is None:
                continue
            if e.status == "settled" and e.direction == "debit" and e.event_date < rd and e.category in protected and e.category not in {"rent", "utilities"}:
                var_amounts[e.category].append(e.amount)
        monthly = ZERO
        for cat, amts in var_amounts.items():
            if len(amts) >= 3:
                monthly += med(amts[-6:]) * 4
        for k in range(4):
            d = rd + timedelta(days=30 * k)
            if d <= horizon:
                flows.append((d, -monthly))

    flows.extend(extra)
    return flows


def evaluate_variant(store, samples, v: Variant, verbose=False):
    safe_hits = earliest_hits = 0
    gaps = []
    for sample in samples:
        request = sample.request
        profile = store.profile_for(request.user_id)
        rd = request.request_date
        flows = build_flows(store, request, v)
        by_day = defaultdict(Decimal)
        for d, a in flows:
            by_day[d] += a

        def sim(pay_date, pay_amount):
            bal = profile.current_available_balance
            for offset in range(91):
                day = rd + timedelta(days=offset)
                if day < pay_date:
                    continue
                bal += by_day.get(day, ZERO)
                if day == pay_date:
                    bal -= pay_amount
                if bal < profile.minimum_balance_to_keep:
                    return False
            return True

        q = Decimal("0.01") if "." in str(request.requested_amount) else Decimal(1)
        req = request.requested_amount
        if sim(rd, req):
            safe = req
        else:
            slack = profile.current_available_balance - profile.minimum_balance_to_keep
            hi = min(req, slack)
            if hi <= 0:
                safe = ZERO
            elif sim(rd, hi):
                lo, hi = hi, req
                while hi - lo > q:
                    mid = ((lo + hi) / 2).quantize(q)
                    if mid <= lo:
                        break
                    if sim(rd, mid):
                        lo = mid
                    else:
                        hi = mid
                safe = lo
            else:
                lo, hi = ZERO, hi
                while hi - lo > q:
                    mid = ((lo + hi) / 2).quantize(q)
                    if mid <= lo:
                        break
                    if sim(rd, mid):
                        lo = mid
                    else:
                        hi = mid
                safe = lo

        earliest = None
        for offset in range(91):
            if sim(rd + timedelta(days=offset), req):
                earliest = rd + timedelta(days=offset)
                break

        gold_safe = Decimal(sample.gold["amount_safe_to_pay"] or "0")
        gold_earliest = sample.gold["earliest_date_for_full_payment"]
        ok_s = safe == gold_safe
        ok_e = (earliest.isoformat() if earliest else "") == gold_earliest
        safe_hits += ok_s
        earliest_hits += ok_e
        if not ok_s or verbose:
            implied = gold_safe - profile.current_available_balance + profile.minimum_balance_to_keep
            cum = ZERO
            lowest = ZERO
            low_day = rd
            for offset in range(91):
                day = rd + timedelta(days=offset)
                cum += by_day.get(day, ZERO)
                if cum < lowest:
                    lowest = cum
                    low_day = day
            gaps.append((request.request_id, safe, gold_safe, lowest, implied, low_day))
    return safe_hits, earliest_hits, gaps


def main():
    store = DataStore()
    samples = load_samples()
    variants = [
        Variant("base(desc,var15,pending,monthly)"),
        Variant("cat-grouping", group_by_cat=True),
        Variant("no-var-check", skip_var_check=True),
        Variant("no-pending", pending_debits=False),
        Variant("provision", provision=True),
        Variant("irregular", irregular=True),
        Variant("cat+irregular", group_by_cat=True, irregular=True),
        Variant("cat+no-var", group_by_cat=True, skip_var_check=True),
        Variant("no-pending+provision", pending_debits=False, provision=True),
        Variant("cat+provision", group_by_cat=True, provision=True),
        Variant("rec2", rec_last_n=2),
        Variant("salary2", salary_last_n=2),
        Variant("base+verbose"),
    ]
    results = []
    for v in variants:
        s, e, gaps = evaluate_variant(store, samples, v)
        results.append((v.name, s, e, gaps))
        print(f"{v.name:30s} safe {s:2d}/25  earliest {e:2d}/25")
    print()
    best = max(results, key=lambda r: r[1] + r[2])
    print(f"=== best: {best[0]} (safe {best[1]}, earliest {best[2]}) ===")
    for rid, safe, gold_safe, lowest, implied, low_day in best[3]:
        print(f"  {rid}: safe={safe} gold={gold_safe} min_cum={lowest} implied={implied} low_day={low_day}")


if __name__ == "__main__":
    main()
