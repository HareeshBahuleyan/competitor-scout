from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Iterable
from urllib.parse import SplitResult, urlsplit, urlunsplit

import tldextract

type Resolver = Callable[[str, int], Awaitable[Iterable[str]]]

_PUBLIC_SUFFIX_EXTRACTOR = tldextract.TLDExtract(
    suffix_list_urls=(),
    fallback_to_snapshot=True,
    include_psl_private_domains=True,
)


class UnsafeSourceUrl(ValueError):
    """Raised when a source URL could reach an untrusted network location."""


async def _system_resolver(hostname: str, port: int) -> tuple[str, ...]:
    infos = await asyncio.get_running_loop().getaddrinfo(
        hostname,
        port,
        type=socket.SOCK_STREAM,
    )
    return tuple({info[4][0] for info in infos})


def _parse_url(value: str) -> SplitResult:
    stripped = value.strip()
    if not stripped or "\\" in stripped or any(character.isspace() for character in stripped):
        raise UnsafeSourceUrl("source URL is malformed")
    try:
        return urlsplit(stripped)
    except ValueError as error:
        raise UnsafeSourceUrl("source URL is malformed") from error


def _normalized_hostname(hostname: str) -> str:
    unqualified = hostname.rstrip(".")
    if not unqualified:
        raise UnsafeSourceUrl("source URL has no hostname")
    try:
        return unqualified.encode("idna").decode("ascii").casefold()
    except UnicodeError as error:
        raise UnsafeSourceUrl("source URL hostname is invalid") from error


def _ip_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return address.is_global and not (
        address.is_link_local
        or address.is_loopback
        or address.is_multicast
        or address.is_private
        or address.is_reserved
        or address.is_unspecified
    )


def _canonical_host(
    hostname: str,
) -> tuple[str, ipaddress.IPv4Address | ipaddress.IPv6Address | None]:
    normalized = _normalized_hostname(hostname)
    address = _ip_address(normalized)
    if address is not None:
        return address.compressed, address
    return normalized, None


async def validate_public_https_url(
    value: str,
    *,
    resolver: Resolver | None = None,
    resolution_timeout: float = 5.0,
) -> str:
    """Validate and canonicalize a public HTTPS URL without fetching it."""

    parsed = _parse_url(value)
    if parsed.scheme.casefold() != "https":
        raise UnsafeSourceUrl("source URL must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeSourceUrl("source URL must not contain credentials")
    if parsed.hostname is None:
        raise UnsafeSourceUrl("source URL has no hostname")
    try:
        port = parsed.port
    except ValueError as error:
        raise UnsafeSourceUrl("source URL port is invalid") from error
    if port not in (None, 443):
        raise UnsafeSourceUrl("source URL must use the standard HTTPS port")

    hostname, literal_address = _canonical_host(parsed.hostname)
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise UnsafeSourceUrl("source URL hostname is not public")

    if literal_address is not None:
        if not _is_public_address(literal_address):
            raise UnsafeSourceUrl("source URL hostname is not public")
    else:
        resolve = resolver or _system_resolver
        try:
            resolved_values = await asyncio.wait_for(
                resolve(hostname, 443),
                timeout=resolution_timeout,
            )
            addresses = tuple(resolved_values)
        except (OSError, TimeoutError, TypeError, ValueError) as error:
            raise UnsafeSourceUrl("source URL hostname could not be resolved") from error
        if not addresses:
            raise UnsafeSourceUrl("source URL hostname did not resolve")
        for value in addresses:
            address = _ip_address(value)
            if address is None or not _is_public_address(address):
                raise UnsafeSourceUrl(
                    "source URL hostname does not resolve only to public addresses"
                )

    canonical_netloc = (
        f"[{hostname}]" if literal_address and literal_address.version == 6 else hostname
    )
    return urlunsplit(("https", canonical_netloc, parsed.path, "", ""))


def _hostname_from_domain_or_url(value: str) -> str | None:
    stripped = value.strip()
    if not stripped:
        return None
    candidate = stripped if "://" in stripped else f"//{stripped}"
    try:
        parsed = urlsplit(candidate)
        if parsed.hostname is None or parsed.username is not None or parsed.password is not None:
            return None
        hostname, _address = _canonical_host(parsed.hostname)
    except (UnsafeSourceUrl, ValueError):
        return None
    return hostname


def _registrable_domain(hostname: str) -> str | None:
    if _ip_address(hostname) is not None:
        return None
    extracted = _PUBLIC_SUFFIX_EXTRACTOR(hostname)
    return extracted.top_domain_under_public_suffix or None


def same_registrable_domain(source_url: str, competitor_domain: str) -> bool:
    """Return whether a source is within the competitor's registrable-domain scope."""

    source_hostname = _hostname_from_domain_or_url(source_url)
    competitor_hostname = _hostname_from_domain_or_url(competitor_domain)
    if source_hostname is None or competitor_hostname is None:
        return False

    source_address = _ip_address(source_hostname)
    competitor_address = _ip_address(competitor_hostname)
    if source_address is not None or competitor_address is not None:
        return source_address is not None and source_address == competitor_address

    competitor_registrable = _registrable_domain(competitor_hostname)
    if competitor_registrable is not None:
        return _registrable_domain(source_hostname) == competitor_registrable

    return source_hostname == competitor_hostname or source_hostname.endswith(
        f".{competitor_hostname}"
    )
