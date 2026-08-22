"""Unit and integration tests for the research subsystem (no internet)."""

from __future__ import annotations

import pytest

from cyberai.core.config import ResearchSettings
from cyberai.modules.research import (
    ResearchDecider,
    ResearchDecision,
    ResearchOrchestrator,
    ResearchPlan,
)
from cyberai.modules.research.providers.base import SearchProvider
from cyberai.modules.research.sources import (
    authority_score,
    canonicalize_url,
    deduplicate,
    rank_sources,
)
from cyberai.modules.research.types import Source, SourceType


def _source(url: str, snippet: str = "", source_type: SourceType = SourceType.WEB) -> Source:
    from cyberai.modules.research.sources import domain_of

    return Source(
        url=url,
        title=url,
        domain=domain_of(url),
        source_type=source_type,
        snippet=snippet,
        provider="test",
    )


class _FakeProvider(SearchProvider):
    def __init__(self, name: str, results: list[Source]) -> None:
        self.name = name
        self._results = results

    @property
    def is_configured(self) -> bool:
        return True

    async def search(self, query: str) -> list[Source]:
        return self._results


# --- Research decision -------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("como funciona o nmap -sV?", ResearchDecision.NONE),
        ("explique o que é uma variável", ResearchDecision.NONE),
        ("CVE-2024-3094", ResearchDecision.QUICK),
        ("qual é a versão atual do Kubernetes?", ResearchDecision.QUICK),
        ("pesquise as últimas notícias sobre o kernel linux", ResearchDecision.QUICK),
        ("compare NVD com CISA KEV em profundidade", ResearchDecision.DEEP),
    ],
)
def test_research_decision(query: str, expected: ResearchDecision) -> None:
    assert ResearchDecider().decide(query).decision is expected


def test_cve_decision_extracts_cve_query() -> None:
    plan = ResearchDecider().decide("o que é CVE-2024-3094?")
    assert plan.decision is ResearchDecision.QUICK
    assert plan.queries[0] == "CVE-2024-3094"


# --- Source ranking ----------------------------------------------------------


def test_canonicalize_url_strips_tracking_and_www() -> None:
    assert canonicalize_url("https://www.example.com/path/?utm_source=x") == (
        "https://example.com/path"
    )


def test_deduplicate_removes_duplicates() -> None:
    sources = [
        _source("https://example.com/a"),
        _source("https://www.example.com/a"),
        _source("https://example.com/b"),
    ]
    assert len(deduplicate(sources)) == 2


def test_authority_prefers_authoritative_domains() -> None:
    assert authority_score(_source("https://cisa.gov/x", source_type=SourceType.AUTHORITATIVE)) > (
        authority_score(_source("https://randomblog.example/x"))
    )


def test_rank_sources_orders_and_limits() -> None:
    sources = [
        _source("https://low.example/a", "irrelevant"),
        _source("https://cisa.gov/a", "CVE-2024-3094 exploited", SourceType.AUTHORITATIVE),
        _source("https://nvd.nist.gov/a", "CVE-2024-3094 xz backdoor", SourceType.AUTHORITATIVE),
    ]
    ranked = rank_sources(sources, "CVE-2024-3094", limit=2)
    assert len(ranked) <= 2
    assert ranked[0].domain in {"nvd.nist.gov", "cisa.gov"}


# --- Orchestrator (fake providers, no network) --------------------------------


@pytest.mark.asyncio
async def test_orchestrator_returns_citations_in_order() -> None:
    settings = ResearchSettings(enabled=True, max_sources=3)
    orchestrator = ResearchOrchestrator(
        settings,
        providers=[
            _FakeProvider(
                "fake",
                [
                    _source("https://a.example/1", "CVE-2024-3094 detail"),
                    _source("https://b.example/2", "CVE-2024-3094 analysis"),
                ],
            )
        ],
        cyber_providers=[],
    )
    plan = ResearchPlan(ResearchDecision.QUICK, ("CVE-2024-3094",))
    result = await orchestrator.run(plan)

    assert result.count == 2
    assert [c.index for c in result.citations] == [1, 2]


@pytest.mark.asyncio
async def test_orchestrator_skips_when_disabled() -> None:
    settings = ResearchSettings(enabled=False)
    orchestrator = ResearchOrchestrator(settings, providers=[])
    assert orchestrator.decide("CVE-2024-3094").is_empty
    result = await orchestrator.run(ResearchPlan(ResearchDecision.QUICK, ("x",)))
    assert result.count == 0


@pytest.mark.asyncio
async def test_orchestrator_handles_provider_failure() -> None:
    class _FailingProvider(SearchProvider):
        name = "failing"

        @property
        def is_configured(self) -> bool:
            return True

        async def search(self, query: str) -> list[Source]:
            raise RuntimeError("boom")

    settings = ResearchSettings(enabled=True, max_sources=3)
    orchestrator = ResearchOrchestrator(
        settings,
        providers=[_FailingProvider()],
        cyber_providers=[],
    )
    result = await orchestrator.run(ResearchPlan(ResearchDecision.QUICK, ("CVE-2024-3094",)))
    # Cyber providers are keyless and would hit the network; with only the
    # failing web provider configured the run must not raise and yields nothing.
    assert result.count == 0
