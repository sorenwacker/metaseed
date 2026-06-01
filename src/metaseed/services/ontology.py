"""Centralized ontology lookup service with caching and rate limiting.

This module provides a centralized `OntologyService` class that manages all
OLS4 API requests with caching and rate limiting. This prevents overwhelming
the external API when multiple users/tools perform lookups simultaneously.

Configuration via environment variables:
- METASEED_OLS_CACHE_TTL: Cache TTL in seconds (default: 600)
- METASEED_OLS_RATE_LIMIT: Max requests per minute (default: 60)
- METASEED_OLS_BASE_URL: OLS4 API base URL (default: https://www.ebi.ac.uk/ols4/api)

Example:
    >>> from metaseed.services import get_ontology_service
    >>> service = get_ontology_service()
    >>> results = await service.search("drought", ontology="pato")
    >>> term = await service.get_term("PATO:0000001")
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Self

import httpx

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_CACHE_TTL = 600  # 10 minutes
DEFAULT_RATE_LIMIT = 60  # requests per minute
DEFAULT_BASE_URL = "https://www.ebi.ac.uk/ols4/api"
DEFAULT_TIMEOUT = 30.0


@dataclass
class CacheEntry:
    """A cached value with expiration timestamp."""

    value: Any
    expires_at: float

    def is_expired(self: Self) -> bool:
        """Check if this cache entry has expired."""
        return time.time() >= self.expires_at


@dataclass
class OntologySearchResult:
    """Result from an ontology term search."""

    term_id: str
    label: str
    description: str | None = None
    ontology: str | None = None
    iri: str | None = None
    short_form: str | None = None

    def to_dict(self: Self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "term_id": self.term_id,
            "label": self.label,
            "description": self.description,
            "ontology": self.ontology,
            "iri": self.iri,
            "short_form": self.short_form,
        }


@dataclass
class OntologyTerm:
    """Detailed information about an ontology term."""

    term_id: str
    label: str
    description: str | None = None
    ontology: str | None = None
    iri: str | None = None
    synonyms: list[str] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)

    def to_dict(self: Self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "term_id": self.term_id,
            "label": self.label,
            "description": self.description,
            "ontology": self.ontology,
            "iri": self.iri,
            "synonyms": self.synonyms,
            "parents": self.parents,
            "children": self.children,
        }


class RateLimiter:
    """Sliding window rate limiter.

    Tracks request timestamps and blocks when the rate limit is exceeded.
    """

    def __init__(self, max_requests: int, window_seconds: int = 60) -> None:
        """Initialize the rate limiter.

        Args:
            max_requests: Maximum requests allowed in the window.
            window_seconds: Time window in seconds (default: 60).
        """
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._request_times: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self: Self) -> None:
        """Wait until a request can be made within rate limits."""
        async with self._lock:
            now = time.time()
            cutoff = now - self._window_seconds

            # Remove expired timestamps
            self._request_times = [t for t in self._request_times if t > cutoff]

            if len(self._request_times) >= self._max_requests:
                # Wait until oldest request expires
                oldest = self._request_times[0]
                wait_time = oldest + self._window_seconds - now
                if wait_time > 0:
                    logger.debug("Rate limit reached, waiting %.2f seconds", wait_time)
                    await asyncio.sleep(wait_time)
                    # Clean up again after waiting
                    now = time.time()
                    cutoff = now - self._window_seconds
                    self._request_times = [t for t in self._request_times if t > cutoff]

            self._request_times.append(time.time())

    def acquire_sync(self: Self) -> None:
        """Synchronous version of acquire for non-async contexts."""
        now = time.time()
        cutoff = now - self._window_seconds

        # Remove expired timestamps
        self._request_times = [t for t in self._request_times if t > cutoff]

        if len(self._request_times) >= self._max_requests:
            # Wait until oldest request expires
            oldest = self._request_times[0]
            wait_time = oldest + self._window_seconds - now
            if wait_time > 0:
                logger.debug("Rate limit reached, waiting %.2f seconds", wait_time)
                time.sleep(wait_time)
                # Clean up again after waiting
                now = time.time()
                cutoff = now - self._window_seconds
                self._request_times = [t for t in self._request_times if t > cutoff]

        self._request_times.append(time.time())


class OntologyService:
    """Centralized ontology lookup service with caching and rate limiting.

    Provides methods for searching and retrieving ontology terms from OLS4
    with automatic caching and rate limiting to prevent API abuse.

    The service is designed to be used as a singleton via `get_ontology_service()`.

    Attributes:
        cache_ttl: Time-to-live for cache entries in seconds.
        rate_limit: Maximum requests per minute.
        base_url: OLS4 API base URL.
    """

    def __init__(
        self,
        cache_ttl: int | None = None,
        rate_limit: int | None = None,
        base_url: str | None = None,
    ) -> None:
        """Initialize the ontology service.

        Args:
            cache_ttl: Cache TTL in seconds (default from env or 600).
            rate_limit: Max requests per minute (default from env or 60).
            base_url: OLS4 API base URL (default from env or standard OLS4).
        """
        self.cache_ttl = cache_ttl or int(
            os.environ.get("METASEED_OLS_CACHE_TTL", DEFAULT_CACHE_TTL)
        )
        self.rate_limit = rate_limit or int(
            os.environ.get("METASEED_OLS_RATE_LIMIT", DEFAULT_RATE_LIMIT)
        )
        self.base_url = base_url or os.environ.get("METASEED_OLS_BASE_URL", DEFAULT_BASE_URL)

        self._cache: dict[str, CacheEntry] = {}
        self._rate_limiter = RateLimiter(self.rate_limit)
        self._lock = asyncio.Lock()

        logger.debug(
            "OntologyService initialized: cache_ttl=%d, rate_limit=%d/min",
            self.cache_ttl,
            self.rate_limit,
        )

    def _get_cached(self: Self, key: str) -> Any | None:
        """Get a value from the cache if not expired.

        Args:
            key: Cache key.

        Returns:
            Cached value or None if not found/expired.
        """
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry.is_expired():
            del self._cache[key]
            return None
        return entry.value

    def _set_cached(self: Self, key: str, value: Any) -> None:
        """Store a value in the cache.

        Args:
            key: Cache key.
            value: Value to cache.
        """
        self._cache[key] = CacheEntry(
            value=value,
            expires_at=time.time() + self.cache_ttl,
        )

    def clear_cache(self: Self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        logger.debug("Ontology cache cleared")

    def get_cache_stats(self: Self) -> dict[str, int]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats (size, expired count).
        """
        now = time.time()
        total = len(self._cache)
        expired = sum(1 for e in self._cache.values() if e.expires_at < now)
        return {
            "total_entries": total,
            "expired_entries": expired,
            "valid_entries": total - expired,
        }

    async def search(
        self: Self,
        query: str,
        ontology: str | None = None,
        rows: int = 10,
        exact: bool = False,
    ) -> list[OntologySearchResult]:
        """Search OLS4 for ontology terms.

        Args:
            query: Search query string.
            ontology: Optional ontology ID to filter (e.g., "pato", "go").
            rows: Maximum number of results (default: 10).
            exact: If True, only return exact matches.

        Returns:
            List of OntologySearchResult objects.
        """
        if not query or not query.strip():
            return []

        cache_key = f"search:{query}:{ontology}:{rows}:{exact}"

        # Check cache
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug("Cache hit for search: %s", query)
            return cached

        # Rate limit
        await self._rate_limiter.acquire()

        # Build request
        params: dict[str, Any] = {
            "q": query,
            "rows": rows,
            "fieldList": "iri,label,short_form,obo_id,ontology_name,ontology_prefix,description",
        }
        if ontology:
            params["ontology"] = ontology.lower()
        if exact:
            params["exact"] = "true"

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await client.get(f"{self.base_url}/search", params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            logger.warning("OLS4 search error: %s %s", e.response.status_code, e.response.text)
            return []
        except httpx.RequestError as e:
            logger.warning("OLS4 search request failed: %s", e)
            return []

        # Parse results
        results: list[OntologySearchResult] = []
        docs = data.get("response", {}).get("docs", [])

        for doc in docs:
            term_id = doc.get("obo_id") or doc.get("short_form") or ""
            results.append(
                OntologySearchResult(
                    term_id=term_id,
                    label=doc.get("label", ""),
                    description=(doc.get("description") or [""])[0]
                    if doc.get("description")
                    else None,
                    ontology=doc.get("ontology_prefix") or doc.get("ontology_name"),
                    iri=doc.get("iri"),
                    short_form=doc.get("short_form"),
                )
            )

        # Cache results
        self._set_cached(cache_key, results)
        logger.debug("Cached search results for: %s (%d results)", query, len(results))

        return results

    def search_sync(
        self: Self,
        query: str,
        ontology: str | None = None,
        rows: int = 10,
        exact: bool = False,
    ) -> list[OntologySearchResult]:
        """Synchronous version of search for non-async contexts.

        Args:
            query: Search query string.
            ontology: Optional ontology ID to filter.
            rows: Maximum number of results.
            exact: If True, only return exact matches.

        Returns:
            List of OntologySearchResult objects.
        """
        if not query or not query.strip():
            return []

        cache_key = f"search:{query}:{ontology}:{rows}:{exact}"

        # Check cache
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug("Cache hit for search: %s", query)
            return cached

        # Rate limit
        self._rate_limiter.acquire_sync()

        # Build request
        params: dict[str, Any] = {
            "q": query,
            "rows": rows,
            "fieldList": "iri,label,short_form,obo_id,ontology_name,ontology_prefix,description",
        }
        if ontology:
            params["ontology"] = ontology.lower()
        if exact:
            params["exact"] = "true"

        try:
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
                response = client.get(f"{self.base_url}/search", params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            logger.warning("OLS4 search error: %s %s", e.response.status_code, e.response.text)
            return []
        except httpx.RequestError as e:
            logger.warning("OLS4 search request failed: %s", e)
            return []

        # Parse results
        results: list[OntologySearchResult] = []
        docs = data.get("response", {}).get("docs", [])

        for doc in docs:
            term_id = doc.get("obo_id") or doc.get("short_form") or ""
            results.append(
                OntologySearchResult(
                    term_id=term_id,
                    label=doc.get("label", ""),
                    description=(doc.get("description") or [""])[0]
                    if doc.get("description")
                    else None,
                    ontology=doc.get("ontology_prefix") or doc.get("ontology_name"),
                    iri=doc.get("iri"),
                    short_form=doc.get("short_form"),
                )
            )

        # Cache results
        self._set_cached(cache_key, results)
        logger.debug("Cached search results for: %s (%d results)", query, len(results))

        return results

    async def get_term(self: Self, term_id: str) -> OntologyTerm | None:
        """Get detailed information about an ontology term.

        Args:
            term_id: Ontology term ID (e.g., "PATO:0000001", "GO:0008150").

        Returns:
            OntologyTerm object or None if not found.
        """
        if not term_id:
            return None

        cache_key = f"term:{term_id}"

        # Check cache
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug("Cache hit for term: %s", term_id)
            return cached

        # Parse term ID to get ontology
        ontology = self._parse_ontology_from_term_id(term_id)
        if not ontology:
            logger.warning("Could not determine ontology from term ID: %s", term_id)
            return None

        # Rate limit
        await self._rate_limiter.acquire()

        # Construct IRI
        iri = self._construct_iri(term_id)
        encoded_iri = httpx.URL(iri).raw_path.decode() if iri else ""

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                url = f"{self.base_url}/ontologies/{ontology}/terms/{encoded_iri}"
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug("Term not found: %s", term_id)
                # Cache negative result
                self._set_cached(cache_key, None)
                return None
            logger.warning("OLS4 term lookup error: %s", e)
            return None
        except httpx.RequestError as e:
            logger.warning("OLS4 term request failed: %s", e)
            return None

        # Parse result
        term = OntologyTerm(
            term_id=data.get("obo_id") or data.get("short_form") or term_id,
            label=data.get("label", ""),
            description=(data.get("description") or [""])[0] if data.get("description") else None,
            ontology=data.get("ontology_prefix") or data.get("ontology_name"),
            iri=data.get("iri"),
            synonyms=data.get("synonyms", []),
        )

        # Cache result
        self._set_cached(cache_key, term)
        logger.debug("Cached term: %s", term_id)

        return term

    def get_term_sync(self: Self, term_id: str) -> OntologyTerm | None:
        """Synchronous version of get_term.

        Args:
            term_id: Ontology term ID.

        Returns:
            OntologyTerm object or None if not found.
        """
        if not term_id:
            return None

        cache_key = f"term:{term_id}"

        # Check cache
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug("Cache hit for term: %s", term_id)
            return cached

        # Parse term ID to get ontology
        ontology = self._parse_ontology_from_term_id(term_id)
        if not ontology:
            logger.warning("Could not determine ontology from term ID: %s", term_id)
            return None

        # Rate limit
        self._rate_limiter.acquire_sync()

        # Construct IRI
        iri = self._construct_iri(term_id)
        encoded_iri = httpx.URL(iri).raw_path.decode() if iri else ""

        try:
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
                url = f"{self.base_url}/ontologies/{ontology}/terms/{encoded_iri}"
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug("Term not found: %s", term_id)
                self._set_cached(cache_key, None)
                return None
            logger.warning("OLS4 term lookup error: %s", e)
            return None
        except httpx.RequestError as e:
            logger.warning("OLS4 term request failed: %s", e)
            return None

        # Parse result
        term = OntologyTerm(
            term_id=data.get("obo_id") or data.get("short_form") or term_id,
            label=data.get("label", ""),
            description=(data.get("description") or [""])[0] if data.get("description") else None,
            ontology=data.get("ontology_prefix") or data.get("ontology_name"),
            iri=data.get("iri"),
            synonyms=data.get("synonyms", []),
        )

        # Cache result
        self._set_cached(cache_key, term)
        logger.debug("Cached term: %s", term_id)

        return term

    async def validate_term(self: Self, term_id: str) -> tuple[bool, str | None]:
        """Validate that an ontology term exists.

        Args:
            term_id: Ontology term ID to validate.

        Returns:
            Tuple of (is_valid, warning_message). Warning is None if valid.
        """
        if not term_id or not isinstance(term_id, str):
            return True, None

        # Check if we can parse the term ID
        if ":" not in term_id and "_" not in term_id:
            # Can't determine ontology, skip validation
            return True, None

        term = await self.get_term(term_id)

        if term is not None:
            return True, None

        return False, f"Ontology term '{term_id}' not found in OLS4"

    def validate_term_sync(self: Self, term_id: str) -> tuple[bool, str | None]:
        """Synchronous version of validate_term.

        Args:
            term_id: Ontology term ID to validate.

        Returns:
            Tuple of (is_valid, warning_message).
        """
        if not term_id or not isinstance(term_id, str):
            return True, None

        if ":" not in term_id and "_" not in term_id:
            return True, None

        term = self.get_term_sync(term_id)

        if term is not None:
            return True, None

        return False, f"Ontology term '{term_id}' not found in OLS4"

    def _parse_ontology_from_term_id(self: Self, term_id: str) -> str | None:
        """Extract ontology prefix from a term ID.

        Args:
            term_id: Term ID like "PATO:0000001" or "GO_0008150".

        Returns:
            Lowercase ontology prefix or None.
        """
        if ":" in term_id:
            return term_id.split(":", maxsplit=1)[0].lower()
        if "_" in term_id:
            return term_id.split("_", maxsplit=1)[0].lower()
        return None

    def _construct_iri(self: Self, term_id: str) -> str | None:
        """Construct OBO IRI from term ID.

        Args:
            term_id: Term ID like "PATO:0000001".

        Returns:
            Full IRI or None.
        """
        if ":" in term_id:
            # Convert PATO:0000001 to http://purl.obolibrary.org/obo/PATO_0000001
            normalized = term_id.replace(":", "_")
            return f"http://purl.obolibrary.org/obo/{normalized}"
        if "_" in term_id:
            return f"http://purl.obolibrary.org/obo/{term_id}"
        return None


# Context variable for ontology service singleton
_service_var: ContextVar[OntologyService | None] = ContextVar("ontology_service", default=None)


def get_ontology_service() -> OntologyService:
    """Get the OntologyService singleton.

    Creates the service on first call with configuration from environment
    variables.

    Returns:
        The OntologyService instance.
    """
    service = _service_var.get()
    if service is None:
        service = OntologyService()
        _service_var.set(service)
    return service


def reset_ontology_service() -> None:
    """Reset the OntologyService singleton.

    Useful for testing or reconfiguration.
    """
    _service_var.set(None)
