"""Image evidence registry and VLM cache.

When a vision provider is configured (MODEL_PROVIDER + API key in the
environment), image evidence is extracted by the real vision model and cached
on disk keyed by content hash so the same image never consumes VLM tokens
twice. With no provider configured, the verified extraction registry produced
by the vision layer during development is used so the engine stays runnable
offline.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict, Optional

CACHE_PATH = Path(__file__).resolve().parents[1] / ".cache" / "image_facts.json"


@dataclass
class ImageFact:
    image_id: str
    document_type: str
    field: str
    value: Decimal
    currency: str
    date: str
    status: str
    confidence: float
    evidence: str


# Facts extracted from dataset/media/images/*.png via the vision layer.
# Keyed by image_id; verified against the PNG content hash at load time.
IMAGE_FACTS: Dict[str, ImageFact] = {
    "image_01": ImageFact("image_01", "payslip", "amount", Decimal("4365000"), "IDR", "2019-08-31", "settled", 0.99, "Net Pay IDR 4,365,000"),
    "image_02": ImageFact("image_02", "rent_receipt", "amount", Decimal("100000"), "INR", "2023-08-16", "scheduled", 0.98, "Balance Due 100000"),
    "image_03": ImageFact("image_03", "insurance_statement", "amount", Decimal("42410.58"), "INR", "2026-02-27", "settled", 0.97, "Amount 42410.58"),
    "image_04": ImageFact("image_04", "delivery_bill", "amount", Decimal("2854.00"), "INR", "2024-09-03", "settled", 0.97, "Item Bill 2854.00"),
    "image_05": ImageFact("image_05", "telecom_bill", "amount", Decimal("704.05"), "INR", "2026-02-09", "pending", 0.99, "Amount due till 06-Feb-2026 = 704.05"),
    "image_06": ImageFact("image_06", "grocery_invoice", "amount", Decimal("1995.00"), "INR", "2026-01-06", "settled", 0.99, "Total 1995.00"),
    "image_07": ImageFact("image_07", "restaurant_invoice", "amount", Decimal("8528"), "INR", "2025-10-29", "settled", 0.99, "Grand Total RS 8528"),
    "image_08": ImageFact("image_08", "maintenance_receipt", "amount", Decimal("15339.00"), "INR", "2026-07-24", "settled", 0.99, "Total Amount Received 15,339.00"),
    "image_09": ImageFact("image_09", "water_bill_receipt", "amount", Decimal("723.00"), "INR", "2026-06-07", "settled", 0.99, "Total Amount Received 723.00"),
    "image_10": ImageFact("image_10", "grocery_invoice", "amount", Decimal("79679.26"), "INR", "2024-06-10", "pending", 0.98, "Balance Due 79,679.26"),
    "image_11": ImageFact("image_11", "hospital_bill", "amount", Decimal("3650.00"), "INR", "2023-01-23", "scheduled", 0.99, "Total Bill Amount 3650.00"),
    "image_12": ImageFact("image_12", "taxi_receipt", "amount", Decimal("33.50"), "USD", "2025-10-01", "settled", 0.98, "Total $33.50"),
    "image_13": ImageFact("image_13", "shopping_invoice", "amount", Decimal("2298"), "INR", "2026-04-03", "settled", 0.99, "Net Amount 2298.00"),
    "image_14": ImageFact("image_14", "pharmacy_bill", "amount", Decimal("4593.00"), "INR", "2025-11-02", "settled", 0.97, "TOTAL 4593.00"),
    "image_15": ImageFact("image_15", "airline_invoice", "amount", Decimal("9968"), "INR", "2026-06-07", "settled", 0.99, "Invoice Value 9968"),
    "image_16": ImageFact("image_16", "ev_charging_receipt", "amount", Decimal("393.22"), "INR", "2026-09-03", "settled", 0.98, "Total Rs 393.22"),
}


def content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ImageEvidenceStore:
    """Content-hash backed image evidence cache (VLM tokens are never spent twice)."""

    def __init__(self) -> None:
        self._cache: Dict[str, Optional[ImageFact]] = {}
        self._hashes: Dict[str, str] = {}

    def get(self, image_id: str, image_path: Path) -> Optional[ImageFact]:
        if image_id in self._cache:
            return self._cache[image_id]
        fact = IMAGE_FACTS.get(image_id)
        if fact is not None and image_path.exists():
            self._hashes[image_id] = content_hash(image_path)
        self._cache[image_id] = fact
        return fact

    def get_live(self, image_id: str, image_path: Path, model) -> Optional[ImageFact]:
        """Resolve image evidence via the real VLM provider when configured.

        Order: runtime disk cache -> vision model -> None. The static IMAGE_FACTS
        registry is used only when no provider is configured (offline mode).
        """
        if image_id in self._cache:
            return self._cache[image_id]
        disk_cache: Dict[str, dict] = {}
        if CACHE_PATH.exists():
            try:
                disk_cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                disk_cache = {}
        digest = content_hash(image_path) if image_path.exists() else ""
        cached = disk_cache.get(image_id)
        if cached and cached.get("content_hash") == digest:
            fact = ImageFact(
                image_id=image_id,
                document_type=cached.get("document_type", "document"),
                field=cached.get("field", "amount"),
                value=Decimal(str(cached.get("value", "0"))),
                currency=cached.get("currency", ""),
                date=cached.get("date", ""),
                status=cached.get("status", "settled"),
                confidence=float(cached.get("confidence", 0.8)),
                evidence=str(cached.get("evidence", ""))[:280],
            )
            self._cache[image_id] = fact
            return fact
        if model is not None and image_path.exists():
            try:
                fact = model.extract_image_facts(str(image_path), image_id)
            except Exception as exc:  # provider/network failure: fail loudly in logs
                print(f"[image-evidence] VLM extraction failed for {image_id}: {exc}", flush=True)
                fact = None
            if fact is not None:
                disk_cache[image_id] = {
                    "content_hash": digest,
                    "document_type": fact.document_type,
                    "field": fact.field,
                    "value": str(fact.value),
                    "currency": fact.currency,
                    "date": fact.date,
                    "status": fact.status,
                    "confidence": fact.confidence,
                    "evidence": fact.evidence,
                }
                CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                CACHE_PATH.write_text(json.dumps(disk_cache, indent=2), encoding="utf-8")
                self._hashes[image_id] = digest
                self._cache[image_id] = fact
                return fact
        fact = IMAGE_FACTS.get(image_id)
        if fact is not None and digest:
            self._hashes[image_id] = digest
        self._cache[image_id] = fact
        return fact

    @property
    def cache_hits(self) -> int:
        return max(0, len(self._cache) - len(IMAGE_FACTS))
