import pytest

from competitor_scout.services.competitors import (
    CompetitorLimitReached,
    ensure_competitor_capacity,
    normalize_primary_domain,
)


def test_tenth_competitor_is_allowed() -> None:
    ensure_competitor_capacity(active_count=9, limit=10)


def test_eleventh_competitor_is_rejected() -> None:
    with pytest.raises(CompetitorLimitReached):
        ensure_competitor_capacity(active_count=10, limit=10)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Example.COM", "example.com"),
        ("example.com.", "example.com"),
        ("https://WWW.Example.COM/pricing?ref=nav", "www.example.com"),
        ("http://example.com:80", "example.com"),
        ("https://bücher.example:443/", "xn--bcher-kva.example"),
    ],
)
def test_normalize_primary_domain_returns_canonical_hostname(
    value: str,
    expected: str,
) -> None:
    assert normalize_primary_domain(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "localhost",
        "127.0.0.1",
        "https://user:pass@example.com",
        "https://example.com:8443",
        "example.com:443",
        "ftp://example.com",
        "bad_label.example.com",
        "single-label",
        "https://[::1]/",
    ],
)
def test_normalize_primary_domain_rejects_non_domain_or_unsafe_input(value: str) -> None:
    with pytest.raises(ValueError, match="domain"):
        normalize_primary_domain(value)
