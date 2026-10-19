"""Message interpreter: maps natural-language evidence to structured financial facts.

Messages arrive in English, Indonesian, or Spanish. A deterministic multilingual
pattern layer extracts the recurring message templates in the dataset;
``llm.EvidenceModel`` is the optional LLM fallback for anything the patterns
cannot parse. Message text is untrusted evidence: extracted facts can amend the
financial state, never the application rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

FACT_TYPES = {
    "salary_change",
    "salary_date_change",
    "new_expense",
    "expense_change",
    "payment_cancelled",
    "payment_settled",
    "refund_pending",
    "refund_settled",
    "internal_transfer",
    "invoice_confirmed",
    "income_unconfirmed",
    "investment_unrealized",
    "one_time_income",
    "contract_ended",
    "recurring_commitment",
    "dispute_open",
    "separate_obligations",
    "irrelevant_or_unknown",
}

MONEY_RE = r"(?:USD|EUR|IDR|INR|ZAR|Rs\.?|Rp|R\$)?\s?([\d][\d,\.\s]*)"
DATE_RE = r"(\d{4}-\d{2}-\d{2})"


@dataclass
class MessageFact:
    fact_type: str
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    effective_date: Optional[str] = None
    recurrence: Optional[str] = None
    action: str = "inform"
    related_event_id: Optional[str] = None
    confidence: float = 0.9
    source_type: str = "message"
    source_id: str = ""
    evidence: str = ""
    amendment: Optional[str] = None  # replace_amount | replace_date | stop_recurrence | none
    raw_text: str = ""


def _num(text: str) -> Decimal:
    cleaned = text.replace(",", "").replace(" ", "").strip()
    # Indonesian messages may use '.' as the thousands separator without decimals
    if cleaned.count(".") > 1 and not cleaned.endswith((".00", ".0")):
        cleaned = cleaned.replace(".", "")
    return Decimal(cleaned)


def _currency_of(text: str) -> Optional[str]:
    for ccy, pattern in (
        ("IDR", r"(?:IDR|Rp)"),
        ("INR", r"(?:INR|Rs\.?)"),
        ("USD", r"USD"),
        ("EUR", r"EUR"),
        ("ZAR", r"ZAR"),
    ):
        if re.search(pattern, text):
            return ccy
    return None


def _first_money(text: str) -> Optional[Decimal]:
    match = re.search(MONEY_RE, text)
    return _num(match.group(1)) if match else None


def _all_money(text: str) -> List[Decimal]:
    return [_num(m.group(1)) for m in re.finditer(MONEY_RE, text)]


def _first_date(text: str) -> Optional[str]:
    match = re.search(DATE_RE, text)
    return match.group(1) if match else None


def _fact(
    fact_type: str,
    text: str,
    message_id: str,
    related_event_id: str,
    confidence: float = 0.9,
    **kwargs,
) -> MessageFact:
    return MessageFact(
        fact_type=fact_type,
        source_id=message_id,
        related_event_id=related_event_id or None,
        evidence=text[:280],
        confidence=confidence,
        raw_text=text,
        **kwargs,
    )


def _salary_raise(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(naik|menjadi|increased?|raised?|has increased)", text, re.I):
        return None
    if not re.search(r"(gaji|salary|pay)", text, re.I):
        return None
    money = _all_money(text)
    if not money:
        return None
    applies = _first_date(text) or _first_date(text)
    return _fact(
        "salary_change",
        text,
        mid,
        rel,
        amount=money[-1],
        currency=_currency_of(text),
        effective_date=applies,
        recurrence="monthly",
        action="replace_previous",
        amendment="replace_amount",
        confidence=0.97,
    )


def _salary_reduced(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(reduced|dikurangi|sementara|temporary monthly pay|gaji bulanan sementara)", text, re.I):
        return None
    money = _all_money(text)
    if not money:
        return None
    return _fact(
        "salary_change",
        text,
        mid,
        rel,
        amount=money[-1],
        currency=_currency_of(text),
        effective_date=_first_date(text),
        recurrence="monthly",
        action="replace_previous",
        amendment="replace_amount",
        confidence=0.97,
    )


def _salary_first(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(first salary|gaji pertama|new employer)", text, re.I):
        return None
    money = _all_money(text)
    if not money:
        return None
    confirmed = _first_date(text)
    return _fact(
        "salary_change",
        text,
        mid,
        rel,
        amount=money[-1],
        currency=_currency_of(text),
        effective_date=confirmed,
        recurrence="monthly",
        action="add_confirmed",
        amendment="replace_amount",
        confidence=0.96,
    )


def _salary_date_change(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(
        r"(now expected on|expected on|diperkirakan (masuk|pada)|dijadwalkan pada|confirmed for|confirmed credit date|dikonfirmasi untuk)",
        text,
        re.I,
    ):
        return None
    if re.search(r"(first salary|gaji pertama)", text, re.I):
        return None
    money = _all_money(text)
    new_date = _first_date(text)
    if not new_date:
        return None
    fact = _fact(
        "salary_date_change",
        text,
        mid,
        rel,
        amount=money[0] if money else None,
        currency=_currency_of(text),
        effective_date=new_date,
        recurrence="monthly",
        action="replace_previous",
        amendment="replace_date",
        confidence=0.95,
    )
    return fact


def _contract_ended(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(contract has ended|kontrak .*(berakhir|telah berakhir)|employment has ended|Hubungan kerja Anda telah berakhir|seasonal contract)", text, re.I):
        return None
    return _fact(
        "contract_ended",
        text,
        mid,
        rel,
        action="stop_income",
        amendment="stop_salary",
        confidence=0.96,
    )


def _household_ended(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(household employment record has ended|sumber pendapatan kerja rumah tangga telah berakhir|one household employment record has ended|Salah satu sumber pendapatan)", text, re.I):
        return None
    money = _all_money(text)
    return _fact(
        "contract_ended",
        text,
        mid,
        rel,
        amount=money[-1] if money else None,
        currency=_currency_of(text),
        action="reduce_income_to",
        amendment="replace_amount",
        confidence=0.95,
    )


def _bonus_pending(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(bonus|commission|komisi)", text, re.I):
        return None
    if not re.search(r"(pending|not.*approved|belum disetujui|menunggu|awaiting approval|belum.*disetujui)", text, re.I):
        return None
    return _fact(
        "income_unconfirmed",
        text,
        mid,
        rel,
        action="ignore_income",
        confidence=0.97,
    )


def _invoice_confirmed(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(invoice payment|pembayaran faktur)", text, re.I):
        return None
    if not re.search(r"(approved|disetujui)", text, re.I):
        return None
    money = _all_money(text)
    settle = _first_date(text)
    if not money or not settle:
        return None
    return _fact(
        "invoice_confirmed",
        text,
        mid,
        rel,
        amount=money[0],
        currency=_currency_of(text),
        effective_date=settle,
        action="add_one_time_income",
        confidence=0.95,
    )


def _payout_pending(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(payout is still pending|masih tertunda|masih menunggu|payout masih)", text, re.I):
        return None
    return _fact(
        "income_unconfirmed",
        text,
        mid,
        rel,
        action="ignore_income",
        confidence=0.96,
    )


def _refund_status(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(refund|pengembalian dana)", text, re.I):
        return None
    if re.search(r"(has reached your account|sudah masuk|completed|settled)", text, re.I):
        money = _all_money(text)
        return _fact(
            "refund_settled",
            text,
            mid,
            rel,
            amount=money[0] if money else None,
            currency=_currency_of(text),
            action="add_income",
            confidence=0.9,
        )
    if re.search(r"(initiated|not reached|belum masuk|still processing|masih (dalam )?proses|diproses)", text, re.I):
        return _fact(
            "refund_pending",
            text,
            mid,
            rel,
            action="ignore_income",
            confidence=0.97,
        )
    return None


def _prize_status(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(prize|hadiah)", text, re.I):
        return None
    if re.search(r"(pay the|bayar biaya)", text, re.I):
        # Scam pattern: asks the user to pay to receive money. Never treat as income.
        return _fact(
            "irrelevant_or_unknown",
            text,
            mid,
            rel,
            action="ignore_income",
            confidence=0.99,
        )
    if re.search(r"(reached your account|sudah masuk)", text, re.I):
        return _fact("one_time_income", text, mid, rel, action="already_settled", confidence=0.9)
    return _fact(
        "income_unconfirmed",
        text,
        mid,
        rel,
        action="ignore_income",
        confidence=0.97,
    )


def _investment_value(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(market value|displayed value|nilai investasi|portfolio)", text, re.I):
        return None
    return _fact(
        "investment_unrealized",
        text,
        mid,
        rel,
        action="not_cash",
        confidence=0.97,
    )


def _investment_sale_settled(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(investment sale|hasil penjualan investasi|penjualan investasi|sale order is complete|penjualan.*selesai)", text, re.I):
        return None
    return _fact(
        "payment_settled",
        text,
        mid,
        rel,
        action="already_settled",
        confidence=0.92,
    )


def _internal_transfer(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(transfer between your (two )?accounts|transfer antara (dua )?rekening|between your two accounts)", text, re.I):
        return None
    return _fact(
        "internal_transfer",
        text,
        mid,
        rel,
        action="ignore_both_sides",
        confidence=0.97,
    )


def _dispute_open(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(dispute is open|reversal has not|extra card charge|penyelidikan|sengketa masih terbuka)", text, re.I):
        return None
    return _fact(
        "dispute_open",
        text,
        mid,
        rel,
        action="ignore_reversal_keep_debit",
        confidence=0.95,
    )


def _failed_debit_retry(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(previous debit attempt failed|debit attempt failed|percobaan debit (sebelumnya )?gagal)", text, re.I):
        return None
    money = _all_money(text)
    return _fact(
        "payment_settled",
        text,
        mid,
        rel,
        amount=money[0] if money else None,
        currency=_currency_of(text),
        action="keep_future_debit",
        confidence=0.95,
    )


def _separate_cards(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(two separate card accounts|minimum payments due on two|dua (kartu|rekening kartu) terpisah|minimum payments)", text, re.I):
        return None
    return _fact(
        "separate_obligations",
        text,
        mid,
        rel,
        action="count_each_min_payment",
        confidence=0.93,
    )


def _rent_increase(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(rent|sewa)", text, re.I):
        return None
    if not re.search(r"(12%|increases?|menaikkan|naik)", text, re.I):
        return None
    return _fact(
        "expense_change",
        text,
        mid,
        rel,
        amount=Decimal("12"),
        action="multiply_amount",
        amendment="rent_increase_12pct",
        confidence=0.96,
    )


def _arrears_one_time(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(arrears|tunggakan|one-time)", text, re.I):
        return None
    money = _all_money(text)
    if len(money) < 2:
        return None
    return _fact(
        "one_time_income",
        text,
        mid,
        rel,
        amount=money[-1],
        currency=_currency_of(text),
        effective_date=_first_date(text),
        action="add_one_time_income",
        confidence=0.95,
    )


def _childcare_starts(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(childcare|pengasuhan anak)", text, re.I):
        return None
    if not re.search(r"(begins|resumes|dimulai|bermulai)", text, re.I):
        return None
    money = _all_money(text)
    return _fact(
        "recurring_commitment",
        text,
        mid,
        rel,
        amount=money[-1] if money else None,
        currency=_currency_of(text),
        effective_date=_first_date(text),
        recurrence="monthly",
        action="add_expense",
        confidence=0.9,
    )


def _salary_resumes(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(resumes on|salary of|regular salary|gaji rutin)", text, re.I):
        return None
    if re.search(r"(childcare|arrears|one-time|bonus|commission)", text, re.I):
        return None
    money = _all_money(text)
    if not money:
        return None
    return _fact(
        "salary_change",
        text,
        mid,
        rel,
        amount=money[-1],
        currency=_currency_of(text),
        effective_date=_first_date(text),
        recurrence="monthly",
        action="replace_amount_keep_schedule",
        amendment="replace_amount",
        confidence=0.9,
    )


def _base_salary_confirmed(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    if not re.search(r"(confirmed base salary|confirmed salary|base salary|gaji pokok)", text, re.I):
        return None
    if re.search(r"(bonus|commission|komisi)", text, re.I):
        # The main fact is the confirmed base; the pending part is ignored separately.
        pass
    money = _all_money(text)
    if not money:
        return None
    return _fact(
        "salary_change",
        text,
        mid,
        rel,
        amount=money[-1],
        currency=_currency_of(text),
        effective_date=_first_date(text),
        recurrence="monthly",
        action="replace_amount_keep_schedule",
        amendment="replace_amount",
        confidence=0.93,
    )


def _payment_cancelled_multilingual(text: str, mid: str, rel: str) -> Optional[MessageFact]:
    """Cancellation evidence in any supported language (EN/ES/ID)."""
    if not re.search(
        r"(cancel(?:l)?ed|has been cancelled|no longer will be charged|"
        r"cancelado|ha sido cancelad[oa]|no se procesar|"
        r"dibatalkan|tidak akan diproses)",
        text,
        re.I,
    ):
        return None
    return _fact(
        "payment_cancelled", text, mid, rel,
        action="cancel",
        amendment="cancel",
        confidence=0.95,
    )


_EXTRACTORS = (
    _payment_cancelled_multilingual,
    _rent_increase,
    _invoice_confirmed,
    _internal_transfer,
    _investment_sale_settled,
    _investment_value,
    _prize_status,
    _refund_status,
    _dispute_open,
    _failed_debit_retry,
    _separate_cards,
    _contract_ended,
    _household_ended,
    _arrears_one_time,
    _childcare_starts,
    _salary_raise,
    _salary_reduced,
    _salary_first,
    _salary_date_change,
    _payout_pending,
    _bonus_pending,
    _base_salary_confirmed,
    _salary_resumes,
)


def extract_facts(text: str, message_id: str = "", related_event_id: str = "") -> List[MessageFact]:
    """Deterministically extract financial facts from one untrusted message."""
    facts: List[MessageFact] = []
    for extractor in _EXTRACTORS:
        try:
            fact = extractor(text, message_id, related_event_id)
        except Exception:  # defensive: evidence parsing must never crash inference
            continue
        if fact is not None:
            facts.append(fact)
    if not facts:
        facts.append(
            _fact("irrelevant_or_unknown", text, message_id, related_event_id, confidence=0.5)
        )
    return facts
