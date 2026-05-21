from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from app.adapters.serpapi_client import OrganicResult
from app.domain_blocklist import normalized_host_matches_allowlist
from app.research.matcher import host_from_url


SOURCE_TIER_MANUFACTURER_PAGE = "manufacturer_page"
SOURCE_TIER_DATASHEET = "manufacturer_datasheet"
SOURCE_TIER_AUTHORIZED_DISTRIBUTOR = "authorized_distributor"
SOURCE_TIER_ECOMMERCE = "ecommerce"
SOURCE_TIER_OTHER = "other"


@dataclass
class RankedCandidate:
    result: OrganicResult
    tier: str
    score: float


def _looks_like_pdf(url: str, title: str, snippet: str) -> bool:
    lower = f"{url} {title} {snippet}".lower()
    return url.lower().endswith(".pdf") or "datasheet" in lower or "spec sheet" in lower or "manual" in lower


def _manufacturer_host_hint(manufacturer: str) -> set[str]:
    tokens = [t for t in manufacturer.lower().replace(",", " ").split() if len(t) >= 4]
    return set(tokens)


def classify_result(
    result: OrganicResult,
    *,
    manufacturer: str,
    authorized_domains: frozenset[str],
) -> tuple[str, float]:
    host = host_from_url(result.url)
    host_key = host[4:] if host.startswith("www.") else host
    mfg_tokens = _manufacturer_host_hint(manufacturer)
    title_snippet = f"{result.title} {result.snippet}".lower()

    if any(token in host_key for token in mfg_tokens) or any(token in title_snippet for token in mfg_tokens):
        if _looks_like_pdf(result.url, result.title, result.snippet):
            return SOURCE_TIER_DATASHEET, 100.0
        return SOURCE_TIER_MANUFACTURER_PAGE, 90.0

    if normalized_host_matches_allowlist(host_key, authorized_domains):
        return SOURCE_TIER_AUTHORIZED_DISTRIBUTOR, 70.0

    if any(token in title_snippet for token in ("buy", "shop", "price", "in stock", "add to cart")):
        return SOURCE_TIER_ECOMMERCE, 50.0

    return SOURCE_TIER_OTHER, 30.0


def rank_results(
    results: list[OrganicResult],
    *,
    manufacturer: str,
    authorized_domains: frozenset[str],
    limit: int = 8,
) -> list[RankedCandidate]:
    ranked: list[RankedCandidate] = []
    seen_urls: set[str] = set()
    for result in results:
        if result.url in seen_urls:
            continue
        seen_urls.add(result.url)
        tier, score = classify_result(result, manufacturer=manufacturer, authorized_domains=authorized_domains)
        ranked.append(RankedCandidate(result=result, tier=tier, score=score))
    ranked.sort(key=lambda c: (-c.score, c.result.position))
    return ranked[:limit]
