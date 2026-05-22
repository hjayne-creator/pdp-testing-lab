from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.research.ranker import MATCH_TRUSTED_TIERS

# Cap how much of a huge page we scan for coincidental MPN hits.
_MATCH_SCAN_LIMIT = 100_000
_COLOCATE_WINDOW = 800


def normalize_mpn(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value or "").upper()


def normalize_manufacturer(value: str) -> str:
    s = re.sub(r"[^\w\s]", " ", value or "", flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip().lower()


def normalize_product_inputs(manufacturer: str, mpn: str) -> tuple[str, str]:
    """Strip a duplicated MPN from the manufacturer field when users paste both together."""
    mfg = (manufacturer or "").strip()
    part = (mpn or "").strip()
    if not part:
        return mfg, part

    pattern = re.compile(rf"\b{re.escape(part)}\b", flags=re.IGNORECASE)
    mfg = pattern.sub("", mfg)
    mfg = re.sub(r"\s+", " ", mfg).strip(" ,;-")
    return mfg, part


def manufacturer_matches(source_text: str, manufacturer: str, *, threshold: float = 0.72) -> bool:
    norm_source = normalize_manufacturer(source_text)
    norm_target = normalize_manufacturer(manufacturer)
    if not norm_target:
        return False
    if norm_target in norm_source:
        return True
    tokens = [t for t in norm_target.split() if len(t) >= 3]
    if tokens and sum(1 for t in tokens if t in norm_source) >= max(1, len(tokens) - 1):
        return True
    return SequenceMatcher(None, norm_target, norm_source).ratio() >= threshold


def exact_mpn_in_text(text: str, mpn: str) -> bool:
    target = normalize_mpn(mpn)
    if not target:
        return False
    compact = normalize_mpn(text[:_MATCH_SCAN_LIMIT])
    if target in compact:
        return True
    pattern = re.escape(mpn.strip())
    if pattern and re.search(pattern, text[:_MATCH_SCAN_LIMIT], flags=re.IGNORECASE):
        return True
    return False


def mpn_and_manufacturer_cooccur(text: str, manufacturer: str, mpn: str) -> bool:
    """Require MPN and manufacturer to appear near each other in the same source."""
    if not exact_mpn_in_text(text, mpn):
        return False

    scan = text[:_MATCH_SCAN_LIMIT]
    pattern = re.compile(re.escape(mpn.strip()), flags=re.IGNORECASE)
    for match in pattern.finditer(scan):
        start = max(0, match.start() - _COLOCATE_WINDOW)
        end = min(len(scan), match.end() + _COLOCATE_WINDOW)
        if manufacturer_matches(scan[start:end], manufacturer):
            return True
    return False


def source_supports_product_match(
    text: str,
    *,
    manufacturer: str,
    mpn: str,
    tier: str,
) -> bool:
    if tier not in MATCH_TRUSTED_TIERS:
        return False
    return mpn_and_manufacturer_cooccur(text, manufacturer, mpn)


@dataclass
class MatchAssessment:
    verified: bool
    reason: str
    manufacturer_match: bool
    mpn_match: bool
    trusted_source_count: int = 0


def assess_product_match(
    *,
    manufacturer: str,
    mpn: str,
    sources: list[tuple[str, str, str]],
) -> MatchAssessment:
    """Assess match using per-source (text, tier, url) tuples from trusted sources only."""
    trusted_hits = 0
    any_mpn = False
    any_manufacturer = False

    for text, tier, _url in sources:
        if not text or tier not in MATCH_TRUSTED_TIERS:
            continue
        if exact_mpn_in_text(text, mpn):
            any_mpn = True
        if manufacturer_matches(text, manufacturer):
            any_manufacturer = True
        if source_supports_product_match(text, manufacturer=manufacturer, mpn=mpn, tier=tier):
            trusted_hits += 1

    if trusted_hits >= 1:
        return MatchAssessment(
            True,
            "Exact MPN and manufacturer evidence found on a trusted source.",
            any_manufacturer,
            any_mpn,
            trusted_hits,
        )
    if any_mpn and not any_manufacturer:
        return MatchAssessment(
            False,
            "Exact MPN found but manufacturer name could not be verified in sources.",
            any_manufacturer,
            any_mpn,
            trusted_hits,
        )
    if any_mpn:
        return MatchAssessment(
            False,
            "MPN appeared in sources but not with the manufacturer on a trusted product page.",
            any_manufacturer,
            any_mpn,
            trusted_hits,
        )
    return MatchAssessment(
        False,
        "Exact product match could not be verified.",
        any_manufacturer,
        any_mpn,
        trusted_hits,
    )
