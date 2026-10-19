"""Deterministic FX conversion using only dataset/exchange_rates.csv."""

from __future__ import annotations

import csv
from bisect import bisect_left
from datetime import date
from decimal import Decimal, localcontext
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Tuple

DATASET_DIR = Path(__file__).resolve().parents[2] / "dataset"

# Ordered currency-chain preference used when no direct dated rate exists.
_PREFERRED_CHAINS: Dict[str, Tuple[Tuple[str, ...], ...]] = {
    "INR": (("USD", "INR"),),
    "IDR": (("USD", "IDR"),),
    "EUR": (("USD", "EUR"), ("EUR", "USD")),
    "ZAR": (("EUR", "ZAR"),),
    "USD": (("EUR", "USD"), ("USD", "EUR")),
}


@lru_cache(maxsize=1)
def _rate_table() -> Tuple[Tuple[str, str, str, str], ...]:
    path = DATASET_DIR / "exchange_rates.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    table = tuple(
        (row["rate_date"].strip(), row["from_currency"].strip(), row["to_currency"].strip(), row["rate"].strip())
        for row in rows
    )
    return table


@lru_cache(maxsize=None)
def _rates_by_pair() -> Dict[Tuple[str, str], Tuple[Tuple[date, Decimal], ...]]:
    grouped: Dict[Tuple[str, str], list] = {}
    for rate_date, from_ccy, to_ccy, rate in _rate_table():
        grouped.setdefault((from_ccy, to_ccy), []).append(
            (date.fromisoformat(rate_date), Decimal(rate))
        )
    return {
        pair: tuple(sorted(values, key=lambda item: item[0])) for pair, values in grouped.items()
    }


@lru_cache(maxsize=None)
def _rate_on(pair: Tuple[str, str], on_date: date) -> Optional[Decimal]:
    """Latest rate for the pair dated on or before ``on_date`` (None if none exists)."""
    series = _rates_by_pair().get(pair)
    if not series:
        return None
    dates = [d for d, _ in series]
    idx = bisect_left(dates, on_date)
    if idx < len(dates) and dates[idx] == on_date:
        return series[idx][1]
    idx -= 1
    if idx < 0:
        return None
    return series[idx][1]


def _direct_rate(from_ccy: str, to_ccy: str, on_date: date) -> Optional[Decimal]:
    return _rate_on((from_ccy, to_ccy), on_date)


def _inverse_rate(from_ccy: str, to_ccy: str, on_date: date) -> Optional[Decimal]:
    rate = _rate_on((to_ccy, from_ccy), on_date)
    if rate is None or rate == 0:
        return None
    return Decimal(1) / rate


def _chain_rate(from_ccy: str, to_ccy: str, on_date: date) -> Optional[Decimal]:
    for chain in _PREFERRED_CHAINS.get(from_ccy, ()):
        if chain and chain[0] == from_ccy and chain[-1] == to_ccy:
            with localcontext() as ctx:
                ctx.prec = 50
                factor = Decimal(1)
                for a, b in zip(chain, chain[1:]):
                    rate = _direct_rate(a, b, on_date)
                    if rate is None:
                        rate = _inverse_rate(a, b, on_date)
                    if rate is None:
                        factor = None
                        break
                    factor = factor * rate
                if factor is not None:
                    return +factor
    return None


def convert(amount: Decimal, from_ccy: str, to_ccy: str, on_date: date) -> Decimal:
    """Convert ``amount`` from one currency to another on a dated rate.

    Direct dated rates win; then inverses; then the deterministic chain
    (e.g. USD->IDR for IDR/INR homes, EUR->ZAR for ZAR homes). Raises when
    the supplied rate table cannot express the conversion.
    """
    if from_ccy == to_ccy:
        return amount
    with localcontext() as ctx:
        ctx.prec = 50
        rate = _direct_rate(from_ccy, to_ccy, on_date)
        if rate is None:
            rate = _inverse_rate(from_ccy, to_ccy, on_date)
        if rate is None:
            rate = _chain_rate(from_ccy, to_ccy, on_date)
        if rate is None:
            raise ValueError(f"No FX path from {from_ccy} to {to_ccy} on {on_date}")
        return +(amount * rate)


def quantize(amount: Decimal, currency: str) -> Decimal:
    """Round to the conventional minor-unit precision of a currency."""
    exponent = Decimal("0.01") if currency in {"USD", "EUR"} else Decimal("1")
    return amount.quantize(exponent)
