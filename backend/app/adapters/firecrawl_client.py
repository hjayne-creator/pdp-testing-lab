"""Thin async wrapper around the Firecrawl /v1/scrape endpoint."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = logging.getLogger(__name__)

PDF_INSUFFICIENT_TIME_CODE = "SCRAPE_PDF_INSUFFICIENT_TIME_ERROR"


class FirecrawlError(RuntimeError):
    pass


def is_pdf_url(url: str) -> bool:
    path = (urlparse(url).path or "").lower()
    return path.endswith(".pdf")


def _scrape_payload(
    url: str,
    formats: list[str] | None,
    wait_for_ms: int | None,
    timeout_ms: int | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": url,
        "formats": formats or ["markdown"],
        "onlyMainContent": True,
        "blockAds": True,
        "removeBase64Images": True,
        "maxAge": 259200000,
    }
    if wait_for_ms is not None:
        payload["waitFor"] = wait_for_ms
    if timeout_ms is not None:
        payload["timeout"] = timeout_ms
    return payload


def _response_error_code(response: httpx.Response) -> str | None:
    try:
        data = response.json()
    except ValueError:
        return None
    if isinstance(data, dict):
        return data.get("code")
    return None


class FirecrawlClient:
    BASE_URL = "https://api.firecrawl.dev/v1"

    def __init__(self, api_key: str | None = None, timeout: float | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.firecrawl_api_key
        self.wait_for_ms = settings.firecrawl_wait_for_ms
        self.timeout_ms = settings.firecrawl_timeout_ms
        self.pdf_timeout_ms = settings.firecrawl_pdf_timeout_ms
        self.pdf_retry_timeout_ms = settings.firecrawl_pdf_retry_timeout_ms
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _timeout_ms_for_url(self, url: str, *, override_ms: int | None = None) -> int:
        if override_ms is not None:
            return override_ms
        if is_pdf_url(url):
            return self.pdf_timeout_ms
        return self.timeout_ms

    def _http_timeout_seconds(self, timeout_ms: int) -> float:
        if self.timeout is not None:
            return self.timeout
        return (timeout_ms / 1000.0) + 30.0

    async def scrape(
        self,
        url: str,
        formats: list[str] | None = None,
        *,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            raise FirecrawlError("FIRECRAWL_API_KEY is not configured")

        effective_timeout_ms = self._timeout_ms_for_url(url, override_ms=timeout_ms)
        return await self._scrape_once(url, formats, effective_timeout_ms)

    async def _scrape_once(
        self,
        url: str,
        formats: list[str] | None,
        timeout_ms: int,
    ) -> dict[str, Any]:
        payload = _scrape_payload(url, formats, self.wait_for_ms, timeout_ms)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        http_timeout = self._http_timeout_seconds(timeout_ms)

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(min=1, max=8),
            retry=retry_if_exception_type((httpx.HTTPError,)),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(timeout=http_timeout) as client:
                    response = await client.post(
                        f"{self.BASE_URL}/scrape",
                        json=payload,
                        headers=headers,
                    )
                    if response.status_code >= 400:
                        error_code = _response_error_code(response)
                        if (
                            error_code == PDF_INSUFFICIENT_TIME_CODE
                            and is_pdf_url(url)
                            and timeout_ms < self.pdf_retry_timeout_ms
                        ):
                            logger.info(
                                "Firecrawl PDF timeout for %s at %sms; retrying with %sms",
                                url,
                                timeout_ms,
                                self.pdf_retry_timeout_ms,
                            )
                            return await self._scrape_once(url, formats, self.pdf_retry_timeout_ms)
                        raise FirecrawlError(
                            f"Firecrawl scrape failed for {url}: {response.status_code} {response.text[:300]}"
                        )
                    return response.json()
        raise FirecrawlError(f"Firecrawl scrape exhausted retries for {url}")

    @staticmethod
    def extract_markdown(response: dict[str, Any]) -> str:
        data = response.get("data") or {}
        markdown = data.get("markdown") or ""
        return markdown.strip()
