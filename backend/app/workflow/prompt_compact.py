from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_TRUNC_SUFFIX = "\n...[truncated for LLM context]"


def _truncate_str(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    keep = max_chars - len(_TRUNC_SUFFIX)
    if keep <= 0:
        return _TRUNC_SUFFIX.strip()
    return value[:keep] + _TRUNC_SUFFIX


def style_guide_for_llm(text: str | None, max_chars: int = 60_000) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    logger.warning("prompt_compact: truncating style guide %s -> %s chars", len(text), max_chars)
    return _truncate_str(text, max_chars)
