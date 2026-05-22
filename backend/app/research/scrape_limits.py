"""Guardrails for Firecrawl scrape size and PDF trust."""
from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from app.adapters.firecrawl_client import is_pdf_url
from app.config import Settings, get_settings
from app.domain_blocklist import normalized_host_matches_allowlist
logger = logging.getLogger(__name__)


def manufacturer_host_tokens(manufacturer: str) -> set[str]:
    return {t for t in manufacturer.lower().replace(",", " ").split() if len(t) >= 4}

_TRUNCATION_NOTICE = "\n\n[Content truncated for token limits.]"


def host_from_url(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def pdf_host_is_trusted(
    url: str,
    *,
    manufacturer: str,
    authorized_domains: frozenset[str],
) -> bool:
    """PDFs on random hosts (e.g. path-only /meritor/) are not trusted even if the title mentions the brand."""
    host = host_from_url(url)
    host_key = host[4:] if host.startswith("www.") else host
    if normalized_host_matches_allowlist(host_key, authorized_domains):
        return True
    mfg_tokens = manufacturer_host_tokens(manufacturer)
    return any(token in host_key for token in mfg_tokens)


async def remote_pdf_byte_size(url: str, *, timeout: float = 15.0) -> int | None:
    """Best-effort Content-Length via HEAD (or tiny Range GET). None if unknown."""
    headers = {"User-Agent": "PDP-Testing-Lab/1.0"}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.head(url, headers=headers)
            if response.status_code == 405 or response.status_code == 501:
                response = await client.get(url, headers={**headers, "Range": "bytes=0-0"})
            if response.status_code >= 400:
                return None
            raw = response.headers.get("content-length")
            if raw and raw.isdigit():
                return int(raw)
    except httpx.HTTPError as exc:
        logger.debug("Could not probe PDF size for %s: %s", url, exc)
    return None


def cap_scraped_markdown(markdown: str, url: str, settings: Settings | None = None) -> str:
    """Truncate scraped text before matcher / evidence assembly."""
    cfg = settings or get_settings()
    limit = cfg.research_pdf_max_chars if is_pdf_url(url) else cfg.research_page_max_chars
    if len(markdown) <= limit:
        return markdown
    return markdown[:limit] + _TRUNCATION_NOTICE


def evidence_slice(markdown: str, settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    limit = cfg.research_evidence_max_chars
    if len(markdown) <= limit:
        return markdown
    return markdown[:limit]
