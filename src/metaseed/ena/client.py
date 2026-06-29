"""HTTP client for the ENA Portal API.

Fetches run-level metadata for an accession from the ENA Portal ``filereport``
endpoint. Requires ``httpx`` (the ``metaseed[ena]`` extra). An ``httpx.Client``
can be injected for hermetic testing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    import httpx
except (
    ModuleNotFoundError
) as exc:  # pragma: no cover - exercised only without the extra
    raise ModuleNotFoundError(
        "ENA import requires httpx. Install with: pip install 'metaseed[ena]'"
    ) from exc

from metaseed._http import request_json
from metaseed.ena.mapper import READ_RUN_FIELDS

if TYPE_CHECKING:
    from collections.abc import Mapping

PORTAL_FILEREPORT = "https://www.ebi.ac.uk/ena/portal/api/filereport"
USER_AGENT = "metaseed (+https://github.com/sorenwacker/metaseed)"


class EnaClient:
    """Minimal client for the ENA Portal ``filereport`` endpoint."""

    def __init__(
        self,
        *,
        base_url: str = PORTAL_FILEREPORT,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: ENA Portal filereport endpoint.
            timeout: Per-request timeout in seconds.
            http_client: Optional pre-configured ``httpx.Client`` (e.g. with a
                mock transport for tests). When omitted, a request is issued
                directly via ``httpx``.
        """
        self._base_url = base_url
        self._timeout = timeout
        self._client = http_client

    def read_run(self, accession: str) -> list[dict[str, Any]]:
        """Return ENA ``read_run`` metadata rows for an accession.

        Args:
            accession: Any ENA accession resolvable to runs (study, sample,
                experiment, or run).

        Returns:
            One dict per run (empty if the accession resolves to no runs).
        """
        params: Mapping[str, str] = {
            "accession": accession,
            "result": "read_run",
            "fields": ",".join(READ_RUN_FIELDS),
            "format": "json",
            "limit": "0",  # no row cap
        }
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        data = request_json(
            self._base_url,
            params=params,
            headers=headers,
            timeout=self._timeout,
            http_client=self._client,
        )
        return data if isinstance(data, list) else []
