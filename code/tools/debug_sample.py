"""Dump the engine's internal facts for one sample request, next to the gold row.

Usage:
    python code/tools/debug_sample.py request_02 [more_ids...]

Prints the reconstructed ledger, safe amount, earliest full date, generated
candidates and the gold-vs-predicted fields so mismatches can be explained.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buy_or_wait.forecast import fmt_amount  # noqa: E402
from buy_or_wait.loader import DataStore, load_samples  # noqa: E402
from buy_or_wait.plan_generator import CandidateGenerator  # noqa: E402
from buy_or_wait.pipeline import decide  # noqa: E402


def dump(store: DataStore, sample) -> None:
    request, gold = sample.request, sample.gold
    ledger = store_ledger(store, request)
    gen = CandidateGenerator(ledger, store.options_for(request.request_id))
    decision = decide(store, request)

    print("=" * 78)
    print(f"{request.request_id} [{request.user_id}]  {request.request_text[:70]}")
    print(
        f"  request_date={request.request_date} requested={fmt_amount(request.requested_amount)} "
        f"desired_by={request.desired_completion_date} partial={request.allows_partial_payment}"
    )
    profile = ledger.profile
    print(
        f"  balance={fmt_amount(ledger.starting_balance)} minimum={fmt_amount(ledger.minimum_balance)} "
        f"methods={','.join(profile.payment_methods_user_will_consider)} "
        f"max_inst_months={profile.max_installment_months}"
    )
    print(
        f"  reduce_ok={profile.expense_categories_user_is_willing_to_reduce} "
        f"stop_ok={profile.expense_categories_user_is_willing_to_stop} "
        f"protected={profile.expense_categories_to_protect}"
    )
    print(f"  pending_debit_reserve={sum(f.amount for f in ledger.flows if f.amount < 0 and f.kind == 'pending')}")
    debits = [f for f in ledger.flows if f.amount < 0]
    credits = [f for f in ledger.flows if f.amount > 0]
    print(f"  flows: {len(debits)} debits, {len(credits)} credits; first 8 by date:")
    for flow in sorted(ledger.flows, key=lambda f: f.date)[:8]:
        print(
            f"    {flow.date} {fmt_amount(flow.amount):>14} {flow.kind:<12} {flow.category:<18} "
            f"flex={flow.flexible!s:<5} {flow.source_id}"
        )
    print(f"  engine: safe_amount={fmt_amount(gen.safe_amount)} earliest_full={gen.earliest_full_date}")
    for candidate in gen.generate():
        print(
            f"    cand {candidate.method:<15} start={candidate.first_payment_date} "
            f"n={candidate.number_of_payments} total={fmt_amount(candidate.total_payable)} "
            f"changes={candidate.spending_changes_needed()}"
        )
    print(f"  DECISION: status={decision.affordability_status} method={decision.recommended_payment_method} "
          f"safe={fmt_amount(decision.amount_safe_to_pay)} earliest={decision.earliest_date_for_full_payment}")
    print(f"            plan={decision.payment_plan}")
    print(f"            changes={decision.spending_changes_needed}")
    print(f"            expl={decision.decision_explanation}")
    print(f"  GOLD:     status={gold.get('affordability_status')} method={gold.get('recommended_payment_method')} "
          f"safe={gold.get('amount_safe_to_pay')} earliest={gold.get('earliest_date_for_full_payment')}")
    print(f"            plan={gold.get('payment_plan')}")
    print(f"            changes={gold.get('spending_changes_needed')}")
    print(f"            expl={gold.get('decision_explanation')}")


def store_ledger(store: DataStore, request):
    from buy_or_wait.ledger import LedgerBuilder

    return LedgerBuilder(store).build(request)


def main(argv=None) -> int:
    args = [a for a in (argv or sys.argv[1:])]
    store = DataStore()
    wanted = set(args) if args else None
    for sample in load_samples():
        if wanted is None or sample.request.request_id in wanted:
            dump(store, sample)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
