"""Structured-output contracts for evidence extraction (§3.3).

Every model reply — local or cloud — is validated against these contracts before
it reaches the deterministic engine. Pydantic is used when installed for strict
typing and coercion; otherwise an equivalent pure-Python check runs so the engine
never hard-depends on an optional package (the offline deterministic path must
stay installable with only the core requirements).

Two principles encoded here:

* **Unknown stays unknown.** Missing amounts/dates remain ``None``; a model that
  fabricates a value is rejected, not trusted.
* **Fail closed into a retry.** ``validate_*`` returns ``(ok, reason)``; the
  caller re-prompts the model once with the reason, then degrades gracefully.
"""

from __future__ import annotations

from typing import List, Tuple

try:  # pragma: no cover - exercised only when pydantic is installed
    from pydantic import BaseModel, Field, field_validator

    HAVE_PYDANTIC = True
except Exception:  # pragma: no cover
    HAVE_PYDANTIC = False


def _is_numeric(value) -> bool:
    """True for a number or a numeric string ("1,840.50"); False for "abc".

    Numeric *fields* (amount/value) must be numeric — a garbage string is a bad
    extraction and should fail validation. Qualitative fields (confidence) are
    deliberately NOT checked here, so "confidence": "High" is accepted.
    """
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value.replace(",", "").strip())
            return True
        except ValueError:
            return False
    return False

VALID_FACT_TYPES = {
    "salary_change", "salary_date_change", "new_expense", "expense_change",
    "payment_cancelled", "payment_settled", "refund_pending", "refund_settled",
    "internal_transfer", "invoice_confirmed", "income_unconfirmed",
    "investment_unrealized", "one_time_income", "contract_ended",
    "recurring_commitment", "dispute_open", "separate_obligations",
    "irrelevant_or_unknown",
}

if HAVE_PYDANTIC:

    class _MessageFactModel(BaseModel):
        model_config = {"extra": "ignore"}

        # Nullable by design: a model may legitimately mark any of these unknown
        # (e.g. "confidence": null). Unknown stays unknown; defaults are applied
        # when the fact is built, never fabricated by the model.
        fact_type: str | None = None
        amount: str | float | None = None  # models may quote numbers as strings
        currency: str | None = None
        date: str | None = None
        recurrence: str | None = None
        action: str | None = None
        related_event_id: str | None = None
        confidence: str | float | None = None  # e.g. 0.9, "0.9", or "High"
        evidence: str | None = None

        @field_validator("amount")
        @classmethod
        def _amount_numeric(cls, v):
            if v is not None and not _is_numeric(v):
                raise ValueError("amount must be numeric")
            return v

    class _MessageExtraction(BaseModel):
        model_config = {"extra": "ignore"}

        facts: List[_MessageFactModel] = Field(default_factory=list)

    class _ImageFactModel(BaseModel):
        model_config = {"extra": "ignore"}

        field: str | None = None
        value: str | float | None = None  # models may quote numbers as strings
        currency: str | None = None
        date: str | None = None
        status: str | None = None
        confidence: str | float | None = None  # e.g. 0.9, "0.9", or "High"

        @field_validator("value")
        @classmethod
        def _value_numeric(cls, v):
            if v is not None and not _is_numeric(v):
                raise ValueError("value must be numeric")
            return v

    class _ImageExtraction(BaseModel):
        model_config = {"extra": "ignore"}

        document_type: str | None = None
        facts: List[_ImageFactModel] = Field(default_factory=list)


def validate_message_payload(data) -> Tuple[bool, str]:
    """Return (ok, reason) for a message-extraction payload."""
    if not isinstance(data, dict):
        return False, "payload is not a JSON object"
    facts = data.get("facts")
    if not isinstance(facts, list):
        return False, "'facts' must be a list"

    if HAVE_PYDANTIC:
        try:
            _MessageExtraction.model_validate(data)
        except Exception as exc:  # pydantic ValidationError
            return False, f"schema: {exc}"
    else:
        # Structural + numeric-field checks; qualitative coercion happens at build
        # so a correct extraction is never rejected over "confidence": "High".
        for item in facts:
            if not isinstance(item, dict):
                return False, "each fact must be an object"
            amt = item.get("amount")
            if amt is not None and not _is_numeric(amt):
                return False, "amount must be numeric"
    return True, ""


def validate_image_payload(data) -> Tuple[bool, str]:
    """Return (ok, reason) for an image-extraction payload."""
    if not isinstance(data, dict):
        return False, "payload is not a JSON object"
    facts = data.get("facts")
    if not isinstance(facts, list):
        return False, "'facts' must be a list"

    if HAVE_PYDANTIC:
        try:
            _ImageExtraction.model_validate(data)
        except Exception as exc:
            return False, f"schema: {exc}"
    else:
        # Structural + numeric-field checks (see validate_message_payload).
        for item in facts:
            if not isinstance(item, dict):
                return False, "each fact must be an object"
            val = item.get("value")
            if val is not None and not _is_numeric(val):
                return False, "value must be numeric"
    return True, ""
