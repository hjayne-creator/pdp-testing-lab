from __future__ import annotations

import logging
from dataclasses import dataclass

from app.adapters.firecrawl_client import FirecrawlClient, FirecrawlError, is_pdf_url
from app.adapters.serpapi_client import SerpapiClient
from app.config import get_settings
from app.domain_blocklist import merged_blocked_keys
from app.models.schemas import SourceRecord
from app.observability.run_usage import log_external_cost
from app.research.matcher import (
    RESEARCH_TIER_COMPETITOR_PROXY,
    RESEARCH_TIER_EXACT_MANUFACTURER,
    RESEARCH_TIER_FAMILY_SERIES,
    RESEARCH_TIER_NONE,
    assess_research_tier,
    normalize_product_inputs,
    source_supports_competitor_match,
    source_supports_exact_manufacturer_match,
    source_supports_family_match,
    source_supports_product_match,
)
from app.research.ranker import (
    MANUFACTURER_SOURCE_TIERS,
    MATCH_TRUSTED_TIERS,
    RankedCandidate,
    rank_competitor_results,
    rank_results,
)
from app.research.ranker import (
    SOURCE_TIER_AUTHORIZED_DISTRIBUTOR,
    SOURCE_TIER_COMPETITOR,
    SOURCE_TIER_DATASHEET,
    SOURCE_TIER_ECOMMERCE,
    SOURCE_TIER_MANUFACTURER_PAGE,
    SOURCE_TIER_OTHER,
)
from app.research.scrape_limits import (
    cap_scraped_markdown,
    evidence_slice,
    pdf_host_is_trusted,
    remote_pdf_byte_size,
)
from sqlmodel import Session, select

from app.models.db import AuthorizedDistributor, BlockedDomain, get_engine

logger = logging.getLogger(__name__)

_EVIDENCE_HEADERS = {
    RESEARCH_TIER_EXACT_MANUFACTURER: "Match mode: exact_manufacturer",
    RESEARCH_TIER_FAMILY_SERIES: "Match mode: family_series (MPN may not appear on this page)",
    RESEARCH_TIER_COMPETITOR_PROXY: "Match mode: competitor_proxy (competitive analogs, not OEM-verified)",
}


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
    product_family_hint: str = ""
    research_tier: str = RESEARCH_TIER_NONE
    research_tier_reason: str = ""


def _load_domain_sets() -> tuple[frozenset[str], frozenset[str]]:
    with Session(get_engine()) as session:
        blocked = [r.domain for r in session.exec(select(BlockedDomain)).all()]
        authorized = [r.domain for r in session.exec(select(AuthorizedDistributor)).all()]
    return merged_blocked_keys(blocked, ()), frozenset(authorized)


async def _run_serp_queries(
    serp: SerpapiClient,
    queries: list[str],
    *,
    blocked_keys: frozenset[str],
) -> list:
    settings = get_settings()
    organic = []
    seen_urls: set[str] = set()
    for query in queries:
        results = await serp.search(query, num=10, blocked_hosts=tuple(sorted(blocked_keys)))
        log_external_cost(service="serpapi", phase="research", units=1, unit_cost_usd=settings.serpapi_cost_usd)
        for result in results:
            if result.url not in seen_urls:
                seen_urls.add(result.url)
                organic.append(result)
    return organic


def _exact_tier_satisfied(scraped: list[ScrapedSource]) -> bool:
    return any(
        s.record.scrape_ok
        and s.record.exact_manufacturer_match
        for s in scraped
    )


def _family_tier_satisfied(scraped: list[ScrapedSource]) -> bool:
    return any(
        s.record.scrape_ok
        and s.record.tier in MANUFACTURER_SOURCE_TIERS
        and s.record.family_match_found
        for s in scraped
    )


def _build_evidence(
    scraped: list[ScrapedSource],
    *,
    research_tier: str,
    settings=None,
) -> str:
    settings = settings or get_settings()
    header = _EVIDENCE_HEADERS.get(research_tier, "Match mode: unknown")
    evidence_chunks = [header]
    for source in scraped:
        if not source.record.scrape_ok or not source.markdown:
            continue
        if source.record.tier not in MATCH_TRUSTED_TIERS:
            continue
        include = False
        if research_tier == RESEARCH_TIER_EXACT_MANUFACTURER:
            include = source.record.exact_manufacturer_match and source.record.tier in MANUFACTURER_SOURCE_TIERS
        elif research_tier == RESEARCH_TIER_FAMILY_SERIES:
            include = source.record.family_match_found and source.record.tier in MANUFACTURER_SOURCE_TIERS
        elif research_tier == RESEARCH_TIER_COMPETITOR_PROXY:
            include = source.record.tier == SOURCE_TIER_COMPETITOR and source.record.competitor_match_found
        if include:
            evidence_chunks.append(
                f"## Source: {source.record.url}\nTier: {source.record.tier}\n\n"
                f"{evidence_slice(source.markdown, settings)}"
            )
    return "\n\n---\n\n".join(evidence_chunks) if len(evidence_chunks) > 1 else ""


def _finalize_bundle(
    scraped: list[ScrapedSource],
    *,
    manufacturer: str,
    mpn: str,
    family_hint: str,
    assessment,
) -> ResearchBundle:
    settings = get_settings()
    research_tier = assessment.research_tier
    evidence_text = _build_evidence(scraped, research_tier=research_tier, settings=settings)

    manufacturer_data_available = research_tier in {
        RESEARCH_TIER_EXACT_MANUFACTURER,
        RESEARCH_TIER_FAMILY_SERIES,
    }
    fallback_ecommerce_used = research_tier == RESEARCH_TIER_COMPETITOR_PROXY

    incomplete_reason = None
    if not assessment.verified:
        if not any(s.record.scrape_ok for s in scraped):
            incomplete_reason = "Required source could not be retrieved via Firecrawl."
        else:
            incomplete_reason = assessment.reason

    match_verified = assessment.verified and bool(evidence_text)
    if assessment.verified and not evidence_text:
        incomplete_reason = "Source evidence was insufficient to satisfy the required prompt output safely."

    return ResearchBundle(
        sources=scraped,
        evidence_text=evidence_text,
        match_verified=match_verified,
        incomplete_reason=incomplete_reason,
        manufacturer_data_available=manufacturer_data_available,
        fallback_ecommerce_used=fallback_ecommerce_used,
        normalized_manufacturer=manufacturer,
        normalized_mpn=mpn,
        product_family_hint=family_hint,
        research_tier=research_tier,
        research_tier_reason=assessment.reason,
    )


async def research_product(
    *,
    manufacturer: str,
    mpn: str,
    product_family_hint: str = "",
) -> ResearchBundle:
    settings = get_settings()
    manufacturer, mpn = normalize_product_inputs(manufacturer, mpn)
    family_hint = (product_family_hint or "").strip()
    serp = SerpapiClient()
    firecrawl = FirecrawlClient()
    blocked_keys, authorized_keys = _load_domain_sets()

    base_queries = [
        f'"{mpn}" {manufacturer}',
        f"{manufacturer} {mpn} datasheet",
        f"{manufacturer} {mpn} specifications",
    ]
    organic = await _run_serp_queries(serp, base_queries, blocked_keys=blocked_keys)
    ranked = rank_results(
        organic,
        manufacturer=manufacturer,
        authorized_domains=authorized_keys,
    )

    scraped: list[ScrapedSource] = []
    seen_urls: set[str] = set()

    for candidate in ranked:
        if candidate.result.url in seen_urls:
            continue
        seen_urls.add(candidate.result.url)
        source = await _scrape_candidate(
            candidate,
            firecrawl=firecrawl,
            manufacturer=manufacturer,
            mpn=mpn,
            family_hint=family_hint,
            authorized_domains=authorized_keys,
        )
        scraped.append(source)
        if _exact_tier_satisfied(scraped):
            break

    if _exact_tier_satisfied(scraped):
        assessment = assess_research_tier(
            manufacturer=manufacturer,
            mpn=mpn,
            family_hint=family_hint,
            sources=[
                (s.markdown, s.record.tier, s.record.url, s.record.scrape_ok) for s in scraped
            ],
        )
        return _finalize_bundle(
            scraped, manufacturer=manufacturer, mpn=mpn, family_hint=family_hint, assessment=assessment
        )

    if family_hint:
        family_queries = [
            f'"{family_hint}" {manufacturer}',
            f"{manufacturer} {family_hint} series",
            f"{manufacturer} {family_hint} models configurations",
        ]
        family_organic = await _run_serp_queries(serp, family_queries, blocked_keys=blocked_keys)
        family_ranked = rank_results(
            family_organic,
            manufacturer=manufacturer,
            authorized_domains=authorized_keys,
        )
        for candidate in family_ranked:
            if candidate.result.url in seen_urls:
                continue
            if candidate.tier not in MANUFACTURER_SOURCE_TIERS:
                continue
            seen_urls.add(candidate.result.url)
            source = await _scrape_candidate(
                candidate,
                firecrawl=firecrawl,
                manufacturer=manufacturer,
                mpn=mpn,
                family_hint=family_hint,
                authorized_domains=authorized_keys,
            )
            scraped.append(source)
            if _family_tier_satisfied(scraped):
                break

        if _family_tier_satisfied(scraped):
            assessment = assess_research_tier(
                manufacturer=manufacturer,
                mpn=mpn,
                family_hint=family_hint,
                sources=[
                    (s.markdown, s.record.tier, s.record.url, s.record.scrape_ok) for s in scraped
                ],
            )
            return _finalize_bundle(
                scraped, manufacturer=manufacturer, mpn=mpn, family_hint=family_hint, assessment=assessment
            )

    competitor_queries = [
        f"{manufacturer} {mpn} alternative",
        f"{manufacturer} {family_hint} similar product".strip() if family_hint else f"{mpn} competitor product",
        f"{manufacturer} {mpn} buy",
    ]
    competitor_organic = await _run_serp_queries(serp, competitor_queries, blocked_keys=blocked_keys)
    competitor_ranked = rank_competitor_results(competitor_organic, manufacturer=manufacturer, limit=3)
    for candidate in competitor_ranked:
        if candidate.result.url in seen_urls:
            continue
        seen_urls.add(candidate.result.url)
        source = await _scrape_candidate(
            candidate,
            firecrawl=firecrawl,
            manufacturer=manufacturer,
            mpn=mpn,
            family_hint=family_hint,
            authorized_domains=authorized_keys,
        )
        scraped.append(source)

    assessment = assess_research_tier(
        manufacturer=manufacturer,
        mpn=mpn,
        family_hint=family_hint,
        sources=[(s.markdown, s.record.tier, s.record.url, s.record.scrape_ok) for s in scraped],
    )
    return _finalize_bundle(
        scraped, manufacturer=manufacturer, mpn=mpn, family_hint=family_hint, assessment=assessment
    )


async def _scrape_candidate(
    candidate: RankedCandidate,
    *,
    firecrawl: FirecrawlClient,
    manufacturer: str,
    mpn: str,
    family_hint: str,
    authorized_domains: frozenset[str],
) -> ScrapedSource:
    settings = get_settings()
    url = candidate.result.url
    record = SourceRecord(
        url=url,
        title=candidate.result.title,
        tier=candidate.tier,
        domain=candidate.result.domain,
        exact_mpn_found=False,
        exact_manufacturer_match=False,
        family_match_found=False,
        competitor_match_found=False,
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
        SOURCE_TIER_COMPETITOR,
    }
    if is_pdf_url(url) and candidate.tier not in trusted_pdf_tiers:
        record.error = (
            "Skipped low-confidence PDF source (likely irrelevant archive/document). "
            "Only manufacturer, datasheet, authorized-distributor, and competitor PDFs are scraped."
        )
        logger.info("Skipping PDF scrape for %s (%s tier)", url, candidate.tier)
        return ScrapedSource(record=record, markdown="")

    if is_pdf_url(url) and candidate.tier != SOURCE_TIER_COMPETITOR and not pdf_host_is_trusted(
        url,
        manufacturer=manufacturer,
        authorized_domains=authorized_domains,
    ):
        record.error = (
            "Skipped PDF on untrusted host (manufacturer name in title/path only). "
            "PDFs are only scraped from manufacturer or authorized-distributor domains."
        )
        logger.info("Skipping untrusted-host PDF %s", url)
        return ScrapedSource(record=record, markdown="")

    if is_pdf_url(url) and settings.research_pdf_max_bytes > 0:
        byte_size = await remote_pdf_byte_size(url)
        if byte_size is not None and byte_size > settings.research_pdf_max_bytes:
            mb = byte_size / (1024 * 1024)
            cap_mb = settings.research_pdf_max_bytes / (1024 * 1024)
            record.error = (
                f"Skipped oversized PDF ({mb:.1f} MB; limit {cap_mb:.1f} MB). "
                "Large multi-page PDFs are excluded to control token usage."
            )
            logger.info("Skipping oversized PDF %s (%s bytes)", url, byte_size)
            return ScrapedSource(record=record, markdown="")

    try:
        response = await firecrawl.scrape(url)
        log_external_cost(
            service="firecrawl", phase="research", units=1, unit_cost_usd=settings.firecrawl_cost_usd
        )
        markdown = cap_scraped_markdown(FirecrawlClient.extract_markdown(response), url, settings)
        record.scrape_ok = bool(markdown)
        record.exact_manufacturer_match = source_supports_exact_manufacturer_match(
            markdown,
            manufacturer=manufacturer,
            mpn=mpn,
            tier=candidate.tier,
        )
        record.exact_mpn_found = record.exact_manufacturer_match or source_supports_product_match(
            markdown,
            manufacturer=manufacturer,
            mpn=mpn,
            tier=candidate.tier,
        )
        record.family_match_found = bool(
            family_hint
            and source_supports_family_match(
                markdown,
                manufacturer=manufacturer,
                family_hint=family_hint,
                tier=candidate.tier,
            )
        )
        record.competitor_match_found = source_supports_competitor_match(markdown, tier=candidate.tier)
        return ScrapedSource(record=record, markdown=markdown)
    except FirecrawlError as exc:
        record.error = str(exc)
        logger.warning("Firecrawl failed for %s: %s", url, exc)
        return ScrapedSource(record=record, markdown="")
