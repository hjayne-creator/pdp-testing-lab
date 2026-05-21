"""LLM provider clients for text completion with per-run usage tracking."""
from __future__ import annotations

import logging
from typing import Any

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.observability.run_usage import log_llm_usage, monotonic_ms

logger = logging.getLogger(__name__)

XAI_BASE_URL = "https://api.x.ai/v1"


class LLMClientError(RuntimeError):
    pass


class OpenAIClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or get_settings().openai_api_key
        self._client: AsyncOpenAI | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _client_or_raise(self) -> AsyncOpenAI:
        if not self.configured:
            raise LLMClientError("OPENAI_API_KEY is not configured")
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client

    async def complete_text(
        self,
        *,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 4096,
    ) -> str:
        client = self._client_or_raise()
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(min=1, max=8),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                started_at_ms = monotonic_ms()
                attempt_number = attempt.retry_state.attempt_number
                try:
                    response = await client.chat.completions.create(
                        model=model,
                        max_completion_tokens=max_tokens,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                    )
                except Exception as exc:
                    log_llm_usage(
                        provider="openai",
                        model=model,
                        status="error",
                        attempt_number=attempt_number,
                        started_at_ms=started_at_ms,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    raise
                log_llm_usage(
                    provider="openai",
                    model=model,
                    status="success",
                    attempt_number=attempt_number,
                    started_at_ms=started_at_ms,
                    response=response,
                )
                return response.choices[0].message.content or ""
        raise LLMClientError("OpenAI text completion exhausted retries")


class ClaudeClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or get_settings().anthropic_api_key
        self._client: AsyncAnthropic | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _client_or_raise(self) -> AsyncAnthropic:
        if not self.configured:
            raise LLMClientError("ANTHROPIC_API_KEY is not configured")
        if self._client is None:
            self._client = AsyncAnthropic(api_key=self.api_key)
        return self._client

    async def complete_text(
        self,
        *,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 4096,
    ) -> str:
        client = self._client_or_raise()
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(min=1, max=8),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                started_at_ms = monotonic_ms()
                attempt_number = attempt.retry_state.attempt_number
                try:
                    response = await client.messages.create(
                        model=model,
                        system=system,
                        max_tokens=max_tokens,
                        temperature=0.2,
                        messages=[{"role": "user", "content": user}],
                    )
                except Exception as exc:
                    log_llm_usage(
                        provider="anthropic",
                        model=model,
                        status="error",
                        attempt_number=attempt_number,
                        started_at_ms=started_at_ms,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    raise
                log_llm_usage(
                    provider="anthropic",
                    model=model,
                    status="success",
                    attempt_number=attempt_number,
                    started_at_ms=started_at_ms,
                    response=response,
                )
                parts = []
                for block in response.content:
                    text = getattr(block, "text", None)
                    if text:
                        parts.append(text)
                return "\n".join(parts)
        raise LLMClientError("Claude text completion exhausted retries")


class GrokClient:
    def __init__(self, api_key: str | None = None, base_url: str = XAI_BASE_URL) -> None:
        self.api_key = api_key or get_settings().xai_api_key
        self.base_url = base_url
        self._client: AsyncOpenAI | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _client_or_raise(self) -> AsyncOpenAI:
        if not self.configured:
            raise LLMClientError("XAI_API_KEY is not configured")
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    async def complete_text(
        self,
        *,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 4096,
    ) -> str:
        client = self._client_or_raise()
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(min=1, max=8),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                started_at_ms = monotonic_ms()
                attempt_number = attempt.retry_state.attempt_number
                try:
                    response = await client.chat.completions.create(
                        model=model,
                        max_completion_tokens=max_tokens,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                    )
                except Exception as exc:
                    log_llm_usage(
                        provider="xai",
                        model=model,
                        status="error",
                        attempt_number=attempt_number,
                        started_at_ms=started_at_ms,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    raise
                log_llm_usage(
                    provider="xai",
                    model=model,
                    status="success",
                    attempt_number=attempt_number,
                    started_at_ms=started_at_ms,
                    response=response,
                )
                return response.choices[0].message.content or ""
        raise LLMClientError("Grok text completion exhausted retries")
