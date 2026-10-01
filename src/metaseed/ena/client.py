"""HTTP client for the ENA Portal API.

Fetches the metadata the Portal ``filereport`` endpoint publishes for an
accession, one request per result — ``study``, ``read_run`` and ``analysis`` —
asking for every column ENA publishes (``fields=all``). Requires ``httpx`` (the
``metaseed[ena]`` extra). An ``httpx.Client`` can be injected for hermetic
testing.
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

    def _rows(self, accession: str, result: str) -> list[dict[str, Any]]:
        """One ``filereport`` request for ``result``, with every column.

        Asks for ``fields=all``, so each row carries every column ENA publishes
        for that result rather than a chosen subset. A column the ``ena``
        profile does not declare a field for still reaches the dataset, as an
        attribute.
        """
        params: Mapping[str, str] = {
            "accession": accession,
            "result": result,
            "fields": "all",  # every column ENA publishes for the result
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

    def read_run(self, accession: str) -> list[dict[str, Any]]:
        """Return ENA ``read_run`` rows for an accession: one per run.

        Args:
            accession: Any ENA accession resolvable to runs (study, sample,
                experiment, or run).

        Returns:
            One dict per run (empty if the accession resolves to no runs).
        """
        return self._rows(accession, "read_run")

    def study(self, accession: str) -> list[dict[str, Any]]:
        """Return the ENA ``study`` row for an accession.

        The study record carries the columns that exist under no other result
        (``study_description``, ``study_name``, ``keywords``, ...).

        Returns:
            One dict per study the accession resolves to (normally one).
        """
        return self._rows(accession, "study")

    def analysis(self, accession: str) -> list[dict[str, Any]]:
        """Return ENA ``analysis`` rows for an accession: one per analysis.

        Assemblies, variant calls and annotations are a different Portal
        result from the runs they derive from.

        Returns:
            One dict per analysis (empty when the study has none).
        """
        return self._rows(accession, "analysis")
