"""
QuoteForge Inference Client
=============================
Abstracts LLM inference across backends. Can talk to:
  - vLLM server (production, multi-GPU, OpenAI-compatible)
  - Ollama (local dev, single GPU/CPU)
  - OpenAI API (fallback for when self-hosted is unavailable)

Configure via environment variables:
  LLM_BACKEND=vllm | ollama | openai
  LLM_URL=http://localhost:8001/v1  (vLLM) or http://localhost:11434 (Ollama)
  LLM_MODEL=quoteforge | mistral | llama3.2 | gpt-4o-mini
"""
import os
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

BACKEND = os.getenv("LLM_BACKEND", "ollama").lower()
LLM_URL = os.getenv("LLM_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))


async def generate(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> str:
    """
    Generate text using the configured LLM backend.
    Returns empty string on failure (caller should use fallback).
    """
    try:
        if BACKEND == "vllm":
            return await _call_vllm(system_prompt, user_prompt, max_tokens, temperature)
        elif BACKEND == "openai":
            return await _call_openai(system_prompt, user_prompt, max_tokens, temperature)
        else:
            return await _call_ollama(system_prompt, user_prompt, max_tokens, temperature)
    except Exception as e:
        logger.error(f"Inference failed ({BACKEND}): {e}")
        return ""


async def _call_vllm(system: str, user: str, max_tokens: int, temperature: float) -> str:
    """Call vLLM server (OpenAI-compatible API)."""
    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        resp = await client.post(f"{LLM_URL}/chat/completions", json={
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        })
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


async def _call_ollama(system: str, user: str, max_tokens: int, temperature: float) -> str:
    """Call Ollama local server."""
    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        resp = await client.post(f"{LLM_URL}/api/chat", json={
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        })
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"].strip()


async def _call_openai(system: str, user: str, max_tokens: int, temperature: float) -> str:
    """Call OpenAI API (fallback only)."""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = await client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()


async def check_health() -> dict:
    """Check which backend is available."""
    status = {"backend": BACKEND, "url": LLM_URL, "model": LLM_MODEL, "available": False}
    try:
        if BACKEND == "vllm":
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{LLM_URL}/models")
                status["available"] = resp.status_code == 200
                if status["available"]:
                    status["models"] = [m["id"] for m in resp.json().get("data", [])]
        elif BACKEND == "ollama":
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{LLM_URL}/api/tags")
                status["available"] = resp.status_code == 200
                if status["available"]:
                    status["models"] = [m["name"] for m in resp.json().get("models", [])]
        elif BACKEND == "openai":
            status["available"] = bool(os.getenv("OPENAI_API_KEY"))
    except Exception as e:
        status["error"] = str(e)
    return status
