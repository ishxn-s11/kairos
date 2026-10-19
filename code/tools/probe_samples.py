"""Probe: reverse-engineer the gold forecast model from the 25 solved samples.

For each sample, the probe tries four generic ledger models and reports which
one reproduces the gold safe amount / earliest date:

  A: income-only  - only projected salary + real future events
  B: median-day   - balance clamped to monthly-median of income-only trace
  C: strict       - income + strictly-detected recurring debits
  D: no-provision - our full model without the variable-essential provision
"""

from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buy_or_wait.forecast import simulate  # noqa: E402
from buy_or_wait.ledger import LedgerBuilder, ProjectedFlow  # noqa: E402
from buy_or_wait.loader import DataStore, Request, load_samples  # noqa: E402
from buy_or_wait.messages import extract_facts  # noqa: E402

ZERO = Decimal(0)


def home_amount(store, ledger_profile_home, event, notes):
    from buy_or_wait import fx

    amount = event.amount
    settle = event.settlement_date or event.event_date
    if event.currency == ledger_profile_home:
        return amount
    return fx.convert(amount, event.currency, ledger_profile_home, settle)


def build_models(store: DataStore, request: Request) -> Dict[str, List[ProjectedFlow]]:
    """Return flow lists for the four candidate models."""
    builder = LedgerBuilder(store)
    ledger = builder.build(request)
    profile = ledger.profile
    home = profile.home_currency
    events = ledger.resolved_events
    horizon_end = request.request_date + timedelta(days=95)

    # message amendments (salary replacement etc.)
    salary_replace_amount = None
    salary_replace_date = None
    stop_income = False
    one_time_incomes = []
    extra_expenses = []
    rent_factor = Decimal(1)
    for message, facts in builder.message_facts_for(request.user_id, request):
        if message.sent_at.date() > request.request_date:
            continue
        for fact in facts:
            if fact.fact_type in {"salary_change", "salary_date_change"} and fact.amendment == "replace_amount" and fact.amount is not None:
                salary_replace_amount = fact.amount
                if fact.effective_date:
                    from datetime import date as _date

                    salary_replace_date = _date.fromisoformat(fact.effective_date)
            elif fact.fact_type == "contract_ended":
                if fact.action == "reduce_income_to" and fact.amount is not None:
                    salary_replace_amount = fact.amount
                else:
                    stop_income = True
            elif fact.fact_type == "invoice_confirmed" and fact.amount and fact.effective_date:
                from datetime import date as _date

                one_time_incomes.append(
                    ProjectedFlow(
                        date=_date.fromisoformat(fact.effective_date),
                        amount=home_amount(store, home, type("E", (), {"amount": fact.amount, "currency": fact.currency or home, "settlement_date": _date.fromisoformat(fact.effective_date), "event_date": _date.fromisoformat(fact.effective_date)}), None),
                        kind="income",
                        category="invoice",
                        description=f"confirmed invoice {message.message_id}",
                        source_id=message.message_id,
                    )
                )
            elif fact.fact_type == "recurring_commitment" and fact.amount is not None:
                from datetime import date as _date

                start = _date.fromisoformat(fact.effective_date) if fact.effective_date else request.request_date
                for month in range(4):
                    extra_expenses.append(
                        ProjectedFlow(
                            date=start + timedelta(days=30 * month),
                            amount=-fact.amount,
                            kind="expense",
                            category="childcare",
                            description=f"new recurring commitment ({message.message_id})",
                            source_id=message.message_id,
                            recurring_key=f"childcare:{message.message_id}",
                        )
                    )
            elif fact.fact_type == "expense_change" and fact.amendment == "rent_increase_12pct":
                rent_factor = Decimal("1.12")

    by_id = {e.event_id: e for e in events}

    # ---- income-only model ----
    income_flows: List[ProjectedFlow] = []
    salary_events = sorted(
        [e for e in events if e.event_type == "income" and e.category == "salary" and e.status == "settled"],
        key=lambda e: e.event_date,
    )
    salary_amount = ZERO
    pay_day = 15
    if salary_events:
        amounts = [e.amount for e in salary_events if e.amount is not None]
        if amounts:
            salary_amount = Decimal(str(statistics.median([float(a) for a in amounts[-3:]])))
        pay_day = statistics.mode([e.event_date.day for e in salary_events])
    if salary_replace_amount is not None and not stop_income:
        salary_amount = salary_replace_amount
    if salary_amount > 0 and not stop_income:
        for month_index in range(4):
            month = request.request_date.month + month_index
            year = request.request_date.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            day = pay_day if pay_day <= 28 else 28
            if month_index == 0 and salary_replace_date is not None:
                income_flows.append(
                    ProjectedFlow(date=salary_replace_date, amount=salary_amount, kind="income", category="salary",
                                  description="projected salary", source_id=f"proj_{month_index}", recurring_key="salary")
                )
                continue
            income_flows.append(
                ProjectedFlow(date=date(year, month, day), amount=salary_amount, kind="income", category="salary",
                              description="projected salary", source_id=f"proj_{month_index}", recurring_key="salary")
            )

    # real non-salary events
    real_flows: List[ProjectedFlow] = []
    for event in events:
        settle = event.settlement_date or event.event_date
        if not (request.request_date <= settle < horizon_end):
            continue
        if event.event_type == "income" and event.category == "salary":
            continue
        amount = event.amount
        if amount is None:
            continue
        if event.status == "pending" and event.direction == "credit":
            continue
        if event.status in {"cancelled", "failed", "unrealized"}:
            continue
        home_amt = home_amount(store, home, event, None)
        sign = -1 if event.direction == "debit" else 1
        real_flows.append(
            ProjectedFlow(date=settle, amount=sign * home_amt, kind=event.event_type, category=event.category,
                          description=event.description, source_id=event.event_id)
        )

    model_a = sorted(income_flows + real_flows + one_time_incomes, key=lambda f: (f.date, f.source_id))

    # ---- median-day model: clamp to monthly median of model A ----
    def median_clamp(flows: List[ProjectedFlow]) -> List[ProjectedFlow]:
        by_month: Dict[Tuple[int, int], List[Decimal]] = defaultdict(list)
        for flow in flows:
            by_month[(flow.date.year, flow.date.month)].append(flow.amount)
        clamped = []
        seen_months = set()
        for flow in flows:
            key = (flow.date.year, flow.date.month)
            if key not in seen_months and by_month[key]:
                med = Decimal(str(statistics.median([float(v) for v in by_month[key]])))
                seen_months.add(key)
                clamped.append(
                    ProjectedFlow(date=date(flow.date.year, flow.date.month, min(15, 28)), amount=med,
                                  kind="clamp", category="median", description="monthly median clamp",
                                  source_id=f"clamp_{key[0]}{key[1]:02d}")
                )
        return sorted(clamped, key=lambda f: (f.date, f.source_id))

    model_b = median_clamp(model_a)

    # ---- strict recurring model: income + strictly periodic debits ----
    strict = model_a[:]
    groups: Dict[Tuple, List] = defaultdict(list)
    for event in events:
        if event.event_type in {"expense", "subscription", "debt_payment"} and event.status == "settled":
            groups[(event.event_type, event.category, event.description)].append(event)
    for (event_type, category, description), items in groups.items():
        if len(items) < 3:
            continue
        items = sorted(items, key=lambda e: e.event_date)
        intervals = [(b.event_date - a.event_date).days for a, b in zip(items, items[1:])]
        if len(intervals) < 2:
            continue
        interval = int(statistics.median(intervals))
        if abs(interval - 30) > 3:
            continue
        amounts = [e.amount for e in items if e.amount is not None]
        median_amount = Decimal(str(statistics.median([float(a) for a in amounts[-4:]])))
        if not all(abs(a - median_amount) <= median_amount * Decimal("0.15") for a in amounts[-4:]):
            continue
        last = items[-1]
        factor = rent_factor if category == "rent" else Decimal(1)
        next_date = last.event_date + timedelta(days=interval)
        while next_date < request.request_date:
            next_date += timedelta(days=interval)
        for occurrence in range(4):
            strict.append(
                ProjectedFlow(date=next_date + timedelta(days=interval * occurrence),
                              amount=-(median_amount * factor), kind=event_type, category=category,
                              description=f"recurring {description}", source_id=last.event_id,
                              recurring_key=f"{category}:{description}")
            )
    model_c = sorted(strict, key=lambda f: (f.date, f.source_id))

    # ---- full model without provision ----
    model_d = sorted([f for f in ledger.flows if f.category != "variable_essential"], key=lambda f: (f.date, f.source_id))

    return {"A": model_a, "B": model_b, "C": model_c, "D": model_d}


def safe_amount_for(balance: Decimal, minimum: Decimal, request: Request, flows: List[ProjectedFlow]) -> Decimal:
    quantum = Decimal("0.01") if request.requested_amount.as_tuple().exponent < 0 else Decimal("1")

    def ok(x: Decimal) -> bool:
        bal = balance
        for day_offset in range(92):
            day = request.request_date + timedelta(days=day_offset)
            day_flows = [f for f in flows if f.date == day]
            bal += sum((f.amount for f in day_flows), ZERO)
            if day == request.request_date:
                bal -= x
            if bal < minimum:
                return False
        return True

    if request.requested_amount <= 0:
        return ZERO
    if ok(request.requested_amount):
        return request.requested_amount
    slack = balance - minimum
    if slack <= 0:
        return ZERO
    low, high = ZERO, min(request.requested_amount, slack)
    if not ok(high):
        low, high = ZERO, high
        while high - low > quantum:
            mid = ((low + high) / 2).quantize(quantum)
            if mid <= low:
                break
            if ok(mid):
                low = mid
            else:
                high = mid
        return low
    low, high = min(request.requested_amount, slack), request.requested_amount
    while high - low > quantum:
        mid = ((low + high) / 2).quantize(quantum)
        if mid <= low:
            break
        if ok(mid):
            low = mid
        else:
            high = mid
    return low


def earliest_for(balance: Decimal, minimum: Decimal, request: Request, flows: List[ProjectedFlow]):
    def ok(day_offset: int) -> bool:
        pay_day = request.request_date + timedelta(days=day_offset)
        bal = balance
        for offset in range(day_offset + 1):
            day = request.request_date + timedelta(days=offset)
            bal += sum((f.amount for f in flows if f.date == day), ZERO)
            if offset == day_offset:
                bal -= request.requested_amount
            if bal < minimum:
                return False
        return True

    for day_offset in range(91):
        if ok(day_offset):
            return request.request_date + timedelta(days=day_offset)
    return None


def main() -> None:
    store = DataStore()
    samples = load_samples()
    score = {k: {"safe": 0, "earliest": 0} for k in "ABCD"}
    for sample in samples:
        request = sample.request
        gold_safe = Decimal(sample.gold["amount_safe_to_pay"] or "0")
        gold_earliest = sample.gold["earliest_date_for_full_payment"]
        profile = store.profile_for(request.user_id)
        print("=" * 110)
        print(f"{request.request_id} {request.user_id} GOLD safe={gold_safe} earliest={gold_earliest or '-'}")
        models = build_models(store, request)
        for name, flows in models.items():
            safe_amount = safe_amount_for(profile.current_available_balance, profile.minimum_balance_to_keep, request, flows)
            earliest = earliest_for(profile.current_available_balance, profile.minimum_balance_to_keep, request, flows)
            safe_ok = safe_amount == gold_safe
            earliest_ok = (earliest.isoformat() if earliest else "") == gold_earliest
            if safe_ok:
                score[name]["safe"] += 1
            if earliest_ok:
                score[name]["earliest"] += 1
            print(
                f"  {name}: safe={safe_amount}{'=' if safe_ok else 'X'} earliest={earliest}{'=' if earliest_ok else 'X'}"
            )
    print()
    print(score)


if __name__ == "__main__":
    main()
