"""
ModelBackend abstraction — one method: generate(prompt) -> str.

Four implementations:

  MLXBackend    — Apple Silicon local inference via mlx_lm. Phase 0/demo.
  OllamaBackend — HTTP to a local Ollama server. Phase 1 production.
  VLLMBackend   — HTTP to a vLLM OpenAI-compatible endpoint. Phase 2+.
  StubBackend   — pure-Python deterministic. For CI and the Module 3
                   curl proofs, where we don't have a real model handy.

Pick via settings.NEGOTIATION_MODEL_BACKEND. Everything above this line
(service, adapter, tool) is backend-agnostic.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.gateway.negotiation.context import NegotiationContext

logger = logging.getLogger(__name__)


class ModelBackend(Protocol):
    """Minimal interface — one async method. `name` is logged to Replay Layer."""

    name: str

    async def generate(self, prompt: str) -> str: ...


# ---------------------------------------------------------------------------
# MLX (Apple Silicon, local)
# ---------------------------------------------------------------------------

class MLXBackend:
    """Loads the fine-tuned V3 adapter from NEGOTIATION_MODEL_PATH via mlx_lm.

    Heavy import — mlx_lm pulls the whole framework. Imports are lazy so the
    FastAPI process only loads MLX when this backend is actually selected.
    """

    name = "mlx"

    def __init__(self) -> None:
        self._model = None
        self._tokenizer = None

    def _load(self) -> None:
        if self._model is not None:
            return
        from mlx_lm import load  # type: ignore  # noqa: PLC0415
        self._model, self._tokenizer = load(settings.NEGOTIATION_MODEL_PATH)

    async def generate(self, prompt: str) -> str:
        self._load()
        from mlx_lm import generate  # type: ignore  # noqa: PLC0415

        def _run() -> str:
            return generate(
                self._model, self._tokenizer,
                prompt=prompt,
                max_tokens=settings.NEGOTIATION_MAX_TOKENS,
                verbose=False,
            )

        # MLX is sync — push it off the event loop so the server stays responsive.
        return await asyncio.get_running_loop().run_in_executor(None, _run)


# ---------------------------------------------------------------------------
# Ollama (HTTP, local or remote)
# ---------------------------------------------------------------------------

class OllamaBackend:
    name = "ollama"

    def __init__(self) -> None:
        self._url = f"{settings.NEGOTIATION_OLLAMA_URL.rstrip('/')}/api/generate"
        self._model = settings.NEGOTIATION_OLLAMA_MODEL

    async def generate(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=settings.NEGOTIATION_TIMEOUT_SECONDS) as client:
            resp = await client.post(self._url, json={
                "model": self._model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": settings.NEGOTIATION_MAX_TOKENS, "temperature": 0.2},
            })
            resp.raise_for_status()
            data = resp.json()
        return str(data.get("response", ""))


# ---------------------------------------------------------------------------
# vLLM (OpenAI-compatible HTTP)
# ---------------------------------------------------------------------------

class VLLMBackend:
    name = "vllm"

    def __init__(self) -> None:
        self._url = f"{settings.NEGOTIATION_VLLM_URL.rstrip('/')}/v1/completions"
        self._model = settings.NEGOTIATION_VLLM_MODEL

    async def generate(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=settings.NEGOTIATION_TIMEOUT_SECONDS) as client:
            resp = await client.post(self._url, json={
                "model": self._model,
                "prompt": prompt,
                "max_tokens": settings.NEGOTIATION_MAX_TOKENS,
                "temperature": 0.2,
            })
            resp.raise_for_status()
            data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            return ""
        return str(choices[0].get("text", ""))


# ---------------------------------------------------------------------------
# Stub — deterministic, steered via deal_name
# ---------------------------------------------------------------------------

class StubBackend:
    """
    Integration-test backend. Reads the NegotiationContext out of the
    prompt header line and chooses a response based on `deal_name`:

      deal_name starts with "stub:pass"    → propose base_price (always passes)
      deal_name starts with "stub:retry"   → attempt 1 under-floors; attempt 2 base
      deal_name starts with "stub:fail"    → under-floors forever (fallback)
      deal_name starts with "stub:timeout" → sleeps past the timeout
      deal_name starts with "stub:garbage" → emits non-JSON text
      default                              → propose base_price

    The prompt includes the full NegotiationContext JSON so we don't need any
    side-channel to route.
    """

    name = "stub"

    def __init__(self) -> None:
        self._attempts_by_deal: dict[str, int] = {}

    @staticmethod
    def _extract_request_blob(prompt: str) -> dict[str, Any]:
        # Prompt layout per prompt.py: "<|user|>\n<json>\n<|assistant|>\n"
        start = prompt.find("<|user|>")
        end = prompt.find("<|assistant|>", start)
        if start == -1 or end == -1:
            return {}
        body = prompt[start + len("<|user|>"):end].strip()
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}

    async def generate(self, prompt: str) -> str:
        request = self._extract_request_blob(prompt)
        buyer = request.get("buyer", {}) if isinstance(request, dict) else {}
        deal_name = str(buyer.get("deal_name", "")).lower()
        lines = request.get("line_items", []) if isinstance(request, dict) else []

        # Track attempt count per deal_name so stub:retry can progress.
        self._attempts_by_deal[deal_name] = self._attempts_by_deal.get(deal_name, 0) + 1
        attempt_n = self._attempts_by_deal[deal_name]

        if deal_name.startswith("stub:timeout"):
            # Sleep past the client-side timeout so the service aborts.
            await asyncio.sleep(settings.NEGOTIATION_TIMEOUT_SECONDS + 2)

        if deal_name.startswith("stub:garbage"):
            return "sure here is my answer <not even close to json>"

        # Build proposals keyed by sku.
        proposals: dict[str, int] = {}
        rationale = "stub backend"

        def under_floor(line: dict[str, Any]) -> int:
            # Price at 99% of floor, so MaxDiscount or MinMargin will fire
            # depending on policy.
            return max(1, int(line["min_price_floor_cents"] * 0.99))

        def base(line: dict[str, Any]) -> int:
            return int(line["base_price_cents"])

        for line in lines:
            if deal_name.startswith("stub:fail"):
                proposals[line["sku"]] = under_floor(line)
                rationale = "stub:fail — always under-prices"
            elif deal_name.startswith("stub:retry"):
                if attempt_n == 1:
                    proposals[line["sku"]] = under_floor(line)
                    rationale = "stub:retry attempt 1 (expected to fail)"
                else:
                    proposals[line["sku"]] = base(line)
                    rationale = f"stub:retry attempt {attempt_n} at base"
            else:
                proposals[line["sku"]] = base(line)
                rationale = "stub:pass — priced at base"

        return json.dumps({
            "proposed_unit_prices": proposals,
            "rationale": rationale,
            "confidence": 0.9,
        })


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_BACKENDS: dict[str, type] = {
    "mlx": MLXBackend,
    "ollama": OllamaBackend,
    "vllm": VLLMBackend,
    "stub": StubBackend,
}

_instance: ModelBackend | None = None


def get_backend() -> ModelBackend:
    """Module-level singleton so backends that load model weights do so once."""
    global _instance
    if _instance is None:
        cls = _BACKENDS.get(settings.NEGOTIATION_MODEL_BACKEND)
        if cls is None:
            logger.warning(
                "unknown NEGOTIATION_MODEL_BACKEND=%s, falling back to stub",
                settings.NEGOTIATION_MODEL_BACKEND,
            )
            cls = StubBackend
        _instance = cls()
        logger.info("negotiation backend initialized: %s", _instance.name)
    return _instance


def reset_backend_for_tests() -> None:
    """Only for use by unit tests that want a fresh backend state."""
    global _instance
    _instance = None
