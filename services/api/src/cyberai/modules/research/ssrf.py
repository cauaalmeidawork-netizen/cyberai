"""Server-side request forgery (SSRF) protection for web retrieval.

Every URL the research subsystem fetches must pass through this guard. The guard
resolves DNS *before* any request and rejects anything that resolves to a
private, loopback, link-local or otherwise reserved address, as well as a small
allowlist of dangerous hostnames and non-HTTP(S) schemes.

The resolver is injectable so unit tests never touch the real network.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable
from urllib.parse import urlparse

Resolver = Callable[[str], list[str]]

#: Hosts that must never be reached regardless of DNS resolution.
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata",
        "instance-data",
        "169.254.169.254",
    }
)

#: TLDs that conventionally resolve to private networks.
_BLOCKED_TLDS = (".local", ".internal", ".lan", ".localhost", ".home", ".corp", ".intranet")

_ALLOWED_SCHEMES = frozenset({"http", "https"})

_IP_LITERAL = re.compile(r"^\[?([0-9a-fA-F:.]+)\]?$")

_MAX_URL_LENGTH = 2048


def _resolve(host: str) -> list[str]:
    addresses: set[str] = set()
    try:
        for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP):
            addresses.add(str(info[4][0]))
    except OSError:
        # Resolution failure means the fetch will fail anyway; returning an
        # empty set lets callers decide. We treat it as safe here so a DNS
        # outage surfaces as a fetch error, not an SSRF denial.
        return []
    return sorted(addresses)


def _is_private_ip(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def is_blocked_ip(ip: str) -> bool:
    """Return True when an IP address must never be fetched."""
    return _is_private_ip(ip)


class SSRFGuard:
    """Rejects URLs that resolve to non-public addresses or dangerous hosts."""

    def __init__(self, resolver: Resolver | None = None) -> None:
        self._resolver = resolver or _resolve

    def validate(self, url: str) -> bool:
        """Return True when the URL is safe to fetch, False otherwise."""
        if not url or len(url) > _MAX_URL_LENGTH:
            return False
        parsed = urlparse(url)
        if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
            return False
        host = parsed.hostname
        if not host:
            return False
        return self.validate_host(host)

    def validate_host(self, host: str) -> bool:
        lowered = host.lower().rstrip(".")
        if not lowered or lowered in _BLOCKED_HOSTNAMES:
            return False
        if lowered.endswith(_BLOCKED_TLDS):
            return False

        literal = _IP_LITERAL.match(lowered)
        if literal:
            return not _is_private_ip(literal.group(1))

        return all(not _is_private_ip(ip) for ip in self._resolver(lowered))


_default_guard = SSRFGuard()


def is_blocked_url(url: str) -> bool:
    """Convenience wrapper returning True when a URL is unsafe to fetch."""
    return not _default_guard.validate(url)
