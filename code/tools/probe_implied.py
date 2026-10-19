"""Probe 6: implied-gold cumulative-flow diagnostics.

For each sample the gold answers imply a minimum cumulative net flow over the
horizon:  gold_safe = bal0 + min_cum - minimum_balance   (when not capped)
This probe prints implied min_cum next to the min_cum our ledger produces, so
the missing/extra projected flows can be identified per user.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buy_or_wait.forecast import simulate  # noqa: E402
from buy_or_wait.ledger import LedgerBuilder  # noqa: E402
from buy_or_wait.loader import DataStore, load_samples  # noqa: E402

ZERO = Decimal(0)


def min_cum(flows, bal0, rd, days=91):
    cum = ZERO
    lowest = ZERO
    by_day = {}
    for f in flows:
        if rd <= f.date < rd + timedelta(days=days):
            by_day[f.date] = by_day.get(f.date, ZERO) + f.amount
    lowest_day = None
    for offset in range(days):
        day = rd + timedelta(days=offset)
        cum += by_day.get(day, ZERO)
        if cum < lowest:
            lowest = cum
            lowest_day = day
    return lowest, lowest_day, by_day


def main() -> None:
    store = DataStore()
    samples = load_samples()
    only = sys.argv[1:] or None
    for sample in samples:
        request = sample.request
        if only and request.request_id not in only:
            continue
        profile = store.profile_for(request.user_id)
        gold_safe = Decimal(sample.gold["amount_safe_to_pay"] or "0")
        bal0 = profile.current_available_balance
        mn = profile.minimum_balance_to_keep
        implied = gold_safe - bal0 + mn
        capped = gold_safe >= request.requested_amount

        builder = LedgerBuilder(store)
        ledger = builder.build(request)
        lowest, lowest_day, by_day = min_cum(ledger.flows, bal0, request.request_date)
        ours = bal0 + lowest - mn

        print("=" * 100)
        print(
            f"{request.request_id} [{request.user_id}] req={request.requested_amount} rd={request.request_date} "
            f"bal0={bal0} min={mn}"
        )
        print(f"  gold: safe={gold_safe} status={sample.gold['affordability_status']} "
              f"method={sample.gold['recommended_payment_method']} earliest={sample.gold['earliest_date_for_full_payment'] or '-'} "
              f"changes={sample.gold['spending_changes_needed']}")
        print(f"  implied min_cum={'n/a (capped)' if capped else implied}   our min_cum={ours} (lowest day {lowest_day})")
        if not capped:
            gap = implied - ours
            print(f"  GAP (gold more outflow if negative): {gap}")
        # flow listing grouped by date for manual inspection
        for day in sorted(by_day):
            entries = [f for f in ledger.flows if f.date == day]
            for f in entries:
                print(f"    {f.date} {f.amount:>14} {f.category:18s} {f.kind:12s} {f.description[:44]}")


if __name__ == "__main__":
    main()
