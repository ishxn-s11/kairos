"""Buy or Wait? — main entry point.

Runs the hybrid affordability agent over every request in dataset/requests.csv
(or --requests) and writes output.csv (or --output) in the repository root.

Usage:
    python3 code/main.py
    python3 code/main.py --requests dataset/requests.csv --output output.csv
    python3 code/main.py --debug request_101
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from buy_or_wait.loader import DataStore, load_requests  # noqa: E402
from buy_or_wait.pipeline import decide  # noqa: E402
from buy_or_wait.forecast import fmt_amount  # noqa: E402
from buy_or_wait.usage import TRACKER, write_usage_report  # noqa: E402

OUTPUT_COLUMNS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Buy or Wait? affordability agent")
    parser.add_argument("--requests", default=str(REPO_ROOT / "dataset" / "requests.csv"))
    parser.add_argument("--output", default=str(REPO_ROOT / "output.csv"))
    parser.add_argument("--debug", nargs="?", const="__all__", default=None,
                        help="print structured diagnostics (optionally only for one request id)")
    return parser.parse_args(argv)


def run(argv=None) -> int:
    args = parse_args(argv)
    store = DataStore()
    requests = load_requests(Path(args.requests))

    rows = []
    for index, request in enumerate(requests, start=1):
        decision = decide(store, request)
        rows.append(
            {
                "request_id": decision.request_id,
                "amount_safe_to_pay": fmt_amount(decision.amount_safe_to_pay),
                "affordability_status": decision.affordability_status,
                "recommended_payment_method": decision.recommended_payment_method,
                "payment_plan": decision.payment_plan,
                "earliest_date_for_full_payment": decision.earliest_date_for_full_payment,
                "spending_changes_needed": decision.spending_changes_needed,
                "decision_explanation": decision.decision_explanation,
            }
        )
        if args.debug and (args.debug == "__all__" or args.debug == request.request_id):
            print(
                f"[{index}/{len(requests)}] {request.request_id} "
                f"{decision.affordability_status} {decision.recommended_payment_method} "
                f"safe={decision.amount_safe_to_pay} plan={decision.payment_plan[:60]}",
                flush=True,
            )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    write_usage_report(len(rows), REPO_ROOT / "code" / "evaluation" / "usage_report.md")
    print(f"Wrote {len(rows)} predictions to {output_path}")
    totals = TRACKER.grand_totals()
    print(f"Model calls: {totals['calls']}, tokens: {totals['in'] + totals['out']}, est. cost: ${totals['cost']:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
