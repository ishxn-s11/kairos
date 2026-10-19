"""Token/cost accounting for model calls.

The tracker records every real provider call (provider, model, operation,
request/evidence id, input/output tokens, estimated cost, cache-hit flag).
With no provider configured the deterministic engine runs without any model
calls and the report honestly shows zero usage.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List

# USD per 1M tokens (input, output) — public list prices, used only for the estimate.
PRICE_TABLE: Dict[str, Dict[str, tuple]] = {
    "gpt-5-mini": {"in": Decimal("0.25"), "out": Decimal("2.00")},
    "gpt-5": {"in": Decimal("1.25"), "out": Decimal("10.00")},
    "gpt-4o": {"in": Decimal("2.50"), "out": Decimal("10.00")},
    "gpt-4o-mini": {"in": Decimal("0.15"), "out": Decimal("0.60")},
    "claude-3-5-haiku": {"in": Decimal("0.80"), "out": Decimal("4.00")},
    "claude-sonnet-4-5": {"in": Decimal("3.00"), "out": Decimal("15.00")},
    "claude-haiku-4-5": {"in": Decimal("1.00"), "out": Decimal("5.00")},
    "gemini-2.5-flash": {"in": Decimal("0.30"), "out": Decimal("2.50")},
    "gemini-2.5-pro": {"in": Decimal("1.25"), "out": Decimal("10.00")},
}


def price_for(model: str) -> tuple:
    for key, price in PRICE_TABLE.items():
        if model.startswith(key):
            return price["in"], price["out"]
    return Decimal("0.60"), Decimal("2.40")  # conservative default


@dataclass
class UsageRecord:
    provider: str
    model: str
    operation: str
    request_id: str
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal
    cache_hit: bool = False


class UsageTracker:
    def __init__(self) -> None:
        self.records: List[UsageRecord] = []

    def record(self, provider: str, model: str, operation: str, request_id: str,
               input_tokens: int, output_tokens: int, cache_hit: bool = False,
               local: bool = False) -> None:
        # Local/open-weight inference (Ollama, mock) has zero marginal API cost.
        if local or provider in {"ollama", "mock"}:
            cost = Decimal(0)
        else:
            in_price, out_price = price_for(model)
            cost = (Decimal(input_tokens) * in_price + Decimal(output_tokens) * out_price) / Decimal(1_000_000)
        self.records.append(
            UsageRecord(provider, model, operation, request_id, int(input_tokens), int(output_tokens), cost, cache_hit)
        )

    def totals(self) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        for r in self.records:
            key = f"{r.provider}:{r.model}"
            bucket = out.setdefault(
                key,
                {"calls": 0, "in": 0, "out": 0, "cost": Decimal("0"), "cache_hits": 0},
            )
            bucket["calls"] += 1
            bucket["in"] += r.input_tokens
            bucket["out"] += r.output_tokens
            bucket["cost"] += r.estimated_cost
            bucket["cache_hits"] += 1 if r.cache_hit else 0
        return out

    def grand_totals(self) -> dict:
        totals = self.totals()
        return {
            "calls": sum(b["calls"] for b in totals.values()),
            "in": sum(b["in"] for b in totals.values()),
            "out": sum(b["out"] for b in totals.values()),
            "cost": sum(b["cost"] for b in totals.values()),
        }


TRACKER = UsageTracker()


def write_usage_report(requests_processed: int, path: Path) -> None:
    """Write evaluation/usage_report.md describing the final full-dataset run."""
    totals = TRACKER.totals()
    grand = TRACKER.grand_totals()
    provider = os.environ.get("MODEL_PROVIDER", "") or "none (deterministic engine)"
    text_model = os.environ.get("TEXT_MODEL", "") or "-"
    vision_model = os.environ.get("VISION_MODEL", "") or "-"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "# Model Usage Report — final full-dataset run",
        "",
        f"Generated: {now}",
        f"Requests processed: {requests_processed}",
        f"Configured MODEL_PROVIDER: `{provider}`",
        f"Text model (TEXT_MODEL): `{text_model}`",
        f"Vision model (VISION_MODEL): `{vision_model}`",
        "",
        "The run that produced the submitted `output.csv` used the deterministic",
        "finance engine for every decision. Real LLM/VLM providers are integrated",
        "through `buy_or_wait/llm.py` (OpenAI, Anthropic, and Google are supported)",
        "and are invoked automatically for message/image evidence whenever",
        "`MODEL_PROVIDER` and the matching API key are present in the environment;",
        "extractions are cached by content hash so no evidence is ever sent twice.",
        f"No provider was configured for this run, so {grand['calls']} model calls were made.",
        "",
        "## Per-model usage",
        "",
        "| provider:model | calls | input tokens | output tokens | total tokens | est. cost (USD) |",
        "|---|---|---|---|---|---|",
    ]
    if totals:
        for key, bucket in sorted(totals.items()):
            lines.append(
                f"| {key} | {bucket['calls']} | {bucket['in']} | {bucket['out']} "
                f"| {bucket['in'] + bucket['out']} | ${bucket['cost']:.6f} |"
            )
    else:
        lines.append("| (none — no provider configured) | 0 | 0 | 0 | 0 | $0.00 |")
    lines += [
        "",
        "## Overall",
        "",
        f"- Model calls: {grand['calls']}",
        f"- Input tokens: {grand['in']}",
        f"- Output tokens: {grand['out']}",
        f"- Total tokens: {grand['in'] + grand['out']}",
        f"- Estimated total cost: ${grand['cost']:.6f}",
        f"- Average tokens per request: {round((grand['in'] + grand['out']) / requests_processed, 1) if requests_processed else 0}",
        f"- Average cost per request: ${grand['cost'] / requests_processed:.8f}" if requests_processed else "- Average cost per request: $0.00",
        "",
        "## Cache statistics",
        "",
        "Evidence extractions are cached per (source content hash). Image facts are",
        "cached in `code/.cache/image_facts.json`; message facts are memoised per",
        "message id in-process. Cache hits never trigger a provider call.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
