import asyncio
from collections.abc import Iterable

import pytest

from competitor_scout.security import urls as url_security
from competitor_scout.security.urls import (
    UnsafeSourceUrl,
    same_registrable_domain,
    validate_public_https_url,
)


class StaticResolver:
    def __init__(self, addresses: Iterable[str]) -> None:
        self.addresses = tuple(addresses)
        self.calls: list[tuple[str, int]] = []

    async def __call__(self, hostname: str, port: int) -> tuple[str, ...]:
        self.calls.append((hostname, port))
        return self.addresses


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://example.com/a path",
        "https://example.com\\admin",
        "https://[::1",
        "https:///missing-host",
        "https://example.com:not-a-port/",
    ],
)
async def test_malformed_urls_are_rejected_before_resolution(url: str) -> None:
    resolver = StaticResolver(["93.184.216.34"])

    with pytest.raises(UnsafeSourceUrl):
        await validate_public_https_url(url, resolver=resolver)

    assert resolver.calls == []


async def test_default_resolver_returns_unique_socket_addresses(monkeypatch) -> None:
    class FakeLoop:
        async def getaddrinfo(self, hostname: str, port: int, *, type: int):
            assert (hostname, port, type) == ("example.com", 443, url_security.socket.SOCK_STREAM)
            return [
                (None, None, None, None, ("93.184.216.34", port)),
                (None, None, None, None, ("93.184.216.34", port)),
                (None, None, None, None, ("2606:2800:220:1::1", port, 0, 0)),
            ]

    monkeypatch.setattr(url_security.asyncio, "get_running_loop", lambda: FakeLoop())

    assert set(await url_security._system_resolver("example.com", 443)) == {
        "93.184.216.34",
        "2606:2800:220:1::1",
    }


def test_domain_scope_rejects_empty_malformed_and_credentialed_values() -> None:
    assert not same_registrable_domain("", "example.com")
    assert not same_registrable_domain("https://user@example.com/", "example.com")
    assert not same_registrable_domain("https://[::1", "example.com")


def test_domain_scope_compares_ip_literals_exactly() -> None:
    assert same_registrable_domain("https://93.184.216.34/path", "93.184.216.34")
    assert not same_registrable_domain("https://93.184.216.34/", "93.184.216.35")


def test_invalid_hostname_and_ip_have_no_registrable_domain() -> None:
    with pytest.raises(UnsafeSourceUrl):
        url_security._normalized_hostname(".")
    with pytest.raises(UnsafeSourceUrl):
        url_security._normalized_hostname("\ud800.example")
    assert url_security._registrable_domain("93.184.216.34") is None


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/pricing",
        "ftp://example.com/pricing",
        "//example.com/pricing",
    ],
)
async def test_only_https_urls_are_allowed(url: str) -> None:
    with pytest.raises(UnsafeSourceUrl, match="HTTPS"):
        await validate_public_https_url(url, resolver=StaticResolver(["93.184.216.34"]))


@pytest.mark.parametrize(
    "url",
    [
        "https://user@example.com/pricing",
        "https://user:password@example.com/pricing",
        "https://example.com:8443/pricing",
    ],
)
async def test_credentials_and_nonstandard_ports_are_rejected(url: str) -> None:
    with pytest.raises(UnsafeSourceUrl):
        await validate_public_https_url(url, resolver=StaticResolver(["93.184.216.34"]))


@pytest.mark.parametrize(
    "hostname",
    [
        "localhost",
        "api.localhost",
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "224.0.0.1",
        "240.0.0.1",
        "0.0.0.0",
        "[::1]",
        "[fe80::1]",
        "[ff02::1]",
        "[::ffff:127.0.0.1]",
    ],
)
async def test_local_and_nonpublic_literal_hosts_are_rejected(hostname: str) -> None:
    resolver = StaticResolver(["93.184.216.34"])

    with pytest.raises(UnsafeSourceUrl, match="public"):
        await validate_public_https_url(f"https://{hostname}/", resolver=resolver)

    assert resolver.calls == []


@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        ["10.0.0.1"],
        ["169.254.169.254"],
        ["224.0.0.1"],
        ["240.0.0.1"],
        ["::1"],
        ["fe80::1"],
        ["ff02::1"],
        ["93.184.216.34", "10.0.0.1"],
    ],
)
async def test_any_nonpublic_dns_answer_rejects_the_url(addresses: list[str]) -> None:
    with pytest.raises(UnsafeSourceUrl, match="public"):
        await validate_public_https_url(
            "https://example.com/pricing",
            resolver=StaticResolver(addresses),
        )


async def test_empty_dns_answer_is_rejected() -> None:
    with pytest.raises(UnsafeSourceUrl, match="resolve"):
        await validate_public_https_url(
            "https://example.com/pricing",
            resolver=StaticResolver([]),
        )


async def test_url_is_canonicalized_after_validation() -> None:
    resolver = StaticResolver(["93.184.216.34"])

    normalized = await validate_public_https_url(
        "  HTTPS://ExAmPle.COM.:443/pricing?campaign=ignored#plans  ",
        resolver=resolver,
    )

    assert normalized == "https://example.com/pricing"
    assert resolver.calls == [("example.com", 443)]


async def test_unicode_hostname_is_resolved_and_returned_as_idna() -> None:
    resolver = StaticResolver(["93.184.216.34"])

    normalized = await validate_public_https_url(
        "https://BÜCHER.example/pricing",
        resolver=resolver,
    )

    assert normalized == "https://xn--bcher-kva.example/pricing"
    assert resolver.calls == [("xn--bcher-kva.example", 443)]


async def test_public_ipv6_literal_is_canonicalized_without_dns() -> None:
    resolver = StaticResolver([])

    normalized = await validate_public_https_url(
        "https://[2606:4700:4700::1111]:443/dns-query?ignored=yes",
        resolver=resolver,
    )

    assert normalized == "https://[2606:4700:4700::1111]/dns-query"
    assert resolver.calls == []


async def test_resolver_error_is_reported_as_an_unsafe_url() -> None:
    async def failing_resolver(_hostname: str, _port: int) -> tuple[str, ...]:
        raise OSError("resolver details must not escape")

    with pytest.raises(UnsafeSourceUrl, match="resolve") as error:
        await validate_public_https_url("https://example.com/", resolver=failing_resolver)

    assert "resolver details" not in str(error.value)


async def test_resolver_timeout_is_bounded_and_reported_as_an_unsafe_url() -> None:
    async def hanging_resolver(_hostname: str, _port: int) -> tuple[str, ...]:
        await asyncio.Event().wait()
        return ()

    with pytest.raises(UnsafeSourceUrl, match="resolve"):
        await validate_public_https_url(
            "https://example.com/",
            resolver=hanging_resolver,
            resolution_timeout=0.001,
        )


async def test_injected_resolver_makes_resolution_deterministic() -> None:
    resolver = StaticResolver(["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"])

    assert (
        await validate_public_https_url("https://example.com/docs", resolver=resolver)
        == "https://example.com/docs"
    )
    assert resolver.calls == [("example.com", 443)]


@pytest.mark.parametrize(
    ("source", "competitor"),
    [
        ("https://acme.co.uk/pricing", "acme.co.uk"),
        ("https://www.acme.co.uk/pricing", "acme.co.uk"),
        ("https://docs.eu.acme.co.uk/", "https://app.acme.co.uk"),
        ("https://xn--bcher-kva.example/", "bücher.example"),
        ("https://docs.acme.test/", "acme.test"),
        ("https://docs.team.github.io/", "team.github.io"),
    ],
)
def test_same_registrable_domain_accepts_the_domain_and_its_subdomains(
    source: str,
    competitor: str,
) -> None:
    assert same_registrable_domain(source, competitor)


@pytest.mark.parametrize(
    ("source", "competitor"),
    [
        ("https://acme.co.uk.evil.com/", "acme.co.uk"),
        ("https://acme-example.com/", "acme.example.com"),
        ("https://evilacme.co.uk/", "acme.co.uk"),
        ("https://acme.co.uk.evil.test/", "acme.co.uk"),
        ("https://attacker.github.io/", "team.github.io"),
        ("https://attacker.test/", "acme.test"),
    ],
)
def test_same_registrable_domain_rejects_deceptive_or_sibling_domains(
    source: str,
    competitor: str,
) -> None:
    assert not same_registrable_domain(source, competitor)
