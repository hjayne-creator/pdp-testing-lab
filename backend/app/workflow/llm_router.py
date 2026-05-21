from __future__ import annotations

from app.adapters.llm_clients import ClaudeClient, GrokClient, LLMClientError, OpenAIClient


def provider_for_model(model_id: str, *, provider_hint: str | None = None) -> str:
    if provider_hint:
        return provider_hint
    lower = model_id.lower()
    if lower.startswith("gpt-") or lower.startswith("o"):
        return "openai"
    if "claude" in lower:
        return "anthropic"
    if "grok" in lower:
        return "xai"
    raise LLMClientError(f"Cannot infer provider for model: {model_id}")


async def complete_text(*, model: str, provider: str, system: str, user: str) -> str:
    if provider == "openai":
        return await OpenAIClient().complete_text(model=model, system=system, user=user)
    if provider == "anthropic":
        return await ClaudeClient().complete_text(model=model, system=system, user=user)
    if provider == "xai":
        return await GrokClient().complete_text(model=model, system=system, user=user)
    raise LLMClientError(f"Unsupported provider: {provider}")
