from __future__ import annotations

from app.adapters.firecrawl_client import _scrape_payload, is_pdf_url


def test_is_pdf_url() -> None:
    assert is_pdf_url("https://example.com/spec.pdf")
    assert not is_pdf_url("https://example.com/product")


def test_scrape_payload_includes_timeout() -> None:
    payload = _scrape_payload("https://example.com/spec.pdf", None, None, 300_000)
    assert payload["timeout"] == 300_000
