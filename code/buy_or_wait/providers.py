"""Inference providers for KAIROS — local-first, provider-neutral.

KAIROS keeps every authoritative number in the deterministic engine. This module
only supplies *evidence interpretation*: turning a message or a document image
into candidate financial facts that the engine then verifies. It deliberately
exposes a tiny synchronous interface (``generate`` / ``analyze_image``) so it can
be injected into the existing synchronous pipeline without an event loop. Async
callers can wrap these with ``asyncio.to_thread``.

Design goals (Hacktoberfest "local-first" thesis):

* ``OllamaProvider`` is the default *production* path — no API key, no outbound
  network beyond loopback, zero marginal cost, open-weight models you can swap.
* ``MockProvider`` returns deterministic, schema-valid payloads so the whole
  pipeline (and its tests) runs with **no** model and **no** network at all.
* Existing cloud providers (OpenAI / Anthropic / Google) remain optional and are
  wired through ``llm.EvidenceModel`` exactly as before.

Dependency-free on purpose: Ollama is reached through its plain REST API using
the standard library, so no SDK is added and the offline path stays installable
with only the core requirements.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

from .usage import TRACKER

# Ollama defaults. Any open-weight instruct/VL model pulled into Ollama works;
# override per deployment with TEXT_MODEL / VISION_MODEL / OLLAMA_HOST.
#
# Vision default note: qwen3-vl is a *thinking* model that, on Ollama 0.40.5,
# ignores both `think:false` and `/no_think` and burns its whole output budget on
# reasoning before emitting JSON (`done_reason=length`, empty content) — verified
# against the real runtime. qwen2.5vl (non-thinking) is Ollama's documented pick
# for structured invoice/form extraction and returns clean JSON, so it is the
# default here. Swap freely once a qwen3-vl release fixes thinking-off handling.
DEFAULT_TEXT_MODEL = "qwen3:4b"
DEFAULT_VISION_MODEL = "qwen2.5vl:3b"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"


@dataclass
class ProviderResponse:
    """Raw model output plus the token accounting the engine reports honestly."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class AIProvider:
    """Provider-neutral inference interface.

    Synchronous by design to match the deterministic pipeline. Implementations
    must never raise on a *malformed model reply* — returning the raw text lets
    the caller attempt a bounded repair. They may raise on transport failure
    (server down, model missing) so callers can fail loudly and honestly.
    """

    name = "base"
    is_local = False

    @property
    def available(self) -> bool:
        return True

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        schema: Optional[dict] = None,
        operation: str = "generate",
        evidence_id: str = "",
    ) -> ProviderResponse:
        raise NotImplementedError

    def analyze_image(
        self,
        image: bytes,
        prompt: str,
        system: Optional[str] = None,
        mime_type: str = "image/png",
        schema: Optional[dict] = None,
        evidence_id: str = "",
    ) -> ProviderResponse:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Ollama (local, open-weight) — the primary production path.
# --------------------------------------------------------------------------- #
class OllamaProvider(AIProvider):
    """Talks to a local Ollama server over loopback REST.

    Structured outputs are requested via Ollama's ``format`` field (``"json"`` or
    a JSON schema). No data leaves the machine; token counts come back on every
    response and are recorded with zero cost.
    """

    name = "ollama"
    is_local = True

    def __init__(
        self,
        text_model: Optional[str] = None,
        vision_model: Optional[str] = None,
        host: Optional[str] = None,
        timeout: float = 300.0,
    ) -> None:
        self.text_model = (text_model or os.environ.get("TEXT_MODEL") or DEFAULT_TEXT_MODEL).strip()
        self.vision_model = (vision_model or os.environ.get("VISION_MODEL") or DEFAULT_VISION_MODEL).strip()
        self.host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST).rstrip("/")
        self.timeout = timeout
        # Structured extraction does not benefit from reasoning chains, and on CPU
        # qwen3's thinking loop can run for minutes before emitting JSON (observed:
        # >120s timeout vs ~1s with thinking off). Opt out unless explicitly wanted.
        self.think = os.environ.get("OLLAMA_THINK", "").strip().lower() in {"1", "true", "yes"}

    @property
    def available(self) -> bool:
        return True  # availability is proven per-request; config alone is enough

    # -- transport -------------------------------------------------------- #
    def _post(self, path: str, body: dict) -> dict:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # model missing, bad request, etc.
            detail = exc.read().decode("utf-8", "replace")[:200]
            raise RuntimeError(f"Ollama HTTP {exc.code} on {path}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Ollama unreachable at {self.host} ({exc.reason}). "
                "Start it with `ollama serve` and pull a model, or set MODEL_PROVIDER=mock for offline runs."
            ) from exc

    def list_models(self) -> List[str]:
        """Names of models already pulled locally (used by privacy/health UI)."""
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=5) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return [m.get("name", "") for m in payload.get("models", [])]
        except Exception:
            return []

    # -- inference -------------------------------------------------------- #
    def _chat(
        self,
        model: str,
        prompt: str,
        system: Optional[str],
        schema: Optional[dict],
        images: Optional[List[bytes]],
        operation: str,
        evidence_id: str,
    ) -> ProviderResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        user_msg = {"role": "user", "content": prompt}
        if images:
            user_msg["images"] = [base64.b64encode(b).decode("ascii") for b in images]
        messages.append(user_msg)

        body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0},
            # Ask for JSON; a supplied schema is passed through for models that
            # support native structured outputs.
            "format": schema if schema else "json",
            # Disable reasoning for structured extraction (see __init__). Ollama
            # ignores this field on models without a thinking mode.
            "think": self.think,
        }
        data = self._post("/api/chat", body)
        text = (data.get("message") or {}).get("content", "")
        in_tok = int(data.get("prompt_eval_count", 0) or 0)
        out_tok = int(data.get("eval_count", 0) or 0)
        TRACKER.record("ollama", model, operation, evidence_id, in_tok, out_tok, local=True)
        return ProviderResponse(text=text, input_tokens=in_tok, output_tokens=out_tok)

    def generate(self, prompt, system=None, schema=None, operation="generate", evidence_id=""):
        return self._chat(self.text_model, prompt, system, schema, None, operation, evidence_id)

    def analyze_image(self, image, prompt, system=None, mime_type="image/png", schema=None, evidence_id=""):
        return self._chat(self.vision_model, prompt, system, schema, [image], "image_extraction", evidence_id)


# --------------------------------------------------------------------------- #
# Mock — deterministic, offline, schema-valid. Used by tests and no-model runs.
# --------------------------------------------------------------------------- #
class MockProvider(AIProvider):
    """Returns canned, schema-valid JSON so the pipeline runs with zero network.

    This is not a substitute for a real model; it exists so (a) the extraction →
    validation → engine path is exercised in CI without any model installed, and
    (b) a developer can run KAIROS end-to-end on a plane. The facts it emits are
    deliberately conservative (an unconfirmed-income hint), and the deterministic
    engine still verifies everything.
    """

    name = "mock"
    is_local = True

    def generate(self, prompt, system=None, schema=None, operation="generate", evidence_id=""):
        payload = {
            "facts": [
                {
                    "fact_type": "income_unconfirmed",
                    "amount": None,
                    "currency": None,
                    "date": None,
                    "recurrence": None,
                    "action": "inform",
                    "related_event_id": None,
                    "confidence": 0.2,
                    "evidence": "mock provider: no live model configured",
                }
            ]
        }
        TRACKER.record("mock", "mock-text", operation, evidence_id, 0, 0, local=True)
        return ProviderResponse(text=json.dumps(payload), input_tokens=0, output_tokens=0)

    def analyze_image(self, image, prompt, system=None, mime_type="image/png", schema=None, evidence_id=""):
        payload = {
            "document_type": "document",
            "facts": [
                {
                    "field": "amount",
                    "value": None,
                    "currency": None,
                    "date": None,
                    "status": "unknown",
                    "confidence": 0.2,
                }
            ],
        }
        TRACKER.record("mock", "mock-vision", "image_extraction", evidence_id, 0, 0, local=True)
        return ProviderResponse(text=json.dumps(payload), input_tokens=0, output_tokens=0)


# --------------------------------------------------------------------------- #
# Factory — dependency injection seam. Business logic asks for a provider, never
# for a concrete class. Cloud providers are handled by llm.EvidenceModel.
# --------------------------------------------------------------------------- #
def build_provider() -> Optional[AIProvider]:
    """Return a local provider when configured, else None.

    ``MODEL_PROVIDER=ollama`` (or ``local``) → OllamaProvider.
    ``MODEL_PROVIDER=mock`` (or ``test``)    → MockProvider.
    Anything else (openai/anthropic/google/empty) → None; llm.EvidenceModel keeps
    its existing cloud handling, and empty means the deterministic-only path.
    """
    provider = os.environ.get("MODEL_PROVIDER", "").strip().lower()
    if provider in {"ollama", "local"}:
        return OllamaProvider()
    if provider in {"mock", "test"}:
        return MockProvider()
    return None
