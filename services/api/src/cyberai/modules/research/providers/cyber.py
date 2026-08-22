"""Authoritative, keyless cybersecurity sources (NVD, CISA KEV, OSV, GHSA).

These adapters query structured public feeds directly instead of relying on a
generic search engine. They require no API key, use a clearly identifiable
User-Agent, and are given privileged authority scoring in the ranker.
"""

from __future__ import annotations

import re
from typing import Any

from cyberai.core.logging import get_logger
from cyberai.modules.research.providers.base import SearchProvider
from cyberai.modules.research.providers.web import safe_get_json
from cyberai.modules.research.ssrf import SSRFGuard
from cyberai.modules.research.types import Source, SourceType

logger = get_logger(__name__)

_CVE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)


def _cve_from(query: str) -> str | None:
    match = _CVE.search(query)
    return match.group(0).upper() if match else None


class NvdCveProvider(SearchProvider):
    """NVD CVE API (no key required for low-volume access)."""

    name = "nvd"

    def __init__(self, timeout: float, guard: SSRFGuard) -> None:
        self._timeout = timeout
        self._guard = guard

    @property
    def is_configured(self) -> bool:
        return True

    async def search(self, query: str) -> list[Source]:
        cve = _cve_from(query)
        if not cve:
            return []
        data = await safe_get_json(
            "https://services.nvd.nist.gov/rest/json/cves/2.0",
            request_timeout=self._timeout,
            guard=self._guard,
            params={"cveId": cve},
        )
        if not data:
            return []
        vulnerabilities = data.get("vulnerabilities", [])
        if not vulnerabilities:
            return []
        cve_data = vulnerabilities[0].get("cve", {})
        description = ""
        for entry in cve_data.get("descriptions", []):
            if entry.get("lang") == "en":
                description = entry.get("value", "")
                break
        severity = _nvd_severity(cve_data)
        return [
            Source(
                url=f"https://nvd.nist.gov/vuln/detail/{cve}",
                title=f"{cve} — {cve_data.get('id', cve)}",
                domain="nvd.nist.gov",
                source_type=SourceType.AUTHORITATIVE,
                snippet=_join(description, severity),
                published_at=cve_data.get("published"),
                provider=self.name,
            )
        ]


class CisaKevProvider(SearchProvider):
    """CISA Known Exploited Vulnerabilities catalog."""

    name = "cisa-kev"

    _FEED_URL = (
        "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
    )

    def __init__(self, timeout: float, guard: SSRFGuard) -> None:
        self._timeout = timeout
        self._guard = guard

    @property
    def is_configured(self) -> bool:
        return True

    async def search(self, query: str) -> list[Source]:
        cve = _cve_from(query)
        if not cve:
            return []
        data = await safe_get_json(self._FEED_URL, request_timeout=self._timeout, guard=self._guard)
        if not data:
            return []
        for entry in data.get("vulnerabilities", []):
            if entry.get("cveID", "").upper() == cve:
                return [
                    Source(
                        url="https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                        title=f"{cve} — CISA Known Exploited Vulnerabilities",
                        domain="cisa.gov",
                        source_type=SourceType.AUTHORITATIVE,
                        snippet=_join(
                            entry.get("vulnerabilityName"),
                            f"Vendor: {entry.get('vendorProject')} {entry.get('product')}",
                            f"Added: {entry.get('dateAdded')}",
                            f"Action: {entry.get('requiredAction')}",
                        ),
                        published_at=entry.get("dateAdded"),
                        provider=self.name,
                    )
                ]
        return []


class OsvProvider(SearchProvider):
    """OSV.dev vulnerability database."""

    name = "osv"

    def __init__(self, timeout: float, guard: SSRFGuard) -> None:
        self._timeout = timeout
        self._guard = guard

    @property
    def is_configured(self) -> bool:
        return True

    async def search(self, query: str) -> list[Source]:
        cve = _cve_from(query)
        if not cve:
            return []
        data = await safe_get_json(
            f"https://api.osv.dev/v1/vulns/{cve}",
            request_timeout=self._timeout,
            guard=self._guard,
        )
        if not data:
            return []
        return [
            Source(
                url=f"https://osv.dev/vulnerability/{cve}",
                title=f"{cve} — {data.get('summary') or data.get('id', cve)}",
                domain="osv.dev",
                source_type=SourceType.AUTHORITATIVE,
                snippet=_join(data.get("summary"), data.get("details")),
                published_at=data.get("published"),
                provider=self.name,
            )
        ]


class GithubAdvisoryProvider(SearchProvider):
    """GitHub Global Security Advisories."""

    name = "ghsa"

    def __init__(self, timeout: float, guard: SSRFGuard) -> None:
        self._timeout = timeout
        self._guard = guard

    @property
    def is_configured(self) -> bool:
        return True

    async def search(self, query: str) -> list[Source]:
        cve = _cve_from(query)
        if not cve:
            return []
        data = await safe_get_json(
            "https://api.github.com/advisories",
            request_timeout=self._timeout,
            guard=self._guard,
            params={"cve_id": cve, "per_page": "3"},
            headers={"Accept": "application/vnd.github+json"},
        )
        if not data:
            return []
        return [
            Source(
                url=item.get("html_url", f"https://github.com/advisories/{item.get('ghsa_id')}"),
                title=f"{item.get('cve_id') or item.get('ghsa_id')} — {item.get('summary') or ''}",
                domain="github.com",
                source_type=SourceType.VENDOR,
                snippet=_join(item.get("summary"), item.get("description", "")[:1200]),
                published_at=item.get("published_at"),
                provider=self.name,
            )
            for item in data
            if isinstance(item, dict)
        ]


def build_cyber_providers(timeout: float, guard: SSRFGuard) -> list[SearchProvider]:
    """Keyless authoritative sources that are always available."""
    return [
        NvdCveProvider(timeout, guard),
        CisaKevProvider(timeout, guard),
        OsvProvider(timeout, guard),
        GithubAdvisoryProvider(timeout, guard),
    ]


def _nvd_severity(cve_data: dict[str, Any]) -> str:
    try:
        for metric_key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            metrics = cve_data.get("metrics", {}).get(metric_key) or []
            if metrics:
                base = metrics[0].get("cvssData", {}).get("baseScore")
                if base is not None:
                    return f"CVSS base score: {base}"
    except Exception:
        return ""
    return ""


def _join(*parts: str | None) -> str:
    return " ".join(part for part in parts if part).strip()
