"""
LLM provider abstraction.

The rest of the app talks to `get_provider().complete(...)` and never to a
specific vendor SDK. This keeps us free to switch backends — and, importantly,
to run with NO paid dependency at all.

Providers:
  * NoneProvider      — deterministic-only; raises LLMUnavailable so callers fall
                        back to keyword parsing / template narration. Always free.
  * GroqProvider      — Groq free tier (no credit card), OpenAI-compatible HTTP.
  * AnthropicProvider — Anthropic (PAID; requires credits). Kept for parity.

A single primitive — `complete(system, user, json_mode)` — covers both intent
extraction (json_mode=True) and narration (json_mode=False), so every provider is
small and uniform.
"""

from __future__ import annotations

from functools import lru_cache

import httpx

from .config import settings


class LLMUnavailable(RuntimeError):
    """Raised when no usable LLM provider is configured or a call fails."""


class BaseProvider:
    name = "base"

    def complete(self, system: str, user: str, *, max_tokens: int = 500,
                 json_mode: bool = False) -> str:
        raise NotImplementedError


class NoneProvider(BaseProvider):
    name = "none"

    def complete(self, *args, **kwargs) -> str:  # noqa: D401
        raise LLMUnavailable("No LLM provider configured (deterministic mode).")


class GroqProvider(BaseProvider):
    """OpenAI-compatible chat completions against Groq's free tier."""

    name = "groq"

    def __init__(self, api_key: str, model: str, url: str):
        self.api_key = api_key
        self.model = model
        self.url = url

    def complete(self, system: str, user: str, *, max_tokens: int = 500,
                 json_mode: bool = False) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            resp = httpx.post(
                self.url,
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=20,
            )
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"Groq network error: {exc}") from exc
        if resp.status_code != 200:
            raise LLMUnavailable(f"Groq API error {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def complete(self, system: str, user: str, *, max_tokens: int = 500,
                 json_mode: bool = False) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        sys_prompt = system
        if json_mode:
            sys_prompt += "\n\nRespond with a single valid JSON object and nothing else."
        try:
            resp = client.messages.create(
                model=self.model, max_tokens=max_tokens, system=sys_prompt,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:  # billing/auth/etc.
            raise LLMUnavailable(f"Anthropic error: {exc}") from exc
        return "".join(b.text for b in resp.content if b.type == "text").strip()


@lru_cache(maxsize=1)
def get_provider() -> BaseProvider:
    p = settings.llm_provider
    if p == "groq" and settings.groq_api_key:
        return GroqProvider(settings.groq_api_key, settings.groq_model, settings.groq_api_url)
    if p == "anthropic" and settings.anthropic_api_key:
        return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
    return NoneProvider()


def provider_label() -> str:
    """Human-readable label for /health and the UI."""
    prov = get_provider()
    if prov.name == "groq":
        return f"Groq · {settings.groq_model}"
    if prov.name == "anthropic":
        return f"Anthropic · {settings.anthropic_model}"
    return "deterministic"
