"""Dataset contracts for the Buy or Wait? financial affordability agent."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

DATASET_DIR = Path(__file__).resolve().parents[2] / "dataset"


def parse_date(text: str) -> Optional[date]:
    text = (text or "").strip()
    if not text:
        return None
    return date.fromisoformat(text)


def parse_amount(text: str) -> Optional[Decimal]:
    text = (text or "").strip().replace(",", "")
    if not text:
        return None
    return Decimal(text)


def parse_bool(text: str) -> bool:
    return (text or "").strip().lower() == "true"


def parse_list(text: str) -> List[str]:
    return [item.strip() for item in (text or "").split("|") if item.strip()]


@dataclass
class Request:
    request_id: str
    user_id: str
    request_date: date
    request_type: str
    requested_amount: Decimal
    desired_completion_date: date
    allows_partial_payment: bool
    request_text: str


@dataclass
class FinancialProfile:
    user_id: str
    home_currency: str
    current_available_balance: Decimal
    minimum_balance_to_keep: Decimal
    financial_priorities: List[str] = field(default_factory=list)
    expense_categories_to_protect: List[str] = field(default_factory=list)
    expense_categories_user_is_willing_to_reduce: List[str] = field(default_factory=list)
    expense_categories_user_is_willing_to_stop: List[str] = field(default_factory=list)
    payment_methods_user_will_consider: List[str] = field(default_factory=list)
    max_installment_months: Optional[int] = None


@dataclass
class FinancialEvent:
    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: str
    amount: Optional[Decimal]
    currency: str
    event_date: date
    settlement_date: Optional[date]
    status: str
    linked_event_id: str = ""
    flexibility: str = "fixed"
    minimum_allowed_amount: Optional[Decimal] = None


@dataclass
class PaymentOption:
    payment_option_id: str
    request_id: str
    payment_method: str
    payment_amount: Decimal
    number_of_payments: int
    first_payment_date: date
    payment_frequency_days: Optional[int]
    financing_fee: Decimal
    total_payable_amount: Decimal


@dataclass
class Message:
    message_id: str
    user_id: str
    request_id: str
    related_event_id: str
    sent_at: datetime
    source_type: str
    message_text: str


@dataclass
class ImageLink:
    image_id: str
    user_id: str
    request_id: str
    related_event_id: str


@dataclass
class SampleRow:
    request: Request
    gold: Dict[str, str]


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_requests(path: Optional[Path] = None) -> List[Request]:
    path = path or DATASET_DIR / "requests.csv"
    requests = []
    for row in _read_csv(path):
        requests.append(
            Request(
                request_id=row["request_id"],
                user_id=row["user_id"],
                request_date=parse_date(row["request_date"]),
                request_type=row["request_type"],
                requested_amount=parse_amount(row["requested_amount"]),
                desired_completion_date=parse_date(row["desired_completion_date"]),
                allows_partial_payment=parse_bool(row["allows_partial_payment"]),
                request_text=row.get("request_text", ""),
            )
        )
    return requests


def load_profiles(path: Optional[Path] = None) -> Dict[str, FinancialProfile]:
    path = path or DATASET_DIR / "financial_profiles.csv"
    profiles = {}
    for row in _read_csv(path):
        profiles[row["user_id"]] = FinancialProfile(
            user_id=row["user_id"],
            home_currency=row["home_currency"],
            current_available_balance=parse_amount(row["current_available_balance"]),
            minimum_balance_to_keep=parse_amount(row["minimum_balance_to_keep"]),
            financial_priorities=parse_list(row.get("financial_priorities", "")),
            expense_categories_to_protect=parse_list(row.get("expense_categories_to_protect", "")),
            expense_categories_user_is_willing_to_reduce=parse_list(
                row.get("expense_categories_user_is_willing_to_reduce", "")
            ),
            expense_categories_user_is_willing_to_stop=parse_list(
                row.get("expense_categories_user_is_willing_to_stop", "")
            ),
            payment_methods_user_will_consider=parse_list(
                row.get("payment_methods_user_will_consider", "")
            ),
            max_installment_months=int(row["max_installment_months"])
            if (row.get("max_installment_months") or "").strip()
            else None,
        )
    return profiles


def load_events(path: Optional[Path] = None) -> List[FinancialEvent]:
    path = path or DATASET_DIR / "financial_events.csv"
    events = []
    for row in _read_csv(path):
        events.append(
            FinancialEvent(
                event_id=row["event_id"],
                user_id=row["user_id"],
                event_type=row["event_type"],
                description=row.get("description", ""),
                category=row["category"],
                direction=row["direction"],
                amount=parse_amount(row["amount"]),
                currency=row["currency"],
                event_date=parse_date(row["event_date"]),
                settlement_date=parse_date(row["settlement_date"]),
                status=row["status"],
                linked_event_id=row.get("linked_event_id", "") or "",
                flexibility=row.get("flexibility", "") or "fixed",
                minimum_allowed_amount=parse_amount(row.get("minimum_allowed_amount", "")),
            )
        )
    return events


def load_payment_options(path: Optional[Path] = None) -> List[PaymentOption]:
    path = path or DATASET_DIR / "request_payment_options.csv"
    options = []
    for row in _read_csv(path):
        options.append(
            PaymentOption(
                payment_option_id=row["payment_option_id"],
                request_id=row["request_id"],
                payment_method=row["payment_method"],
                payment_amount=parse_amount(row["payment_amount"]),
                number_of_payments=int(row["number_of_payments"]),
                first_payment_date=parse_date(row["first_payment_date"]),
                payment_frequency_days=int(row["payment_frequency_days"])
                if (row.get("payment_frequency_days") or "").strip()
                else None,
                financing_fee=parse_amount(row["financing_fee"]),
                total_payable_amount=parse_amount(row["total_payable_amount"]),
            )
        )
    return options


def load_messages(path: Optional[Path] = None) -> List[Message]:
    path = path or DATASET_DIR / "messages.csv"
    messages = []
    for row in _read_csv(path):
        messages.append(
            Message(
                message_id=row["message_id"],
                user_id=row["user_id"],
                request_id=row.get("request_id", "") or "",
                related_event_id=row.get("related_event_id", "") or "",
                sent_at=datetime.fromisoformat(row["sent_at"].replace("Z", "+00:00")),
                source_type=row.get("source_type", ""),
                message_text=row.get("message_text", ""),
            )
        )
    return messages


def load_image_links(path: Optional[Path] = None) -> List[ImageLink]:
    path = path or DATASET_DIR / "images.csv"
    links = []
    for row in _read_csv(path):
        links.append(
            ImageLink(
                image_id=row["image_id"],
                user_id=row["user_id"],
                request_id=row.get("request_id", "") or "",
                related_event_id=row.get("related_event_id", "") or "",
            )
        )
    return links


def load_samples(path: Optional[Path] = None) -> List[SampleRow]:
    path = path or DATASET_DIR / "sample_requests.csv"
    samples = []
    for row in _read_csv(path):
        gold_fields = [
            "amount_safe_to_pay",
            "affordability_status",
            "recommended_payment_method",
            "payment_plan",
            "earliest_date_for_full_payment",
            "spending_changes_needed",
            "decision_explanation",
        ]
        request = Request(
            request_id=row["request_id"],
            user_id=row["user_id"],
            request_date=parse_date(row["request_date"]),
            request_type=row["request_type"],
            requested_amount=parse_amount(row["requested_amount"]),
            desired_completion_date=parse_date(row["desired_completion_date"]),
            allows_partial_payment=parse_bool(row["allows_partial_payment"]),
            request_text=row.get("request_text", ""),
        )
        samples.append(SampleRow(request=request, gold={f: row.get(f, "") for f in gold_fields}))
    return samples


class DataStore:
    """Loads and indexes every dataset once; request-scoped views are derived from it."""

    def __init__(self, dataset_dir: Optional[Path] = None) -> None:
        if dataset_dir is not None:
            global DATASET_DIR
            previous = DATASET_DIR
            DATASET_DIR = dataset_dir
            try:
                self.requests = load_requests()
                self.profiles = load_profiles()
                self.events = load_events()
                self.payment_options = load_payment_options()
                self.messages = load_messages()
                self.image_links = load_image_links()
            finally:
                DATASET_DIR = previous
        else:
            self.requests = load_requests()
            self.profiles = load_profiles()
            self.events = load_events()
            self.payment_options = load_payment_options()
            self.messages = load_messages()
            self.image_links = load_image_links()

        self.events_by_user: Dict[str, List[FinancialEvent]] = {}
        for event in self.events:
            self.events_by_user.setdefault(event.user_id, []).append(event)
        for events in self.events_by_user.values():
            events.sort(key=lambda e: (e.event_date, e.event_id))

        self.options_by_request: Dict[str, List[PaymentOption]] = {}
        for option in self.payment_options:
            self.options_by_request.setdefault(option.request_id, []).append(option)
        for options in self.options_by_request.values():
            options.sort(key=lambda o: o.payment_option_id)

        self.messages_by_user: Dict[str, List[Message]] = {}
        for message in self.messages:
            self.messages_by_user.setdefault(message.user_id, []).append(message)
        for messages in self.messages_by_user.values():
            messages.sort(key=lambda m: m.sent_at)

        self.images_by_event: Dict[str, List[ImageLink]] = {}
        self.images_by_request: Dict[str, List[ImageLink]] = {}
        for link in self.image_links:
            if link.related_event_id:
                self.images_by_event.setdefault(link.related_event_id, []).append(link)
            if link.request_id:
                self.images_by_request.setdefault(link.request_id, []).append(link)

    def events_for_user(self, user_id: str) -> List[FinancialEvent]:
        return self.events_by_user.get(user_id, [])

    def profile_for(self, user_id: str) -> FinancialProfile:
        return self.profiles[user_id]

    def options_for(self, request_id: str) -> List[PaymentOption]:
        return self.options_by_request.get(request_id, [])

    def messages_for_user(self, user_id: str) -> List[Message]:
        return self.messages_by_user.get(user_id, [])

    def image_path_for(self, image_id: str) -> Path:
        return DATASET_DIR / "media" / "images" / f"{image_id}.png"
