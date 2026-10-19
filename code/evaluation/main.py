"""Sample evaluation: run the pipeline on sample_requests.csv using ONLY the
input columns, then compare predictions with the gold outputs.

Never passes gold columns into the inference pipeline (see tests/test_output.py).
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buy_or_wait.forecast import fmt_amount  # noqa: E402
from buy_or_wait.loader import DataStore, load_samples  # noqa: E402
from buy_or_wait.pipeline import decide  # noqa: E402

GOLD_FIELDS = [
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]


def normalize_amount(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    try:
        return fmt_amount(Decimal(text.replace(",", "")))
    except Exception:
        return text


def normalize(text: str) -> str:
    return (text or "").strip()


def evaluate(sample_limit: int | None = None, show_all: bool = False) -> float:
    store = DataStore()
    samples = load_samples()
    if sample_limit:
        samples = samples[:sample_limit]

    field_hits: dict[str, int] = {f: 0 for f in GOLD_FIELDS if f != "decision_explanation"}
    explanation_consistent = 0
    mismatches: list[tuple[str, str, str, str]] = []

    for sample in samples:
        request = sample.request
        gold = sample.gold
        decision = decide(store, request)

        predicted = {
            "amount_safe_to_pay": fmt_amount(decision.amount_safe_to_pay),
            "affordability_status": decision.affordability_status,
            "recommended_payment_method": decision.recommended_payment_method,
            "payment_plan": decision.payment_plan,
            "earliest_date_for_full_payment": decision.earliest_date_for_full_payment,
            "spending_changes_needed": decision.spending_changes_needed,
            "decision_explanation": decision.decision_explanation,
        }

        row_ok = True
        for field_name in field_hits:
            expected = normalize(gold.get(field_name, ""))
            actual = predicted[field_name]
            if field_name == "amount_safe_to_pay":
                ok = normalize_amount(expected) == normalize_amount(actual)
            else:
                ok = expected == actual
            if ok:
                field_hits[field_name] += 1
            else:
                row_ok = False
                mismatches.append((request.request_id, field_name, expected, actual))

        # Explanation consistency check: the decision explanation must mention
        # the numbers of the structured decision.
        exp = predicted["decision_explanation"].replace(",", "")
        safe_txt = predicted["amount_safe_to_pay"].replace(",", "")
        consistent = True
        if predicted["recommended_payment_method"] == "installments":
            consistent = str(len(predicted["payment_plan"].split("|"))) in exp
        if predicted["amount_safe_to_pay"] not in ("0",) and predicted["affordability_status"] == "affordable_now":
            consistent = consistent and normalize_amount(safe_txt) == normalize_amount(
                str(request.requested_amount)
            )
        if consistent:
            explanation_consistent += 1

        marker = "OK " if row_ok else "MISS"
        print(
            f"{marker} {request.request_id} [{request.user_id}] "
            f"safe={predicted['amount_safe_to_pay']} status={predicted['affordability_status']} "
            f"method={predicted['recommended_payment_method']} "
            f"plan={predicted['payment_plan'][:48]} earliest={predicted['earliest_date_for_full_payment']} "
            f"changes={predicted['spending_changes_needed'][:32]}"
        )
        if not row_ok or show_all:
            print(f"     gold status={gold.get('affordability_status')} method={gold.get('recommended_payment_method')} "
                  f"safe={gold.get('amount_safe_to_pay')} earliest={gold.get('earliest_date_for_full_payment')} "
                  f"changes={gold.get('spending_changes_needed')}")
            print(f"     gold plan={gold.get('payment_plan')}")
            print(f"     gold expl={gold.get('decision_explanation')[:140]}")
            print(f"     pred expl={predicted['decision_explanation'][:140]}")

    total = len(samples)
    print("\n===== FIELD ACCURACY =====")
    for field_name, hits in field_hits.items():
        print(f"  {field_name:32s} {hits}/{total}  ({hits / total * 100:.0f}%)")
    exact_rows = sum(
        1 for f in field_hits
    )
    overall = sum(
        1
        for sample in samples
        if all(
            normalize_amount(sample.gold[f]) == fmt_amount(decide(store, sample.request).amount_safe_to_pay)
            if False
            else True
            for f in []
        )
    )
    print(f"  explanation-consistent: {explanation_consistent}/{total}")
    print("\n===== MISMATCHES =====")
    for request_id, field_name, expected, actual in mismatches:
        print(f"  {request_id:14s} {field_name:30s} gold={expected[:60]!r} pred={actual[:60]!r}")
    return 0.0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate predictions on solved samples")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--show-all", action="store_true")
    args = parser.parse_args()
    evaluate(args.limit, args.show_all)
