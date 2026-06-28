"""HTTP client for a BrAPI v2 server.

Fetches plant-breeding metadata from any server implementing the
[Breeding API](https://brapi.org) v2. The base URL is configurable (BrAPI is a
standard, not a single endpoint) and an optional bearer token authenticates
against protected servers. Requires ``httpx`` (the ``metaseed[brapi]`` extra).
An ``httpx.Client`` can be injected for hermetic testing.

BrAPI wraps every payload as ``{"metadata": ..., "result": {"data": [...]}}``;
each method returns the ``result.data`` list.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    import httpx
except (
    ModuleNotFoundError
) as exc:  # pragma: no cover - exercised only without the extra
    raise ModuleNotFoundError(
        "BrAPI import requires httpx. Install with: pip install 'metaseed[brapi]'"
    ) from exc

if TYPE_CHECKING:
    from collections.abc import Mapping

USER_AGENT = "metaseed (+https://github.com/sorenwacker/metaseed)"


class BrapiClient:
    """Minimal client for the BrAPI v2 endpoints metaseed imports."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: BrAPI v2 base URL (e.g.
                ``https://test-server.brapi.org/brapi/v2``).
            token: Optional bearer token for authenticated servers. When given,
                an ``Authorization: Bearer <token>`` header is sent.
            timeout: Per-request timeout in seconds.
            http_client: Optional pre-configured ``httpx.Client`` (e.g. with a
                mock transport for tests). When omitted, a request is issued
                directly via ``httpx``.
        """
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._client = http_client

    def studies(self) -> list[dict[str, Any]]:
        """Return BrAPI ``studies`` objects."""
        return self._get("studies")

    def observation_units(self, study_db_id: str) -> list[dict[str, Any]]:
        """Return BrAPI ``observationunits`` objects for a study.

        Args:
            study_db_id: The ``studyDbId`` to filter observation units by.
        """
        return self._get("observationunits", {"studyDbId": study_db_id})

    def observations(self, study_db_id: str) -> list[dict[str, Any]]:
        """Return BrAPI ``observations`` objects for a study.

        Args:
            study_db_id: The ``studyDbId`` to filter observations by.
        """
        return self._get("observations", {"studyDbId": study_db_id})

    def germplasm(self) -> list[dict[str, Any]]:
        """Return BrAPI ``germplasm`` objects."""
        return self._get("germplasm")

    def _get(
        self, path: str, params: Mapping[str, str] | None = None
    ) -> list[dict[str, Any]]:
        """Issue a GET request and return the BrAPI ``result.data`` list.

        Args:
            path: Endpoint path appended to the base URL.
            params: Optional query parameters.

        Returns:
            The ``result.data`` list (empty if the server omits it).
        """
        url = f"{self._base_url}/{path}"
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if self._client is not None:
            response = self._client.get(url, params=params, headers=headers)
        else:
            response = httpx.get(
                url, params=params, headers=headers, timeout=self._timeout
            )
        response.raise_for_status()
        result = response.json().get("result") or {}
        data = result.get("data")
        return data if isinstance(data, list) else []
