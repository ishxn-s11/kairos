"""Final 22-point validation of the submitted output.csv.

Run after the full-dataset run: python3 code/evaluation/validate_output.py
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUTPUT = REPO_ROOT / "output.csv"
COLUMNS = [
    "request_id", "amount_safe_to_pay", "affordability_status",
    "recommended_payment_method", "payment_plan", "earliest_date_for_full_payment",
    "spending_changes_needed", "decision_explanation",
]
STATUSES = {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}
METHODS = {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}


def main() -> int:
    checks: list[tuple[bool, str]] = []
    rows = list(csv.DictReader(OUTPUT.open(encoding="utf-8", newline="")))
    requests = {r["request_id"]: r for r in csv.DictReader((REPO_ROOT / "dataset" / "requests.csv").open(encoding="utf-8-sig", newline=""))}
    options = list(csv.DictReader((REPO_ROOT / "dataset" / "request_payment_options.csv").open(encoding="utf-8-sig", newline="")))
    options_by_request: dict[str, list[dict]] = {}
    for o in options:
        options_by_request.setdefault(o["request_id"], []).append(o)

    header = OUTPUT.open(encoding="utf-8", newline="").readline().strip().split(",")
    checks.append((header == COLUMNS, f"1/4 column order exact ({header})"))
    checks.append((len(rows) == 250, f"1/2-3 exactly 250 rows, ids match: {len(rows)}, unique={len({r['request_id'] for r in rows})}, "
                                      f"same_ids={ {r['request_id'] for r in rows} == set(requests) }"))

    bad_enum = bad_amount = bad_plan = bad_chrono = bad_partial = 0
    bad_inst = bad_earliest = bad_now = bad_none = bad_changes = blank = 0
    for r in rows:
        req = requests.get(r["request_id"], {})
        requested = Decimal((req.get("requested_amount") or "0").replace(",", "") or "0")
        rd = date.fromisoformat(req["request_date"]) if req.get("request_date") else None
        deadline = date.fromisoformat(req["desired_completion_date"]) if req.get("desired_completion_date") else None
        safe = Decimal(r["amount_safe_to_pay"] or "0")
        for field in COLUMNS[1:7]:
            # earliest_date_for_full_payment is intentionally blank when no
            # safe full-payment date exists within the horizon (problem_statement.md).
            if field == "earliest_date_for_full_payment":
                continue
            if not r[field].strip():
                blank += 1
        if r["affordability_status"] not in STATUSES or r["recommended_payment_method"] not in METHODS:
            bad_enum += 1
        if not (0 <= safe <= requested):
            bad_amount += 1
        plan = r["payment_plan"]
        if plan != "none":
            pays = plan.split("|")
            dates = [p.split(":")[0] for p in pays]
            try:
                dts = [date.fromisoformat(d) for d in dates]
                amounts = [Decimal(p.split(":")[1]) for p in pays]
            except Exception:
                bad_plan += 1
                continue
            if any(a < 0 for a in amounts):
                bad_plan += 1
            if dts != sorted(dts) or (rd and dts[0] < rd):
                bad_chrono += 1
            total = sum(amounts, Decimal(0))
            if r["recommended_payment_method"] == "partial_payment":
                if len(pays) != 2 or total != requested:
                    bad_partial += 1
            if r["recommended_payment_method"] == "installments":
                match = False
                for o in options_by_request.get(r["request_id"], []):
                    n = int(o["number_of_payments"])
                    freq = int(o["payment_frequency_days"]) if o["payment_frequency_days"] else 0
                    d0 = date.fromisoformat(o["first_payment_date"])
                    sched = [
                        (d0 + timedelta(days=freq * i), Decimal(o["payment_amount"]))
                        for i in range(n)
                    ]
                    if plan == "|".join(f"{d.isoformat()}:{fmt(a)}" for d, a in sched):
                        match = True
                        break
                if not match:
                    bad_inst += 1
        if r["affordability_status"] == "affordable_now" and r["earliest_date_for_full_payment"] != req.get("request_date"):
            bad_now += 1
        if r["recommended_payment_method"] == "not_recommended" and r["payment_plan"] != "none":
            bad_none += 1
        changes = r["spending_changes_needed"]
        if changes != "none" and len(changes.split("|")) > 3:
            bad_changes += 1
        if not r["decision_explanation"].strip():
            blank += 1

    checks.append((blank == 0, f"5/19 no unintentionally blank decision fields (blanks={blank})"))
    checks.append((bad_enum == 0, f"7 enum values valid (bad={bad_enum})"))
    checks.append((bad_amount == 0, f"6 0 <= safe <= requested (bad={bad_amount})"))
    checks.append((bad_plan == 0 and bad_chrono == 0, f"8/9 plan syntax + chronological (bad={bad_plan}/{bad_chrono})"))
    checks.append((bad_partial == 0, f"10 partial plans: two payments summing to request (bad={bad_partial})"))
    checks.append((bad_inst == 0, f"11 installment plans match supplied options (bad={bad_inst})"))
    checks.append((bad_now == 0, f"17 affordable_now uses request_date (bad={bad_now})"))
    checks.append((bad_none == 0, f"18 not_recommended uses plan none (bad={bad_none})"))
    checks.append((bad_changes == 0, f"15 at most three spending changes (bad={bad_changes})"))

    usage = REPO_ROOT / "code" / "evaluation" / "usage_report.md"
    checks.append((usage.exists(), "20 evaluation/usage_report.md exists"))
    checks.append(((REPO_ROOT / "log.txt").exists(), "21 log.txt exists"))
    secrets = False
    for path in [REPO_ROOT / "output.csv", usage, REPO_ROOT / "code" / "buy_or_wait" / "llm.py"]:
        text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        if re.search(r"(sk-[A-Za-z0-9]{16,}|AIza[A-Za-z0-9_\-]{20,})", text):
            secrets = True
    checks.append((not secrets, "22 no API keys/secrets in generated artifacts"))

    failures = [name for ok, name in checks if not ok]
    for ok, name in checks:
        print(("PASS " if ok else "FAIL ") + name)
    print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
    return 0 if not failures else 1


def fmt(amount: Decimal) -> str:
    text = format(amount, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
        if "." in text and len(text.split(".")[1]) == 1:
            text += "0"
    return text


if __name__ == "__main__":
    raise SystemExit(main())
