from __future__ import annotations

import logging
from dataclasses import dataclass

from app.adapters.firecrawl_client import FirecrawlClient, FirecrawlError, is_pdf_url
from app.adapters.serpapi_client import SerpapiClient
from app.config import get_settings
from app.domain_blocklist import merged_blocked_keys
from app.models.schemas import SourceRecord
from app.observability.run_usage import log_external_cost
from app.research.matcher import assess_product_match, normalize_product_inputs, source_supports_product_match
from app.research.ranker import MATCH_TRUSTED_TIERS, RankedCandidate, rank_results
from app.research.ranker import (
    SOURCE_TIER_AUTHORIZED_DISTRIBUTOR,
    SOURCE_TIER_DATASHEET,
    SOURCE_TIER_ECOMMERCE,
    SOURCE_TIER_MANUFACTURER_PAGE,
    SOURCE_TIER_OTHER,
)
from sqlmodel import Session, select

from app.models.db import AuthorizedDistributor, BlockedDomain, get_engine

logger = logging.getLogger(__name__)

_EVIDENCE_CHAR_LIMIT = 12_000


@dataclass
class ScrapedSource:
    record: SourceRecord
    markdown: str


@dataclass
class ResearchBundle:
    sources: list[ScrapedSource]
    evidence_text: str
    match_verified: bool
    incomplete_reason: str | None
    manufacturer_data_available: bool
    fallback_ecommerce_used: bool
    normalized_manufacturer: str
    normalized_mpn: str


def _load_domain_sets() -> tuple[frozenset[str], frozenset[str]]:
    with Session(get_engine()) as session:
        blocked = [r.domain for r in session.exec(select(BlockedDomain)).all()]
        authorized = [r.domain for r in session.exec(select(AuthorizedDistributor)).all()]
    return merged_blocked_keys(blocked, ()), frozenset(authorized)


async def research_product(*, manufacturer: str, mpn: str) -> ResearchBundle:
    settings = get_settings()
    manufacturer, mpn = normalize_product_inputs(manufacturer, mpn)
    serp = SerpapiClient()
    firecrawl = FirecrawlClient()
    blocked_keys, authorized_keys = _load_domain_sets()

    queries = [
        f'"{mpn}" {manufacturer}',
        f"{manufacturer} {mpn} datasheet",
        f"{manufacturer} {mpn} specifications",
    ]

    organic = []
    seen_urls: set[str] = set()
    for query in queries:
        results = await serp.search(query, num=10, blocked_hosts=tuple(sorted(blocked_keys)))
        log_external_cost(service="serpapi", phase="research", units=1, unit_cost_usd=settings.serpapi_cost_usd)
        for result in results:
            if result.url not in seen_urls:
                seen_urls.add(result.url)
                organic.append(result)

    ranked = rank_results(organic, manufacturer=manufacturer, authorized_domains=authorized_keys)
    scraped: list[ScrapedSource] = []

    for candidate in ranked:
        source = await _scrape_candidate(
            candidate,
            firecrawl=firecrawl,
            manufacturer=manufacturer,
            mpn=mpn,
        )
        scraped.append(source)

    source_inputs = [
        (s.markdown, s.record.tier, s.record.url)
        for s in scraped
        if s.record.scrape_ok and s.markdown
    ]
    assessment = assess_product_match(manufacturer=manufacturer, mpn=mpn, sources=source_inputs)

    manufacturer_data_available = any(
        s.record.tier in {SOURCE_TIER_MANUFACTURER_PAGE, SOURCE_TIER_DATASHEET}
        and s.record.exact_mpn_found
        and s.record.scrape_ok
        for s in scraped
    )
    fallback_ecommerce_used = any(
        s.record.tier in {SOURCE_TIER_AUTHORIZED_DISTRIBUTOR, SOURCE_TIER_ECOMMERCE}
        and s.record.exact_mpn_found
        and s.record.scrape_ok
        for s in scraped
    )

    incomplete_reason = None
    if not assessment.verified:
        if not any(s.record.scrape_ok for s in scraped):
            incomplete_reason = "Required source could not be retrieved via Firecrawl."
        elif not manufacturer_data_available and sum(
            1
            for s in scraped
            if s.record.exact_mpn_found and s.record.scrape_ok and s.record.tier in MATCH_TRUSTED_TIERS
        ) < 2:
            incomplete_reason = (
                "Manufacturer source unavailable and fewer than two reliable exact-match eCommerce sources were found."
            )
        else:
            incomplete_reason = assessment.reason

    evidence_chunks = []
    for source in scraped:
        if (
            source.record.scrape_ok
            and source.markdown
            and source.record.tier in MATCH_TRUSTED_TIERS
            and source.record.exact_mpn_found
        ):
            evidence_chunks.append(
                f"## Source: {source.record.url}\nTier: {source.record.tier}\n\n"
                f"{source.markdown[:_EVIDENCE_CHAR_LIMIT]}"
            )
    evidence_text = "\n\n---\n\n".join(evidence_chunks)

    return ResearchBundle(
        sources=scraped,
        evidence_text=evidence_text,
        match_verified=assessment.verified and bool(evidence_text),
        incomplete_reason=incomplete_reason or (
            "Source evidence was insufficient to satisfy the required prompt output safely."
            if assessment.verified and not evidence_text
            else None
        ),
        manufacturer_data_available=manufacturer_data_available,
        fallback_ecommerce_used=fallback_ecommerce_used,
        normalized_manufacturer=manufacturer,
        normalized_mpn=mpn,
    )


async def _scrape_candidate(
    candidate: RankedCandidate,
    *,
    firecrawl: FirecrawlClient,
    manufacturer: str,
    mpn: str,
) -> ScrapedSource:
    settings = get_settings()
    url = candidate.result.url
    record = SourceRecord(
        url=url,
        title=candidate.result.title,
        tier=candidate.tier,
        domain=candidate.result.domain,
        exact_mpn_found=False,
        scrape_ok=False,
    )

    if candidate.tier == SOURCE_TIER_OTHER:
        record.error = "Skipped low-confidence source tier (archive/forum/unrelated)."
        logger.info("Skipping scrape for other-tier source %s", url)
        return ScrapedSource(record=record, markdown="")

    trusted_pdf_tiers = {
        SOURCE_TIER_MANUFACTURER_PAGE,
        SOURCE_TIER_DATASHEET,
        SOURCE_TIER_AUTHORIZED_DISTRIBUTOR,
    }
    if is_pdf_url(url) and candidate.tier not in trusted_pdf_tiers:
        record.error = (
            "Skipped low-confidence PDF source (likely irrelevant archive/document). "
            "Only manufacturer, datasheet, and authorized-distributor PDFs are scraped."
        )
        logger.info("Skipping PDF scrape for %s (%s tier)", url, candidate.tier)
        return ScrapedSource(record=record, markdown="")

    try:
        response = await firecrawl.scrape(url)
        log_external_cost(
            service="firecrawl", phase="research", units=1, unit_cost_usd=settings.firecrawl_cost_usd
        )
        markdown = FirecrawlClient.extract_markdown(response)
        record.scrape_ok = bool(markdown)
        record.exact_mpn_found = source_supports_product_match(
            markdown,
            manufacturer=manufacturer,
            mpn=mpn,
            tier=candidate.tier,
        )
        return ScrapedSource(record=record, markdown=markdown)
    except FirecrawlError as exc:
        record.error = str(exc)
        logger.warning("Firecrawl failed for %s: %s", url, exc)
        return ScrapedSource(record=record, markdown="")
