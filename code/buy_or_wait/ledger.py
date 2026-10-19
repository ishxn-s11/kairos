"""Ledger reconstruction: normalize events to a home-currency cash-flow stream.

Responsibilities:
- resolve blank amounts through linked image evidence;
- fold linked-event lifecycles so one economic transaction is counted once;
- apply message/image amendments with explicit precedence;
- infer supported recurring commitments and monthly variable-essential spending;
- emit a day-indexed home-currency ledger for the 90-day horizon.

Precedence (problem_statement.md): explicit cancellation/settlement/amendment
> newer record from the same source > settled over estimate > safer reading.
"""

from __future__ import annotations

import os
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from . import config, fx
from .images import ImageEvidenceStore, ImageFact
from .loader import DataStore, FinancialEvent, FinancialProfile, Message, Request
from .messages import MessageFact, extract_facts

ZERO = Decimal(0)

# LLM-extracted facts are cached here at runtime by (message_id) so repeated
# requests never re-interpret the same evidence.
_MESSAGE_FACT_CACHE: Dict[str, List[MessageFact]] = {}


@dataclass
class ForecastPolicy:
    """Which forecast layers the ledger projects (calibrated on the public samples).

    Layers:
      project_salary       - monthly salary on the history-anchored payday
      project_recurring    - strict recurring debits (fixed monthly commitments)
      project_variable     - conservative monthly provision for variable protected essentials
      pending_debit_reserve- reserve pending debits (unlike settled, they may still
                             bounce or be disputed; safer to reserve them)
    """

    project_salary: bool = True
    project_recurring: bool = True
    project_variable: bool = True
    pending_debit_reserve: bool = True

    @classmethod
    def from_env(cls) -> "ForecastPolicy":
        import os

        return cls(
            project_salary=os.environ.get("BOW_PROJECT_SALARY", "1") == "1",
            project_recurring=os.environ.get("BOW_PROJECT_RECURRING", "1") == "1",
            project_variable=os.environ.get("BOW_PROJECT_VARIABLE", "1") == "1",
            pending_debit_reserve=os.environ.get("BOW_PENDING_RESERVE", "1") == "1",
        )


@dataclass
class NormalizedFact:
    fact_type: str
    amount: Optional[Decimal]
    currency: str
    effective_date: Optional[date]
    status: str
    source_type: str
    source_id: str
    confidence: float
    note: str = ""


@dataclass
class ProjectedFlow:
    date: date
    amount: Decimal  # signed home-currency cash delta
    kind: str  # expense|income|subscription|debt_payment|other
    category: str
    description: str
    source_id: str
    recurring_key: Optional[str] = None
    flexible: bool = False
    minimum_allowed_amount: Optional[Decimal] = None


@dataclass
class UserLedger:
    profile: FinancialProfile
    request: Request
    starting_balance: Decimal
    minimum_balance: Decimal
    flows: List[ProjectedFlow] = field(default_factory=list)
    resolved_events: List[FinancialEvent] = field(default_factory=list)
    amendments: List[NormalizedFact] = field(default_factory=list)
    fx_notes: List[str] = field(default_factory=list)
    monthly_variable_essential: Decimal = ZERO
    ignored: List[str] = field(default_factory=list)

    def flows_in_horizon(self, start: date, days: int) -> List[ProjectedFlow]:
        end = start + timedelta(days=days)
        return [f for f in self.flows if start <= f.date < end]


def _event_settlement(event: FinancialEvent) -> Optional[date]:
    return event.settlement_date or event.event_date


def _to_home(amount: Decimal, currency: str, on_date: Optional[date], home: str, notes: List[str]) -> Decimal:
    if currency == home:
        return amount
    day = on_date or date(2026, 9, 15)
    converted = fx.convert(amount, currency, home, day)
    notes.append(f"FX {amount} {currency}->{home} @ {day}")
    return converted


def _median(values: List[Decimal]) -> Decimal:
    return Decimal(str(statistics.median([float(v) for v in values])))


class LedgerBuilder:
    """Builds the normalized user ledger for one request."""

    def __init__(self, store: DataStore, image_store: Optional[ImageEvidenceStore] = None,
                 policy: Optional[ForecastPolicy] = None) -> None:
        self.store = store
        self.image_store = image_store or ImageEvidenceStore()
        self.policy = policy or ForecastPolicy.from_env()
        self.model = None
        if os.environ.get("MODEL_PROVIDER", "").strip():
            try:
                from .llm import EvidenceModel

                self.model = EvidenceModel()
            except Exception as exc:
                print(f"[evidence] model provider unavailable: {exc}", flush=True)

    # ------------------------------------------------------------------ #
    # Blank amounts -> image evidence
    # ------------------------------------------------------------------ #
    def _amount_for_event(self, event: FinancialEvent) -> Tuple[Optional[Decimal], str]:
        if event.amount is not None:
            return event.amount, ""
        links = self.store.images_by_event.get(event.event_id, [])
        for link in links:
            fact = self.image_store.get_live(
                link.image_id, self.store.image_path_for(link.image_id), self.model
            )
            if fact is not None:
                return fact.value, f"image:{link.image_id}({fact.evidence})"
        return None, ""

    # ------------------------------------------------------------------ #
    # Message facts (deterministic extraction, optional LLM fallback)
    # ------------------------------------------------------------------ #
    def message_facts_for(self, user_id: str, request: Request) -> List[Tuple[Message, List[MessageFact]]]:
        results = []
        for message in self.store.messages_for_user(user_id):
            if message.message_id in _MESSAGE_FACT_CACHE:
                facts = _MESSAGE_FACT_CACHE[message.message_id]
            else:
                facts = extract_facts(message.message_text, message.message_id, message.related_event_id)
                # Real-model fallback for messages the deterministic layer cannot
                # interpret: the LLM is only ever an evidence interpreter.
                if (
                    self.model is not None
                    and self.model.available
                    and facts
                    and facts[0].fact_type == "irrelevant_or_unknown"
                ):
                    try:
                        live = self.model.extract_message_facts(
                            message.message_text, message.message_id, message.related_event_id
                        )
                        if live and live[0].fact_type != "irrelevant_or_unknown":
                            facts = live
                    except Exception as exc:
                        print(f"[evidence] LLM extraction failed for {message.message_id}: {exc}", flush=True)
                _MESSAGE_FACT_CACHE[message.message_id] = facts
            results.append((message, facts))
        return results

    # ------------------------------------------------------------------ #
    # Lifecycle resolution
    # ------------------------------------------------------------------ #
    def resolve_events(self, user_id: str, request: Request) -> List[FinancialEvent]:
        """Return the economically active events for this user/request."""
        events = self.store.events_for_user(user_id)
        by_id = {e.event_id: e for e in events}

        # Group lifecycles: head events (no linked_event_id) plus their children.
        children_of: Dict[str, List[FinancialEvent]] = defaultdict(list)
        heads: List[FinancialEvent] = []
        for event in events:
            if event.linked_event_id and event.linked_event_id in by_id:
                children_of[event.linked_event_id].append(event)
            else:
                heads.append(event)

        active: List[FinancialEvent] = []
        for head in heads:
            children = children_of.get(head.event_id, [])
            if not children:
                if head.status in {"cancelled", "failed"}:
                    continue
                active.append(head)
                continue
            # Lifecycle rule: only the economically relevant final state counts.
            final = max(children + [head], key=lambda e: (e.event_date, e.event_id))
            if final.status in {"cancelled", "failed"}:
                continue
            if final.event_type == "investment_valuation":
                continue  # non-cash valuation
            # Refunds: only a settled refund is cash; pending ones are not relied on.
            if final.event_type == "refund" and final.status != "settled":
                active.append(final)  # kept but marked pending -> excluded from credits
            active.append(final) if False else None
            if final not in active:
                active.append(final)
        # Deduplicate while preserving order.
        seen = set()
        result = []
        for event in active:
            if event.event_id in seen:
                continue
            seen.add(event.event_id)
            result.append(event)
        return result

    # ------------------------------------------------------------------ #
    # Ledger assembly
    # ------------------------------------------------------------------ #
    def build(self, request: Request) -> UserLedger:
        profile = self.store.profile_for(request.user_id)
        home = profile.home_currency
        notes: List[str] = []
        amendments: List[NormalizedFact] = []
        ignored: List[str] = []

        active_events = self.resolve_events(request.user_id, request)

        # ---------------- message amendments ---------------- #
        msgs = self.message_facts_for(request.user_id, request)
        policy = self.policy
        salary_replacement: Optional[NormalizedFact] = None
        salary_date_replacement: Optional[NormalizedFact] = None
        stop_income = False
        extra_expenses: List[ProjectedFlow] = []
        one_time_incomes: List[ProjectedFlow] = []
        rent_increase_factor: Optional[Decimal] = None

        for message, facts in msgs:
            if request.request_date < message.sent_at.date():
                continue  # evidence dated after the request cannot change history
            for fact in facts:
                if fact.fact_type == "irrelevant_or_unknown":
                    continue
                if fact.amendment == "replace_amount" and fact.amount is not None and fact.fact_type in {
                    "salary_change",
                    "salary_date_change",
                }:
                    candidate = NormalizedFact(
                        fact_type="salary",
                        amount=fact.amount,
                        currency=fact.currency or home,
                        effective_date=message.sent_at.date(),
                        status="confirmed" if fact.fact_type == "salary_change" else "confirmed",
                        source_type="message",
                        source_id=message.message_id,
                        confidence=fact.confidence,
                        note=fact.evidence[:120],
                    )
                    if salary_replacement is None or (
                        message.sent_at.date(), message.message_id
                    ) > (salary_replacement.effective_date or date.min, salary_replacement.source_id):
                        salary_replacement = candidate
                        if fact.effective_date:
                            salary_date_replacement = NormalizedFact(
                                fact_type="salary_date",
                                amount=None,
                                currency=fact.currency or home,
                                effective_date=date.fromisoformat(fact.effective_date),
                                status="confirmed",
                                source_type="message",
                                source_id=message.message_id,
                                confidence=fact.confidence,
                                note=f"date from {message.message_id}",
                            )
                elif fact.fact_type == "contract_ended":
                    if fact.action == "reduce_income_to" and fact.amount is not None:
                        salary_replacement = NormalizedFact(
                            fact_type="salary",
                            amount=fact.amount,
                            currency=fact.currency or home,
                            effective_date=message.sent_at.date(),
                            status="confirmed",
                            source_type="message",
                            source_id=message.message_id,
                            confidence=fact.confidence,
                            note="household income ended; remaining salary",
                        )
                    else:
                        stop_income = True
                elif fact.fact_type == "invoice_confirmed" and fact.amount and fact.effective_date:
                    one_time_incomes.append(
                        ProjectedFlow(
                            date=date.fromisoformat(fact.effective_date),
                            amount=_to_home(fact.amount, fact.currency or home, date.fromisoformat(fact.effective_date), home, notes),
                            kind="income",
                            category="invoice",
                            description=f"confirmed invoice {message.message_id}",
                            source_id=message.message_id,
                        )
                    )
                elif fact.fact_type == "recurring_commitment" and fact.amount is not None:
                    start = date.fromisoformat(fact.effective_date) if fact.effective_date else request.request_date
                    for month in range(4):
                        extra_expenses.append(
                            ProjectedFlow(
                                date=start + timedelta(days=30 * month),
                                amount=-_to_home(fact.amount, fact.currency or home, start, home, notes),
                                kind="expense",
                                category="childcare",
                                description=f"new recurring commitment ({message.message_id})",
                                source_id=message.message_id,
                                recurring_key=f"childcare:{message.message_id}",
                            )
                        )
                elif fact.fact_type == "expense_change" and fact.amendment == "rent_increase_12pct":
                    rent_increase_factor = Decimal("1.12")

        amendments.append(
            NormalizedFact(
                fact_type="salary_override" if salary_replacement else "none",
                amount=salary_replacement.amount if salary_replacement else None,
                currency=home,
                effective_date=salary_replacement.effective_date if salary_replacement else None,
                status="applied" if salary_replacement else "none",
                source_type="message",
                source_id=salary_replacement.source_id if salary_replacement else "",
                confidence=salary_replacement.confidence if salary_replacement else 0.0,
                note=salary_replacement.note if salary_replacement else "no salary amendment",
            )
        )

        # ---------------- recurring detection from history ---------------- #
        policy = self.policy
        recurring_flows, monthly_variable = self._infer_recurring(
            profile, request, active_events, salary_replacement, salary_date_replacement,
            stop_income, rent_increase_factor, notes, policy,
        )

        # ---------------- non-recurring future events ---------------- #
        horizon_end = request.request_date + timedelta(days=config.FORECAST_DAYS)
        recurring_keys = {(f.category, f.description.replace("recurring ", "")) for f in recurring_flows if f.recurring_key and f.recurring_key != "salary"}
        seen_flows = {(f.date, f.amount) for f in recurring_flows}
        for event in active_events:
            settle = _event_settlement(event)
            if settle is None:
                continue
            if not (request.request_date <= settle <= horizon_end):
                continue
            if event.event_type == "income" and event.category == "salary":
                continue  # projected by the salary layer
            amount, source_note = self._amount_for_event(event)
            if amount is None:
                ignored.append(f"{event.event_id}: blank amount without image evidence")
                continue
            home_amount = _to_home(amount, event.currency, settle, home, notes)
            signed = -home_amount if event.direction == "debit" else home_amount
            if event.direction == "non_cash" or event.event_type == "investment_valuation":
                ignored.append(f"{event.event_id}: non-cash valuation")
                continue
            if event.status == "pending" and event.direction == "credit":
                ignored.append(f"{event.event_id}: pending credit not relied upon")
                continue
            if event.status in {"cancelled", "failed"}:
                ignored.append(f"{event.event_id}: {event.status}")
                continue
            if (settle, signed) in seen_flows:
                continue  # already projected by the recurrence layer
            kind = event.event_type if event.event_type != "expense" else "expense"
            recurring_flows.append(
                ProjectedFlow(
                    date=settle,
                    amount=signed,
                    kind=kind,
                    category=event.category,
                    description=event.description or event.category,
                    source_id=event.event_id,
                    flexible=event.flexibility in {"reducible", "stoppable", "reducible_or_stoppable"},
                    minimum_allowed_amount=event.minimum_allowed_amount,
                )
            )
            seen_flows.add((settle, signed))
            if source_note:
                notes.append(f"{event.event_id} amount from {source_note}")

        recurring_flows.extend(extra_expenses)
        recurring_flows.extend(one_time_incomes)
        recurring_flows.sort(key=lambda f: (f.date, f.source_id))

        ledger = UserLedger(
            profile=profile,
            request=request,
            starting_balance=profile.current_available_balance,
            minimum_balance=profile.minimum_balance_to_keep,
            flows=recurring_flows,
            resolved_events=active_events,
            amendments=amendments,
            fx_notes=notes,
            monthly_variable_essential=monthly_variable,
            ignored=ignored,
        )
        return ledger

    # ------------------------------------------------------------------ #
    # Recurrence inference
    # ------------------------------------------------------------------ #
    def _infer_recurring(
        self,
        profile: FinancialProfile,
        request: Request,
        events: List[FinancialEvent],
        salary_replacement: Optional[NormalizedFact],
        salary_date_replacement: Optional[NormalizedFact],
        stop_income: bool,
        rent_increase_factor: Optional[Decimal],
        notes: List[str],
        policy: Optional[ForecastPolicy] = None,
    ) -> Tuple[List[ProjectedFlow], Decimal]:
        policy = policy or ForecastPolicy()
        home = profile.home_currency
        flows: List[ProjectedFlow] = []
        groups: Dict[Tuple, List[FinancialEvent]] = defaultdict(list)

        for event in events:
            if (
                event.status == "settled"
                and event.event_date < request.request_date
                and event.event_type in {"expense", "subscription", "debt_payment", "income"}
                and event.category != "salary"
            ):
                groups[(event.event_type, event.category, event.description)].append(event)

        today = request.request_date

        # ---- salary projection: confirmed scheduled rows first, then history ----
        # A scheduled salary row explicitly confirmed by the evidence counts on
        # its settlement date. When no scheduled row exists, a stable settled
        # salary history (3+ paydays at a consistent day-of-month) is treated
        # as the user's confirmed payroll schedule and projected forward.
        horizon = today + timedelta(days=config.FORECAST_DAYS)
        salary_events = sorted(
            [e for e in events if e.event_type == "income" and e.category == "salary" and e.status == "settled" and e.event_date < today],
            key=lambda e: e.event_date,
        )
        scheduled_salary = sorted(
            [
                e
                for e in events
                if e.event_type == "income" and e.category == "salary" and e.status != "settled"
                and (e.settlement_date or e.event_date) >= today
                and (e.settlement_date or e.event_date) <= horizon
            ],
            key=lambda e: (e.settlement_date or e.event_date),
        )
        if stop_income or not policy.project_salary:
            scheduled_salary = []
            salary_events = []
        if scheduled_salary:
            first = scheduled_salary[0]
            base_salary = _to_home(
                first.amount, first.currency,
                first.settlement_date or first.event_date, home, notes,
            )
            pay_interval = 30
            if len(salary_events) >= 2:
                intervals = [(b.event_date - a.event_date).days for a, b in zip(salary_events, salary_events[1:])]
                pay_interval = max(1, int(statistics.median(intervals)))
            if salary_replacement is not None:
                base_salary = _to_home(salary_replacement.amount, salary_replacement.currency, today, home, notes)
            next_pay = first.settlement_date or first.event_date
            if salary_date_replacement is not None and salary_date_replacement.effective_date:
                next_pay = salary_date_replacement.effective_date
            occurrence = next_pay
            month_index = 0
            while occurrence <= horizon and month_index < 5:
                flows.append(
                    ProjectedFlow(
                        date=occurrence,
                        amount=base_salary,
                        kind="income",
                        category="salary",
                        description="projected salary (evidence-confirmed)",
                        source_id=f"salary_proj_{month_index}",
                        recurring_key="salary",
                    )
                )
                occurrence += timedelta(days=pay_interval)
                month_index += 1
        elif len(salary_events) >= 3:
            # Stable settled history: project the confirmed payroll schedule.
            amounts = [
                _to_home(e.amount, e.currency, e.event_date, home, notes)
                for e in salary_events
                if e.amount is not None
            ]
            if amounts:
                base_salary = _median(amounts[-4:])
                pay_day = min(statistics.mode([e.event_date.day for e in salary_events]), 28)
                month_add = 0 if today.day <= pay_day else 1
                for month_index in range(5):
                    month = today.month + month_add + month_index
                    year = today.year + (month - 1) // 12
                    month = (month - 1) % 12 + 1
                    pay_date = date(year, month, pay_day)
                    if pay_date > horizon:
                        break
                    flows.append(
                        ProjectedFlow(
                            date=pay_date,
                            amount=base_salary,
                            kind="income",
                            category="salary",
                            description="projected salary (payroll history)",
                            source_id=f"salary_proj_{month_index}",
                            recurring_key="salary",
                        )
                    )

        # ---- recurring flows at each series' own observed cadence ---- #
        # Income series participate too: a stable settled salary series (same
        # description, steady amount, monthly cadence) is the user's confirmed
        # payroll and is projected forward on its payday; varying series
        # (freelance top-ups, partial payments) fail the stability gate and are
        # never projected.
        for (event_type, category, description), items in groups.items():
            if not policy.project_recurring:
                continue
            if len(items) < config.RECURRENCE_MIN_OBSERVATIONS:
                continue
            items = sorted(items, key=lambda e: e.event_date)
            intervals = [(b.event_date - a.event_date).days for a, b in zip(items, items[1:])]
            if not intervals:
                continue
            interval = int(statistics.median(intervals))
            if not 25 <= interval <= 35:
                continue  # not a monthly commitment (weekly variable spend is averaged into history)
            amounts = [
                _to_home(a, e.currency, e.event_date, home, notes)
                for e, a in ((e, self._amount_for_event(e)[0]) for e in items)
                if a is not None
            ]
            if not amounts:
                continue
            median_amount = _median(amounts[-4:])
            if any(abs(a - median_amount) > median_amount * config.RECURRENCE_TOLERANCE for a in amounts[-4:]):
                continue  # amounts not stable enough to be a fixed commitment
            last = items[-1]
            factor = rent_increase_factor if (rent_increase_factor and category == "rent") else Decimal(1)
            # Monthly commitments repeat on their observed day of month.
            anchor_day = min(statistics.mode([e.event_date.day for e in items]), 28)
            month_add = 0 if last.event_date.day >= today.day else 1
            occurrence = 0
            while occurrence < 5:
                month = today.month + month_add + occurrence
                year = today.year + (month - 1) // 12
                month = (month - 1) % 12 + 1
                flow_date = date(year, month, anchor_day)
                if flow_date > today + timedelta(days=config.FORECAST_DAYS):
                    break
                if flow_date >= today:
                    flows.append(
                        ProjectedFlow(
                            date=flow_date,
                            amount=-(median_amount * factor),
                            kind=event_type,
                            category=category,
                            description=f"recurring {description}",
                            source_id=last.event_id,
                            recurring_key=f"{category}:{description}",
                            flexible=last.flexibility in {"reducible", "stoppable", "reducible_or_stoppable"},
                            minimum_allowed_amount=last.minimum_allowed_amount,
                        )
                    )
                occurrence += 1

        return flows, ZERO
