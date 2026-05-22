from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from app.adapters.serpapi_client import OrganicResult
from app.domain_blocklist import normalized_host_matches_allowlist
from app.research.scrape_limits import manufacturer_host_tokens, pdf_host_is_trusted


SOURCE_TIER_MANUFACTURER_PAGE = "manufacturer_page"
SOURCE_TIER_DATASHEET = "manufacturer_datasheet"
SOURCE_TIER_AUTHORIZED_DISTRIBUTOR = "authorized_distributor"
SOURCE_TIER_ECOMMERCE = "ecommerce"
SOURCE_TIER_OTHER = "other"

MATCH_TRUSTED_TIERS = frozenset(
    {
        SOURCE_TIER_MANUFACTURER_PAGE,
        SOURCE_TIER_DATASHEET,
        SOURCE_TIER_AUTHORIZED_DISTRIBUTOR,
        SOURCE_TIER_ECOMMERCE,
    }
)


def host_from_url(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


@dataclass
class RankedCandidate:
    result: OrganicResult
    tier: str
    score: float


def _looks_like_pdf(url: str, title: str, snippet: str) -> bool:
    lower = f"{url} {title} {snippet}".lower()
    return url.lower().endswith(".pdf") or "datasheet" in lower or "spec sheet" in lower or "manual" in lower


def classify_result(
    result: OrganicResult,
    *,
    manufacturer: str,
    authorized_domains: frozenset[str],
) -> tuple[str, float]:
    host = host_from_url(result.url)
    host_key = host[4:] if host.startswith("www.") else host
    mfg_tokens = manufacturer_host_tokens(manufacturer)
    title_snippet = f"{result.title} {result.snippet}".lower()

    host_has_mfg = any(token in host_key for token in mfg_tokens)
    title_has_mfg = any(token in title_snippet for token in mfg_tokens)
    if host_has_mfg or title_has_mfg:
        if _looks_like_pdf(result.url, result.title, result.snippet):
            if pdf_host_is_trusted(
                result.url,
                manufacturer=manufacturer,
                authorized_domains=authorized_domains,
            ):
                return SOURCE_TIER_DATASHEET, 100.0
            return SOURCE_TIER_OTHER, 25.0
        if host_has_mfg:
            return SOURCE_TIER_MANUFACTURER_PAGE, 90.0
        return SOURCE_TIER_OTHER, 35.0

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
