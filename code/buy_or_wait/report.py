"""Explainable purchase-decision reports.

Builds a financial decision report whose numbers all originate from either

* **verified input** — the user's profile (available balance, reserve, currency)
  and request fields, or
* **deterministic simulation** — the decision row and the dated cash-flow rows
  produced by ``simulate`` via ``Analysis.cashflow()``.

No number is recomputed or invented here; this module only formats what the
engine already produced. Includes the dated cash-flow table, upcoming confirmed
obligations, forecast income, payment options compared, (optional) uncertainty
scenarios, and an assumptions / missing-information section.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from . import config
from .pipeline import Analysis

try:  # optional; avoids a hard import cycle if scenarios is not loaded
    from .scenarios import ScenarioReport
except Exception:  # pragma: no cover
    ScenarioReport = None  # type: ignore

ZERO = Decimal(0)


def _money(amount: Optional[Decimal]) -> str:
    if amount is None:
        return ""
    text = f"{amount:,.2f}"
    if text.endswith(".00"):
        text = text[:-3]
    return text


def _dmy(d: Optional[date]) -> str:
    if d is None:
        return ""
    return f"{d.day} {d.strftime('%B %Y')}"


def _iso(d: Optional[date]) -> str:
    return d.isoformat() if d else ""


@dataclass
class DecisionReport:
    analysis: Analysis
    invoices_summary: Optional[Dict[str, object]] = None
    scenario_report: Optional["ScenarioReport"] = None
    max_rows: Optional[int] = None  # None = include every forecast day

    # ------------------------------------------------------------------ #
    # Structured output
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict:
        a = self.analysis
        dec = a.decision
        ledger = a.ledger
        prof = ledger.profile
        req = a.request
        cf = a.cashflow()

        rows = cf.rows if self.max_rows is None else cf.rows[: self.max_rows]
        horizon_end = req.request_date + _timedelta(config.FORECAST_DAYS)
        obligations = [
            f for f in ledger.flows
            if f.amount < 0 and req.request_date <= f.date <= horizon_end
        ]
        income = [
            f for f in ledger.flows
            if f.amount >= 0 and f.kind == "income" and req.request_date <= f.date <= horizon_end
        ]

        return {
            "request": {
                "request_id": req.request_id,
                "request_date": req.request_date.isoformat(),
                "requested_amount": str(req.requested_amount),
                "desired_completion_date": req.desired_completion_date.isoformat(),
                "request_text": req.request_text,
            },
            "position": {  # verified input from the profile
                "home_currency": prof.home_currency,
                "available_balance": str(ledger.starting_balance),
                "minimum_balance_to_keep": str(ledger.minimum_balance),
            },
            "decision": {  # computed by the deterministic pipeline
                "affordability_status": dec.affordability_status,
                "amount_safe_to_pay": str(dec.amount_safe_to_pay),
                "recommended_payment_method": dec.recommended_payment_method,
                "payment_plan": dec.payment_plan,
                "earliest_date_for_full_payment": dec.earliest_date_for_full_payment,
                "spending_changes_needed": dec.spending_changes_needed,
                "decision_explanation": dec.decision_explanation,
                "min_closing_balance": str(cf.min_closing_balance),
                "min_margin": str(cf.min_margin),
                "forecast_safe": cf.safe,
                "breach_date": cf.min_date.isoformat() if (not cf.safe and cf.min_date) else "",
            },
            "cashflow": [
                {
                    "date": r.date.isoformat(),
                    "opening": str(r.opening_balance),
                    "credits": str(r.credits),
                    "debits": str(r.debits),
                    "purchase_payments": str(r.candidate_request_payments),
                    "closing": str(r.closing_balance),
                    "reserve": str(r.minimum_balance_to_keep),
                    "margin": str(r.remaining_safety_margin),
                }
                for r in rows
            ],
            "obligations": [
                {"date": f.date.isoformat(), "amount": str(f.amount),
                 "category": f.category, "description": f.description, "source_id": f.source_id}
                for f in sorted(obligations, key=lambda x: x.date)
            ],
            "forecast_income": [
                {"date": f.date.isoformat(), "amount": str(f.amount),
                 "category": f.category, "description": f.description, "source_id": f.source_id}
                for f in sorted(income, key=lambda x: x.date)
            ],
            "payment_options_compared": [
                {
                    "method": e.candidate.method,
                    "payment_option_id": e.candidate.payment_option_id or "",
                    "total_payable": str(e.candidate.total_payable),
                    "number_of_payments": e.candidate.number_of_payments,
                    "first_payment_date": _iso(e.candidate.first_payment_date),
                    "safe": e.safe,
                    "rejection_reason": e.rejection_reason,
                    "selected": a.best is not None and e is a.best,
                }
                for e in a.evaluations
            ],
            "invoices": self.invoices_summary,
            "assumptions_and_missing": self._assumptions(),
            "scenarios": _scenario_dict(self.scenario_report),
            "provenance": {
                "note": "Every number above is verified profile input or a deterministic simulator output.",
                "forecast_days": config.FORECAST_DAYS,
                "cashflow_rows_returned": len(rows),
            },
        }

    def _assumptions(self) -> List[str]:
        a = self.analysis
        ledger = a.ledger
        notes: List[str] = []
        if ledger.ignored:
            notes.append(
                f"{len(ledger.ignored)} event(s) excluded from the forecast (pending credits, "
                "non-cash valuations, cancelled/failed, or blank amounts): "
                + "; ".join(ledger.ignored[:6])
                + (" …" if len(ledger.ignored) > 6 else "")
            )
        for amend in ledger.amendments:
            if amend.fact_type != "none":
                notes.append(f"Amendment applied ({amend.fact_type}): {amend.note or amend.source_id}")
        if ledger.fx_notes:
            notes.append(f"{len(ledger.fx_notes)} FX conversion(s) applied at dated rates.")
        if self.invoices_summary:
            s = self.invoices_summary
            notes.append(
                f"Freelancer receivables: {s.get('counts_by_certainty', {})} — confirmed cash is "
                "projected; at-risk invoices are excluded from the baseline and shown only under scenarios."
            )
        if self.scenario_report is not None:
            cfg = self.scenario_report.config
            notes.append(
                f"Scenario assumptions: delay = {cfg.delay_days} days; unexpected expense = "
                f"{_money(cfg.shock_amount)} on {cfg.shock_date}. These are explicit scenario inputs, not account facts."
            )
        if a.earliest_full_date is None:
            notes.append(
                f"No single full payment is safe within the {config.FORECAST_DAYS}-day forecast horizon."
            )
        if not notes:
            notes.append("No excluded events, FX conversions, or uncertain inputs affected this forecast.")
        return notes

    # ------------------------------------------------------------------ #
    # Markdown rendering
    # ------------------------------------------------------------------ #
    def to_markdown(self) -> str:
        d = self.to_dict()
        a = self.analysis
        dec = a.decision
        pos = d["position"]
        req = d["request"]
        dec_d = d["decision"]
        out: List[str] = []

        out.append(f"# Purchase Decision Report — {req['request_id']}")
        out.append("")
        out.append(f"- **Request date:** {_iso_and_dmy(req['request_date'])}")
        out.append(f"- **Requested amount:** {pos['home_currency']} {_money(a.request.requested_amount)}")
        out.append(f"- **Desired completion:** {_iso_and_dmy(req['desired_completion_date'])}")
        if req["request_text"]:
            out.append(f"- **Request:** {req['request_text']}")
        out.append("")

        out.append("## Financial position (verified input)")
        out.append("")
        out.append(f"| Available balance | Minimum reserve | Home currency |")
        out.append(f"|---|---|---|")
        out.append(
            f"| {pos['home_currency']} {_money(Decimal(pos['available_balance']))} "
            f"| {pos['home_currency']} {_money(Decimal(pos['minimum_balance_to_keep']))} "
            f"| {pos['home_currency']} |"
        )
        out.append("")

        out.append("## Recommendation (deterministic)")
        out.append("")
        out.append(f"- **Affordability status:** `{dec_d['affordability_status']}`")
        out.append(f"- **Payment method:** `{dec_d['recommended_payment_method']}`")
        out.append(f"- **Amount safe to pay now:** {pos['home_currency']} {_money(Decimal(dec_d['amount_safe_to_pay']))}")
        out.append(f"- **Payment plan:** `{dec_d['payment_plan']}`")
        out.append(f"- **Earliest full payment:** {dec_d['earliest_date_for_full_payment'] or '—'}")
        out.append(f"- **Spending changes needed:** `{dec_d['spending_changes_needed']}`")
        out.append(
            f"- **Forecast low point:** {pos['home_currency']} {_money(Decimal(dec_d['min_closing_balance']))} "
            f"(reserve {pos['home_currency']} {_money(Decimal(dec_d['min_margin']))} margin)"
        )
        out.append(f"- **Explanation:** {dec_d['decision_explanation']}")
        out.append("")

        out.append(f"## Dated cash-flow forecast ({config.FORECAST_DAYS} days)")
        out.append("")
        out.append(
            "_Debits include the purchase payments column. All values come from the "
            "deterministic simulator._"
        )
        out.append("")
        out.append("| Date | Opening | Credits | Debits | Purchase | Closing | Reserve | Margin |")
        out.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        for r in d["cashflow"]:
            out.append(
                f"| {r['date']} | {_money(Decimal(r['opening']))} | {_money(Decimal(r['credits']))} "
                f"| {_money(Decimal(r['debits']))} | {_money(Decimal(r['purchase_payments']))} "
                f"| {_money(Decimal(r['closing']))} | {_money(Decimal(r['reserve']))} "
                f"| {_money(Decimal(r['margin']))} |"
            )
        out.append("")

        out.append("## Upcoming confirmed obligations")
        out.append("")
        if d["obligations"]:
            out.append("| Date | Amount | Category | Description |")
            out.append("|---|---:|---|---|")
            for f in d["obligations"]:
                out.append(
                    f"| {f['date']} | {_money(Decimal(f['amount']))} | {f['category']} | {f['description']} |"
                )
        else:
            out.append("_No debits inside the forecast horizon._")
        out.append("")

        out.append("## Forecast income")
        out.append("")
        if d["forecast_income"]:
            out.append("| Date | Amount | Category | Description |")
            out.append("|---|---:|---|---|")
            for f in d["forecast_income"]:
                out.append(
                    f"| {f['date']} | {_money(Decimal(f['amount']))} | {f['category']} | {f['description']} |"
                )
        else:
            out.append("_No projected income inside the forecast horizon._")
        out.append("")

        out.append("## Payment options compared")
        out.append("")
        if d["payment_options_compared"]:
            out.append("| Method | Option | Total payable | # Pmts | First date | Safe | Selected | Notes |")
            out.append("|---|---|---:|---:|---|---|---|---|")
            for o in d["payment_options_compared"]:
                out.append(
                    f"| {o['method']} | {o['payment_option_id'] or '—'} | {_money(Decimal(o['total_payable']))} "
                    f"| {o['number_of_payments']} | {o['first_payment_date'] or '—'} "
                    f"| {'yes' if o['safe'] else 'no'} | {'★' if o['selected'] else ''} "
                    f"| {o['rejection_reason'] or ''} |"
                )
        else:
            out.append("_No candidate payment options were generated for this request._")
        out.append("")

        if self.scenario_report is not None:
            out.extend(_scenario_markdown(self.scenario_report, pos["home_currency"]))

        out.append("## Assumptions & missing / uncertain information")
        out.append("")
        for note in self._assumptions():
            out.append(f"- {note}")
        out.append("")
        out.append(
            "> This report is a forecast based on the supplied information and deterministic "
            "calculations. It is not a guarantee of future financial safety and is not "
            "personalized investment, credit, or regulated financial advice."
        )
        out.append("")
        return "\n".join(out)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _timedelta(days: int):
    from datetime import timedelta

    return timedelta(days=days)


def _iso_and_dmy(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
    except Exception:
        return iso
    return f"{_dmy(d)} ({iso})"


def _scenario_dict(report) -> Optional[dict]:
    if report is None:
        return None
    return {
        "baseline_status": report.baseline_status,
        "baseline_safe_amount": str(report.baseline_safe_amount),
        "at_risk_income_total": str(report.at_risk_income_total),
        "delay_days": report.config.delay_days,
        "shock_amount": str(report.config.shock_amount),
        "shock_date": report.config.shock_date.isoformat() if report.config.shock_date else "",
        "results": [
            {
                "key": r.key,
                "label": r.label,
                "status": r.status,
                "amount_safe_to_pay": str(r.amount_safe_to_pay),
                "method": r.recommended_method,
                "safe": r.safe,
                "min_closing_balance": str(r.min_closing_balance),
                "breach_date": r.breach_date.isoformat() if r.breach_date else "",
                "expected_income_included": str(r.expected_income_included),
                "status_changed": r.status_changed,
                "safe_amount_delta": str(r.safe_amount_delta),
            }
            for r in report.results
        ],
    }


def _scenario_markdown(report, currency: str) -> List[str]:
    out: List[str] = []
    out.append("## Uncertainty scenarios (separate simulator runs)")
    out.append("")
    out.append(
        f"- Baseline status: `{report.baseline_status}`; baseline safe amount: "
        f"{currency} {_money(report.baseline_safe_amount)}"
    )
    out.append(f"- At-risk expected income in play: {currency} {_money(report.at_risk_income_total)}")
    out.append(f"- Assumptions: delay {report.config.delay_days}d; shock "
               f"{currency} {_money(report.config.shock_amount)} on {report.config.shock_date}")
    out.append("")
    out.append("| Scenario | Status | Safe amount | Method | Reserve safe? | Breach | Δ safe amount |")
    out.append("|---|---|---:|---|---|---|---:|")
    for r in report.results:
        out.append(
            f"| {r.label} | `{r.status}` | {currency} {_money(r.amount_safe_to_pay)} "
            f"| {r.recommended_method} | {'yes' if r.safe else 'no'} "
            f"| {r.breach_date or '—'} | {currency} {_money(r.safe_amount_delta)} |"
        )
    out.append("")
    return out


def build_report(
    analysis: Analysis,
    invoices_summary: Optional[Dict[str, object]] = None,
    scenario_report: Optional["ScenarioReport"] = None,
    max_rows: Optional[int] = None,
) -> DecisionReport:
    """Assemble a report from an already-computed analysis (no recomputation)."""
    return DecisionReport(
        analysis=analysis,
        invoices_summary=invoices_summary,
        scenario_report=scenario_report,
        max_rows=max_rows,
    )
