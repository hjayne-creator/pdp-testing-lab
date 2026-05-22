"""SerpAPI client for Google organic search."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.domain_blocklist import normalized_host_matches_blocked

logger = logging.getLogger(__name__)


class SerpapiError(RuntimeError):
    pass


@dataclass
class OrganicResult:
    position: int
    title: str
    url: str
    snippet: str
    domain: str


def _blocked_sites_query_suffix(blocked_hosts: Sequence[str]) -> str:
    if not blocked_hosts:
        return ""
    return " ".join(f"-site:{d}" for d in blocked_hosts)


class SerpapiClient:
    BASE_URL = "https://serpapi.com/search.json"

    def __init__(self, api_key: str | None = None, timeout: float = 30.0) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.serpapi_api_key
        self.country = settings.serpapi_country
        self.language = settings.serpapi_language
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def search(
        self,
        query: str,
        num: int = 15,
        engine: str = "google",
        *,
        blocked_hosts: Sequence[str] = (),
    ) -> list[OrganicResult]:
        if not self.configured:
            raise SerpapiError(
                "SERPAPI_API_KEY is not configured. " + get_settings().missing_api_key_hint("SERPAPI_API_KEY")
            )

        suffix = _blocked_sites_query_suffix(tuple(blocked_hosts))
        q = f"{query} {suffix}".strip()
        params: dict[str, Any] = {
            "engine": engine,
            "q": q,
            "api_key": self.api_key,
            "gl": self.country,
            "hl": self.language,
            "num": num,
        }

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(min=1, max=8),
            retry=retry_if_exception_type((httpx.HTTPError,)),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(self.BASE_URL, params=params)
                    if response.status_code >= 400:
                        raise SerpapiError(
                            f"SerpAPI failed: {response.status_code} {response.text[:300]}"
                        )
                    return self._parse_organic(response.json(), blocked_hosts=blocked_hosts)
        raise SerpapiError(f"SerpAPI exhausted retries for query: {query}")

    @staticmethod
    def _parse_organic(data: dict[str, Any], *, blocked_hosts: Sequence[str]) -> list[OrganicResult]:
        blocked_keys = frozenset(blocked_hosts)
        results: list[OrganicResult] = []
        for r in data.get("organic_results", []) or []:
            url = r.get("link") or ""
            if not url:
                continue
            domain = url.split("/")[2] if "//" in url else url
            host = domain.split(":")[0]
            if normalized_host_matches_blocked(host, blocked_keys):
                continue
            results.append(
                OrganicResult(
                    position=int(r.get("position", len(results) + 1)),
                    title=r.get("title", ""),
                    url=url,
                    snippet=r.get("snippet", ""),
                    domain=domain,
                )
            )
        return results
