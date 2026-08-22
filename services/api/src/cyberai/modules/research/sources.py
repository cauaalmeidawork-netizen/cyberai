"""Source quality scoring, deduplication and canonicalization."""

from __future__ import annotations

from urllib.parse import urlparse

from cyberai.modules.research.types import Source, SourceType

#: Domains given privileged authority treatment for security topics.
_AUTHORITATIVE_DOMAINS = frozenset(
    {
        "nvd.nist.gov",
        "nist.gov",
        "cisa.gov",
        "osv.dev",
        "github.com",
        "github.dev",
        "kb.cert.org",
        "cert.org",
        "kernel.org",
        "mitre.org",
        "cve.org",
        "first.org",
        "cloudflare.com",
        "microsoft.com",
        "learn.microsoft.com",
        "apple.com",
        "google.com",
        "chromium.org",
        "mozilla.org",
        "apache.org",
        "redhat.com",
        "canonical.com",
        "ubuntu.com",
        "debian.org",
        "openssl.org",
        "rust-lang.org",
        "python.org",
        "go.dev",
    }
)

_AUTHORITATIVE_BY_TYPE = {
    SourceType.AUTHORITATIVE: 1.0,
    SourceType.VENDOR: 0.95,
    SourceType.UPSTREAM: 0.9,
    SourceType.TECHNICAL: 0.7,
    SourceType.WEB: 0.5,
}

#: Domains that are almost never worth citing (link farms, aggregators).
_LOW_QUALITY_DOMAINS = frozenset(
    {
        "pinterest.com",
        "reddit.com",
        "quora.com",
        "tiktok.com",
        "instagram.com",
        "facebook.com",
        "youtube.com",
        "twitter.com",
        "x.com",
        "medium.com",
        "linkedin.com",
        "amazon.com",
        "ebay.com",
    }
)


def canonicalize_url(url: str) -> str:
    """Remove tracking fragments and normalize a URL for deduplication."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{netloc}{path}"


def domain_of(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def authority_score(source: Source) -> float:
    base = _AUTHORITATIVE_BY_TYPE.get(source.source_type, 0.5)
    if source.domain in _AUTHORITATIVE_DOMAINS:
        base = max(base, 0.9)
    if source.domain in _LOW_QUALITY_DOMAINS:
        base = min(base, 0.35)
    if source.snippet:
        base = min(1.0, base + 0.02)
    return round(base, 4)


def relevance_score(source: Source, query: str) -> float:
    """A cheap lexical relevance signal for ranking and filtering."""
    terms = [term for term in query.lower().split() if len(term) > 2]
    if not terms:
        return 0.5
    haystack = f"{source.title} {source.snippet}".lower()
    hits = sum(1 for term in terms if term in haystack)
    return round(hits / len(terms), 4)


def deduplicate(sources: list[Source]) -> list[Source]:
    seen: set[str] = set()
    result: list[Source] = []
    for source in sources:
        key = canonicalize_url(source.url)
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result


def rank_sources(sources: list[Source], query: str, limit: int) -> list[Source]:
    """Score, filter and order sources, returning at most ``limit``."""
    deduped = deduplicate(sources)
    scored: list[Source] = []
    for source in deduped:
        authority = authority_score(source)
        relevance = relevance_score(source, query)
        if authority < 0.4 and relevance < 0.2:
            continue
        scored.append(
            Source(
                url=source.url,
                title=source.title,
                domain=source.domain,
                source_type=source.source_type,
                snippet=source.snippet,
                published_at=source.published_at,
                provider=source.provider,
                authority_score=authority,
                relevance_score=relevance,
            )
        )
    scored.sort(key=lambda source: source.score, reverse=True)
    return scored[:limit]
