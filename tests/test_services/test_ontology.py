"""Tests for OntologyService with caching and rate limiting."""

import time

import pytest

from metaseed.services.ontology import (
    CacheEntry,
    OntologySearchResult,
    OntologyService,
    OntologyTerm,
    RateLimiter,
    get_ontology_service,
    reset_ontology_service,
)


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_cache_entry_not_expired(self) -> None:
        """Cache entry is not expired before TTL."""
        entry = CacheEntry(value="test", expires_at=time.time() + 3600)
        assert not entry.is_expired()

    def test_cache_entry_expired(self) -> None:
        """Cache entry is expired after TTL."""
        entry = CacheEntry(value="test", expires_at=time.time() - 1)
        assert entry.is_expired()


class TestOntologySearchResult:
    """Tests for OntologySearchResult dataclass."""

    def test_to_dict(self) -> None:
        """Convert search result to dict."""
        result = OntologySearchResult(
            term_id="PATO:0000001",
            label="quality",
            description="A quality.",
            ontology="PATO",
            iri="http://purl.obolibrary.org/obo/PATO_0000001",
            short_form="PATO_0000001",
        )
        d = result.to_dict()
        assert d["term_id"] == "PATO:0000001"
        assert d["label"] == "quality"
        assert d["ontology"] == "PATO"


class TestOntologyTerm:
    """Tests for OntologyTerm dataclass."""

    def test_to_dict(self) -> None:
        """Convert term to dict."""
        term = OntologyTerm(
            term_id="GO:0008150",
            label="biological_process",
            description="A process.",
            ontology="GO",
            iri="http://purl.obolibrary.org/obo/GO_0008150",
            synonyms=["biological process"],
        )
        d = term.to_dict()
        assert d["term_id"] == "GO:0008150"
        assert d["synonyms"] == ["biological process"]


class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_rate_limiter_allows_requests(self) -> None:
        """Rate limiter allows requests within limit."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)

        # Should allow 5 requests without blocking
        for _ in range(5):
            limiter.acquire_sync()

        # Should have 5 requests tracked
        assert len(limiter._request_times) == 5

    @pytest.mark.asyncio
    async def test_rate_limiter_async(self) -> None:
        """Async rate limiter works."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)

        # Should allow requests
        await limiter.acquire()
        await limiter.acquire()
        await limiter.acquire()

        assert len(limiter._request_times) == 3


class TestOntologyService:
    """Tests for OntologyService."""

    def setup_method(self) -> None:
        """Reset service before each test."""
        reset_ontology_service()

    def test_service_initialization(self) -> None:
        """Service initializes with correct defaults."""
        service = OntologyService()
        assert service.cache_ttl == 600  # Default
        assert service.rate_limit == 60  # Default
        assert "ebi.ac.uk" in service.base_url

    def test_service_custom_config(self) -> None:
        """Service accepts custom configuration."""
        service = OntologyService(
            cache_ttl=120,
            rate_limit=30,
            base_url="https://custom.api/ols",
        )
        assert service.cache_ttl == 120
        assert service.rate_limit == 30
        assert service.base_url == "https://custom.api/ols"

    def test_cache_get_set(self) -> None:
        """Cache stores and retrieves values."""
        service = OntologyService()

        service._set_cached("key1", "value1")
        assert service._get_cached("key1") == "value1"
        assert service._get_cached("nonexistent") is None

    def test_cache_expiry(self) -> None:
        """Cache entries expire after TTL."""
        service = OntologyService()

        # Manually create an already-expired cache entry
        service._cache["key1"] = CacheEntry(
            value="value1",
            expires_at=time.time() - 1,  # Already expired
        )

        assert service._get_cached("key1") is None

    def test_clear_cache(self) -> None:
        """Cache can be cleared."""
        service = OntologyService()
        service._set_cached("key1", "value1")
        service._set_cached("key2", "value2")

        service.clear_cache()

        assert service._get_cached("key1") is None
        assert service._get_cached("key2") is None

    def test_cache_stats(self) -> None:
        """Cache stats are accurate."""
        service = OntologyService()

        # Add entries
        service._cache["key1"] = CacheEntry("val1", time.time() + 3600)
        service._cache["key2"] = CacheEntry("val2", time.time() - 1)  # Expired

        stats = service.get_cache_stats()
        assert stats["total_entries"] == 2
        assert stats["expired_entries"] == 1
        assert stats["valid_entries"] == 1

    def test_parse_ontology_from_term_id(self) -> None:
        """Ontology prefix is extracted from term ID."""
        service = OntologyService()

        assert service._parse_ontology_from_term_id("PATO:0000001") == "pato"
        assert service._parse_ontology_from_term_id("GO_0008150") == "go"
        assert service._parse_ontology_from_term_id("invalid") is None

    def test_construct_iri(self) -> None:
        """IRI is constructed correctly."""
        service = OntologyService()

        iri = service._construct_iri("PATO:0000001")
        assert iri == "http://purl.obolibrary.org/obo/PATO_0000001"

        iri = service._construct_iri("GO_0008150")
        assert iri == "http://purl.obolibrary.org/obo/GO_0008150"

    def test_validate_term_empty(self) -> None:
        """Empty term is considered valid."""
        service = OntologyService()

        is_valid, warning = service.validate_term_sync("")
        assert is_valid is True
        assert warning is None

    def test_validate_term_no_prefix(self) -> None:
        """Term without prefix is assumed valid."""
        service = OntologyService()

        is_valid, warning = service.validate_term_sync("nocolon")
        assert is_valid is True
        assert warning is None

    def test_validate_term_cached_valid(self) -> None:
        """Cached valid term returns True."""
        service = OntologyService()
        service._cache["term:CACHED:0001"] = CacheEntry(
            value=OntologyTerm(term_id="CACHED:0001", label="Test"),
            expires_at=time.time() + 3600,
        )

        is_valid, warning = service.validate_term_sync("CACHED:0001")
        assert is_valid is True
        assert warning is None

    def test_validate_term_cached_invalid(self) -> None:
        """Cached invalid term returns False with warning."""
        service = OntologyService()
        service._cache["term:INVALID:9999"] = CacheEntry(
            value=None,
            expires_at=time.time() + 3600,
        )

        is_valid, warning = service.validate_term_sync("INVALID:9999")
        assert is_valid is False
        assert "not found" in warning

    @pytest.mark.asyncio
    async def test_search_empty_query(self) -> None:
        """Empty search query returns empty list."""
        service = OntologyService()

        results = await service.search("")
        assert results == []

        results = await service.search("   ")
        assert results == []

    def test_search_sync_empty_query(self) -> None:
        """Sync search with empty query returns empty list."""
        service = OntologyService()

        results = service.search_sync("")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_uses_cache(self) -> None:
        """Search uses cached results."""
        service = OntologyService()

        cached_results = [OntologySearchResult(term_id="TEST:001", label="Test Term")]
        service._set_cached("search:drought:None:10:False", cached_results)

        results = await service.search("drought")
        assert len(results) == 1
        assert results[0].term_id == "TEST:001"


class TestOntologyServiceSingleton:
    """Tests for singleton pattern."""

    def setup_method(self) -> None:
        """Reset service before each test."""
        reset_ontology_service()

    def test_get_service_returns_same_instance(self) -> None:
        """get_ontology_service returns the same instance."""
        service1 = get_ontology_service()
        service2 = get_ontology_service()

        assert service1 is service2

    def test_reset_service_clears_instance(self) -> None:
        """reset_ontology_service creates new instance."""
        service1 = get_ontology_service()
        reset_ontology_service()
        service2 = get_ontology_service()

        assert service1 is not service2
