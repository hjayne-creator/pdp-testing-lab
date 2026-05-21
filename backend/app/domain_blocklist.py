"""Shared normalization for blocked domains (SerpAPI + source filtering)."""
from __future__ import annotations

from typing import Iterable
from urllib.parse import urlparse

DEFAULT_BLOCKED_DOMAIN_SEEDS: tuple[str, ...] = (
    "amazon.com",
    "ebay.com",
    "walmart.com",
    "alibaba.com",
    "youtube.com",
    "reddit.com",
    "quora.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "pinterest.com",
    "twitter.com",
    "x.com",
    "wikipedia.org",
)

DEFAULT_AUTHORIZED_DISTRIBUTOR_SEEDS: tuple[str, ...] = (
    "digikey.com",
    "mouser.com",
    "arrow.com",
    "newark.com",
    "farnell.com",
    "element14.com",
    "rs-online.com",
    "jameco.com",
    "alliedelec.com",
    "grainger.com",
)


def _normalize_domain(host: str) -> str:
    h = host.lower().strip()
    return h[4:] if h.startswith("www.") else h


def normalize_blocked_domain_key(raw: str) -> str:
    s = raw.strip().lower()
    if not s:
        return ""
    if "://" in s:
        host = urlparse(s).netloc
        return _normalize_domain(host) if host else ""
    return _normalize_domain(s)


def merged_blocked_keys(global_domains: Iterable[str], additional: Iterable[str]) -> frozenset[str]:
    keys: set[str] = set()
    for d in global_domains:
        k = normalize_blocked_domain_key(d)
        if k:
            keys.add(k)
    for d in additional:
        k = normalize_blocked_domain_key(d)
        if k:
            keys.add(k)
    return frozenset(keys)


def normalized_host_matches_blocked(host: str, blocked_keys: frozenset[str]) -> bool:
    h = host.lower().strip(".")
    if not h:
        return False
    for blocked in blocked_keys:
        if h == blocked or h.endswith(f".{blocked}"):
            return True
    return False


def normalized_host_matches_allowlist(host: str, allowlist_keys: frozenset[str]) -> bool:
    return normalized_host_matches_blocked(host, allowlist_keys)
