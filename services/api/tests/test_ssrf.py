"""Unit tests for the SSRF guard. No real network access."""

from __future__ import annotations

from cyberai.modules.research.ssrf import SSRFGuard, is_blocked_url


def _guard(resolver: dict[str, list[str]]) -> SSRFGuard:
    return SSRFGuard(resolver=lambda host: resolver.get(host, ["93.184.216.34"]))


def test_allows_public_url() -> None:
    guard = _guard({"example.com": ["93.184.216.34"]})
    assert guard.validate("https://example.com/page")


def test_rejects_non_http_scheme() -> None:
    guard = _guard({})
    assert not guard.validate("file:///etc/passwd")
    assert not guard.validate("ftp://example.com/x")


def test_rejects_loopback_hostnames() -> None:
    guard = _guard({})
    assert not guard.validate("http://localhost:8001/admin")
    assert not guard.validate("http://127.0.0.1/")
    assert not guard.validate("http://[::1]/")


def test_rejects_private_ip_literals() -> None:
    guard = _guard({})
    assert not guard.validate("http://10.0.0.1/")
    assert not guard.validate("http://192.168.1.1/")
    assert not guard.validate("http://172.16.0.5/")
    assert not guard.validate("http://169.254.169.254/latest/meta-data/")


def test_rejects_dns_resolving_to_private_ip() -> None:
    guard = _guard({"evil.internal": ["10.0.0.7"]})
    assert not guard.validate("http://evil.internal/x")


def test_rejects_metadata_endpoint_hostname() -> None:
    guard = _guard({})
    assert not guard.validate("http://metadata.google.internal/")


def test_rejects_blocked_tlds() -> None:
    guard = _guard({})
    assert not guard.validate("http://myhost.local/")
    assert not guard.validate("http://corp.internal/")


def test_allows_public_ipv6() -> None:
    guard = _guard({"example.org": ["2606:2800:220:1:248:1893:25c8:1946"]})
    assert guard.validate("https://example.org/thing")


def test_module_level_helper() -> None:
    assert is_blocked_url("http://127.0.0.1/x")
    assert is_blocked_url("http://169.254.169.254/")
    assert not is_blocked_url("https://nvd.nist.gov/vuln/detail/CVE-2024-3094")
