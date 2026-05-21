from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from urllib.parse import urlparse


def normalize_mpn(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value or "").upper()


def normalize_manufacturer(value: str) -> str:
    s = re.sub(r"[^\w\s]", " ", value or "", flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip().lower()


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
    compact = normalize_mpn(text)
    if target in compact:
        return True
    # Also accept common separators in source text.
    pattern = re.escape(mpn.strip())
    if pattern and re.search(pattern, text, flags=re.IGNORECASE):
        return True
    return False


@dataclass
class MatchAssessment:
    verified: bool
    reason: str
    manufacturer_match: bool
    mpn_match: bool


def assess_product_match(
    *,
    manufacturer: str,
    mpn: str,
    texts: list[str],
) -> MatchAssessment:
    combined = "\n".join(texts)
    mpn_match = exact_mpn_in_text(combined, mpn)
    manufacturer_match = manufacturer_matches(combined, manufacturer)
    if mpn_match and manufacturer_match:
        return MatchAssessment(True, "Exact MPN and manufacturer evidence found.", manufacturer_match, mpn_match)
    if mpn_match:
        return MatchAssessment(
            False,
            "Exact MPN found but manufacturer name could not be verified in sources.",
            manufacturer_match,
            mpn_match,
        )
    return MatchAssessment(
        False,
        "Exact product match could not be verified.",
        manufacturer_match,
        mpn_match,
    )


def host_from_url(url: str) -> str:
    return (urlparse(url).hostname or "").lower()
