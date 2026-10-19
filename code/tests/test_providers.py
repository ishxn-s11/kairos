"""Tests for the local-first inference providers and structured-output handling.

Run: python3 -m pytest code/tests/test_providers.py -q

These cover the P0 "open-weight local AI" seam only — they never touch the
deterministic engine's math. No network and no real model are required: the
MockProvider path and a scripted provider exercise the full extract -> validate
-> (repair) -> facts flow, and Ollama request shaping is asserted by stubbing
its transport.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))

from buy_or_wait.llm import EvidenceModel  # noqa: E402
from buy_or_wait.providers import (  # noqa: E402
    AIProvider,
    MockProvider,
    OllamaProvider,
    ProviderResponse,
    build_provider,
)
from buy_or_wait.schemas import validate_image_payload, validate_message_payload  # noqa: E402
from buy_or_wait.usage import TRACKER, UsageTracker  # noqa: E402


# ---------------------------------------------------------------- factory
def test_build_provider_maps_env(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    assert isinstance(build_provider(), OllamaProvider)
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    assert isinstance(build_provider(), MockProvider)
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    assert build_provider() is None  # cloud handled by EvidenceModel, not local
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    assert build_provider() is None


def test_no_provider_is_unavailable(monkeypatch):
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    assert EvidenceModel().available is False


# ---------------------------------------------------------------- schemas
def test_message_schema_accepts_valid_rejects_bad():
    ok, _ = validate_message_payload({"facts": [{"fact_type": "invoice_confirmed", "amount": 1.5, "confidence": 0.9}]})
    assert ok
    assert not validate_message_payload("not an object")[0]
    assert not validate_message_payload({"facts": "nope"})[0]
    assert not validate_message_payload({"facts": [{"amount": "abc"}]})[0]


def test_image_schema_accepts_valid_rejects_bad():
    ok, _ = validate_image_payload({"document_type": "invoice", "facts": [{"field": "amount", "value": 12.3}]})
    assert ok
    assert not validate_image_payload({"facts": [{"value": "abc"}]})[0]


# ---------------------------------------------------------------- mock path
def test_mock_provider_message_path_is_schema_valid(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    model = EvidenceModel()
    assert model.available
    facts = model.extract_message_facts("Client says invoice #44 is paid.", "m1", "e1")
    assert isinstance(facts, list) and facts
    assert all(f.fact_type for f in facts)


def test_mock_provider_image_path_degrades_gracefully(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    img = tmp_path / "doc.png"
    img.write_bytes(b"\x89PNG-fake")
    model = EvidenceModel()
    # Mock emits no numeric value, so the fact must be dropped (unknown stays unknown).
    assert model.extract_image_facts(str(img), "image_x") is None


# ---------------------------------------------------------------- bounded repair
class _Scripted(AIProvider):
    name = "scripted"
    is_local = True

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def generate(self, prompt, system=None, schema=None, operation="generate", evidence_id=""):
        self.calls += 1
        return ProviderResponse(text=self.replies.pop(0))

    def analyze_image(self, image, prompt, system=None, mime_type="image/png", schema=None, evidence_id=""):
        return self.generate(prompt, system, schema, "image_extraction", evidence_id)


def test_local_retry_recovers_after_invalid_json(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    model = EvidenceModel()
    good = json.dumps({"facts": [{"fact_type": "invoice_confirmed", "amount": 123.45,
                                  "currency": "USD", "date": "2026-01-01", "confidence": 0.9}]})
    scripted = _Scripted(["this is not json", good])
    model._local = scripted
    facts = model.extract_message_facts("Invoice #44 paid USD 123.45", "m9", "e1")
    assert scripted.calls == 2
    assert any(f.fact_type == "invoice_confirmed" and f.amount == Decimal("123.45") for f in facts)


def test_local_retry_exhausted_degrades_to_irrelevant(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    model = EvidenceModel()
    scripted = _Scripted(["garbage", "still garbage"])
    model._local = scripted
    facts = model.extract_message_facts("anything", "m10", "")
    assert scripted.calls == 2  # exactly one repair, then give up honestly
    assert all(f.fact_type == "irrelevant_or_unknown" for f in facts)


def test_local_image_retry_recovers(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    img = tmp_path / "doc.png"
    img.write_bytes(b"\x89PNG-fake")
    model = EvidenceModel()
    bad = json.dumps({"facts": [{"value": "not-a-number"}]})
    good = json.dumps({"document_type": "invoice", "facts": [{"field": "amount", "value": 55.5, "confidence": 0.8}]})
    scripted = _Scripted([bad, good])
    model._local = scripted
    fact = model.extract_image_facts(str(img), "image_y")
    assert scripted.calls == 2
    assert fact is not None and fact.value == Decimal("55.5")


# ---------------------------------------------------------------- ollama shaping
def test_ollama_generate_shapes_request_and_records_zero_cost(monkeypatch):
    provider = OllamaProvider(text_model="qwen3:4b")
    captured = {}

    def fake_post(path, body):
        captured["path"] = path
        captured["body"] = body
        return {"message": {"content": '{"facts":[]}'}, "prompt_eval_count": 10, "eval_count": 5}

    monkeypatch.setattr(provider, "_post", fake_post)
    before = len(TRACKER.records)
    resp = provider.generate("hi", system="sys-prompt")

    assert captured["path"] == "/api/chat"
    assert captured["body"]["model"] == "qwen3:4b"
    assert captured["body"]["format"] == "json"
    assert captured["body"]["options"]["temperature"] == 0
    assert captured["body"]["messages"][0] == {"role": "system", "content": "sys-prompt"}
    assert resp.input_tokens == 10 and resp.output_tokens == 5

    assert len(TRACKER.records) == before + 1
    rec = TRACKER.records[-1]
    assert rec.provider == "ollama" and rec.estimated_cost == 0


def test_ollama_vision_base64_encodes_image(monkeypatch):
    provider = OllamaProvider(vision_model="qwen3-vl:4b")
    captured = {}
    monkeypatch.setattr(
        provider, "_post",
        lambda path, body: captured.update(path=path, body=body)
        or {"message": {"content": "{}"}, "prompt_eval_count": 1, "eval_count": 1},
    )
    provider.analyze_image(b"\x89PNG-fake", "describe this bill")
    user = captured["body"]["messages"][-1]
    assert captured["body"]["model"] == "qwen3-vl:4b"
    assert user["images"] and isinstance(user["images"][0], str)


# ---------------------------------------------------------------- usage honesty
def test_local_usage_is_zero_cost_cloud_is_not():
    local = UsageTracker()
    local.record("ollama", "qwen3:4b", "message_extraction", "m", 100, 50, local=True)
    assert local.grand_totals()["cost"] == 0

    cloud = UsageTracker()
    cloud.record("openai", "gpt-5-mini", "message_extraction", "m", 100, 50)
    assert cloud.grand_totals()["cost"] > 0


# --------------------------------- schema robustness (real open-weight model quirks)
# Two bugs found by running REAL Ollama inference, pinned so they cannot return:
#  1. qwen2.5vl emits "confidence": "High" (string) — must not reject a good fact.
#  2. models quote amounts as strings ("1,840.50") — must parse; "abc" must fail.

def test_qualitative_and_null_confidence_are_accepted():
    assert validate_message_payload({"facts": [{"fact_type": "invoice_confirmed", "confidence": "High"}]})[0]
    assert validate_message_payload({"facts": [{"fact_type": "x", "confidence": None}]})[0]
    assert validate_image_payload({"document_type": "d", "facts": [{"value": "8528.10", "confidence": "High"}]})[0]


def test_numeric_strings_accepted_but_garbage_rejected():
    assert validate_message_payload({"facts": [{"amount": "1,840.50"}]})[0]
    assert not validate_message_payload({"facts": [{"amount": "abc"}]})[0]
    assert validate_image_payload({"facts": [{"value": "8528.10"}]})[0]
    assert not validate_image_payload({"facts": [{"value": "abc"}]})[0]


def test_build_coerces_string_amount_and_qualitative_confidence():
    model = EvidenceModel()
    payload = json.dumps({"facts": [{"fact_type": "invoice_confirmed", "amount": "1,840.50",
                                     "confidence": "High", "currency": "USD"}]})
    facts, error = model._parse_message_json(payload, "m", "e")
    assert not error and facts
    assert facts[0].amount == Decimal("1840.50")   # comma-stripped
    assert facts[0].confidence == 0.8               # qualitative -> documented default


def test_build_image_string_value_and_confidence():
    model = EvidenceModel()
    payload = json.dumps({"document_type": "Tax Invoice", "facts": [{
        "field": "Grand Total", "value": "8,528.10", "confidence": "High", "status": "Paid",
    }]})
    fact, error = model._parse_image_json(payload, "i")
    assert not error and fact is not None
    assert fact.value == Decimal("8528.10")
    assert fact.confidence == 0.8
