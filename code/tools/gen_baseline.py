"""Generate frontend/baseline.json: the deterministic engine's full decision set.

Runs every dataset request twice through the real pipeline (code/buy_or_wait)
to confirm bit-identical determinism, then writes the verified rows as JSON for
the frontend test-bench page (offline agent testing + output.csv comparison).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "code"))

from buy_or_wait.loader import DataStore, load_requests  # noqa: E402
from buy_or_wait.pipeline import decide  # noqa: E402


def main() -> int:
    store = DataStore()
    requests = load_requests(REPO_ROOT / "dataset" / "requests.csv")

    first = []
    for request in requests:
        d = decide(store, request)
        profile = store.profile_for(request.user_id)
        first.append(
            {
                "request_id": d.request_id,
                "amount": str(d.amount_safe_to_pay),
                "status": d.affordability_status,
                "method": d.recommended_payment_method,
                "plan": d.payment_plan,
                "earliest": d.earliest_date_for_full_payment,
                "spending": d.spending_changes_needed,
                "explanation": d.decision_explanation,
                "facts": {
                    "user_id": request.user_id,
                    "home_currency": profile.home_currency,
                    "requested_amount": str(request.requested_amount),
                    "request_date": request.request_date.isoformat(),
                    "desired_completion_date": request.desired_completion_date.isoformat(),
                },
            }
        )

    # determinism proof: run everything a second time and compare
    second = []
    for request in requests:
        d = decide(store, request)
        second.append(
            {
                "request_id": d.request_id,
                "amount": str(d.amount_safe_to_pay),
                "status": d.affordability_status,
                "method": d.recommended_payment_method,
                "plan": d.payment_plan,
                "earliest": d.earliest_date_for_full_payment,
                "spending": d.spending_changes_needed,
                "explanation": d.decision_explanation,
            }
        )

    decision_fields = ("request_id", "amount", "status", "method", "plan", "earliest", "spending", "explanation")
    strip = lambda rows: [{k: r[k] for k in decision_fields} for r in rows]
    if strip(first) != strip(second):
        differing = [a["request_id"] for a, b in zip(strip(first), strip(second)) if a != b]
        print(f"NON-DETERMINISTIC for {differing[:5]}", file=sys.stderr)
        return 1

    out = REPO_ROOT / "frontend" / "baseline.json"
    out.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(first)} baseline decisions to {out} (deterministic: double-run identical)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
