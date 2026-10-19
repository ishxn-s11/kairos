"""Freelancer mode: invoice-aware, variable-income cash-flow projection.

Extends the deterministic engine for irregular earners without touching the
core ledger logic. Two ideas:

* **Certainty classification.** Every outstanding invoice is classified so that
  *confirmed* incoming cash is projected (it is reliable) while *expected but
  uncertain* receivables are **never** treated as guaranteed deposits in the
  baseline — they are only surfaced under the uncertainty scenarios
  (``scenarios.py``), which is exactly the financially safer reading the engine
  already applies to pending credits.

* **Invoice-aware projection.** Confirmed invoices become dated ``income`` flows
  inside the forecast horizon, converted at the dated FX rate. Paid/settled
  invoices are skipped (already reflected in the starting balance).

All monetary work is Decimal and delegated to the shared simulator; this module
only decides *which* flows exist and *when*.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import config, fx
from .ledger import LedgerBuilder, ProjectedFlow, UserLedger
from .loader import DataStore, Request, parse_amount, parse_date

ZERO = Decimal(0)

# Certainty buckets. Anything unrecognised is treated as at-risk (safer reading).
SETTLED_STATUSES = {"paid", "received", "settled"}
CONFIRMED_STATUSES = {"confirmed", "client_confirmed"}
AT_RISK_STATUSES = {"expected", "pending", "overdue", "sent", "unconfirmed", "disputed"}


@dataclass
class Invoice:
    """A freelancer receivable (outstanding invoice / expected client payment)."""

    invoice_id: str
    client: str
    amount: Decimal
    currency: str
    issue_date: Optional[date]
    due_date: Optional[date]
    status: str
    expected_payment_date: Optional[date] = None
    user_id: str = ""
    confidence: Optional[Decimal] = None  # reporting only; never used in arithmetic

    @property
    def certainty(self) -> str:
        s = (self.status or "").strip().lower()
        if s in SETTLED_STATUSES:
            return "settled"
        if s in CONFIRMED_STATUSES:
            return "confirmed"
        return "at_risk"

    @property
    def receipt_date(self) -> Optional[date]:
        """Forward-looking cash date: expected date if given, else the due date."""
        return self.expected_payment_date or self.due_date


def load_invoices(path: Optional[Path] = None) -> List[Invoice]:
    """Load invoices from CSV if present; returns [] when the file is absent.

    Expected columns (header): invoice_id, user_id, client, amount, currency,
    issue_date, due_date, status, expected_payment_date, confidence.
    """
    if path is None:
        return []
    if not Path(path).exists():
        return []
    invoices: List[Invoice] = []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            invoices.append(
                Invoice(
                    invoice_id=row.get("invoice_id", ""),
                    client=row.get("client", ""),
                    amount=parse_amount(row.get("amount", "")) or ZERO,
                    currency=(row.get("currency") or "").strip(),
                    issue_date=parse_date(row.get("issue_date", "")),
                    due_date=parse_date(row.get("due_date", "")),
                    status=(row.get("status") or "").strip().lower(),
                    expected_payment_date=parse_date(row.get("expected_payment_date", "")),
                    user_id=row.get("user_id", ""),
                    confidence=parse_amount(row.get("confidence", "")),
                )
            )
    return invoices


def project_invoices(
    invoices: List[Invoice],
    request: Request,
    home_currency: str,
) -> Tuple[List[ProjectedFlow], List[ProjectedFlow]]:
    """Split invoices into (confirmed_flows, at_risk_flows) within the horizon.

    Confirmed flows are projected in the baseline; at-risk flows are excluded
    from the baseline and only injected by the uncertainty scenarios. Settled
    invoices and dates outside the horizon are dropped.
    """
    start = request.request_date
    end = start + timedelta(days=config.FORECAST_DAYS)
    confirmed: List[ProjectedFlow] = []
    at_risk: List[ProjectedFlow] = []

    for inv in invoices:
        if inv.user_id and request.user_id and inv.user_id != request.user_id:
            continue
        cert = inv.certainty
        if cert == "settled":
            continue  # already reflected in the starting balance
        when = inv.receipt_date
        if when is None or not (start <= when <= end):
            continue  # no reliable future date inside the forecast window
        if not inv.currency or inv.currency == home_currency:
            amount = inv.amount
        else:
            amount = fx.convert(inv.amount, inv.currency, home_currency, when)
        flow = ProjectedFlow(
            date=when,
            amount=amount,  # positive = cash in
            kind="income",
            category="invoice",
            description=f"invoice {inv.invoice_id} ({inv.client or 'client'}) [{cert}]",
            source_id=inv.invoice_id or f"inv_{inv.invoice_id}",
        )
        (confirmed if cert == "confirmed" else at_risk).append(flow)

    confirmed.sort(key=lambda f: f.date)
    at_risk.sort(key=lambda f: f.date)
    return confirmed, at_risk


def build_freelancer_ledger(
    store: DataStore,
    request: Request,
    invoices: Optional[List[Invoice]] = None,
) -> Tuple[UserLedger, List[ProjectedFlow]]:
    """Return ``(ledger_with_confirmed_invoice_income, at_risk_flows)``.

    The base ledger is unchanged for users with no confirmed invoices, so
    personal-finance behaviour is preserved. ``at_risk_flows`` are handed to the
    scenario runner — they are deliberately NOT in the baseline ledger.
    """
    ledger = LedgerBuilder(store).build(request)
    profile = store.profile_for(request.user_id)
    invoices = invoices if invoices is not None else []
    confirmed, at_risk = project_invoices(invoices, request, profile.home_currency)
    if not confirmed:
        return ledger, at_risk
    merged = replace(ledger, flows=list(ledger.flows) + confirmed)
    return merged, at_risk


def variable_income_summary(invoices: List[Invoice], home_currency: str = "") -> Dict[str, object]:
    """Reporting-only breakdown of receivables by certainty (no arithmetic on forecasts)."""
    buckets: Dict[str, Decimal] = {"settled": ZERO, "confirmed": ZERO, "at_risk": ZERO}
    counts: Dict[str, int] = {"settled": 0, "confirmed": 0, "at_risk": 0}
    for inv in invoices:
        c = inv.certainty
        buckets[c] += inv.amount
        counts[c] += 1
    return {
        "home_currency": home_currency,
        "totals_by_certainty": dict(buckets),
        "counts_by_certainty": dict(counts),
        "outstanding_confirmed": buckets["confirmed"],
        "outstanding_at_risk": buckets["at_risk"],
        "count": len(invoices),
    }
