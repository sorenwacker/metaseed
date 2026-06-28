"""HTTP client for the PRIDE Archive API.

Fetches project-level metadata and the file list for a ProteomeXchange (PXD)
accession from the PRIDE Archive ``v2`` web service. Requires ``httpx`` (the
``metaseed[pride]`` extra). An ``httpx.Client`` can be injected for hermetic
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
        "PRIDE import requires httpx. Install with: pip install 'metaseed[pride]'"
    ) from exc

if TYPE_CHECKING:
    from collections.abc import Mapping

PRIDE_ARCHIVE_V2 = "https://www.ebi.ac.uk/pride/ws/archive/v2"
USER_AGENT = "metaseed (+https://github.com/sorenwacker/metaseed)"


class PrideClient:
    """Minimal client for the PRIDE Archive ``v2`` web service."""

    def __init__(
        self,
        *,
        base_url: str = PRIDE_ARCHIVE_V2,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: PRIDE Archive ``v2`` base URL.
            timeout: Per-request timeout in seconds.
            http_client: Optional pre-configured ``httpx.Client`` (e.g. with a
                mock transport for tests). When omitted, requests are issued
                directly via ``httpx``.
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = http_client

    def _get(self, path: str) -> Any:
        """Issue a GET request and return the parsed JSON payload.

        Args:
            path: Path appended to the configured base URL.

        Returns:
            The decoded JSON body.
        """
        url = f"{self._base_url}{path}"
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self._client is not None:
            response = self._client.get(url, headers=headers)
        else:
            response = httpx.get(url, headers=headers, timeout=self._timeout)
        response.raise_for_status()
        return response.json()

    def project(self, accession: str) -> dict[str, Any]:
        """Return PRIDE project metadata for an accession.

        Args:
            accession: A ProteomeXchange accession (e.g. ``"PXD000001"``).

        Returns:
            The project metadata as a JSON object (empty if not a dict).
        """
        data = self._get(f"/projects/{accession}")
        return data if isinstance(data, dict) else {}

    def files(self, accession: str) -> list[dict[str, Any]]:
        """Return the list of files for a PRIDE project.

        Handles both the plain list response and the HAL paged
        ``{"_embedded": {"files": [...]}}`` shape.

        Args:
            accession: A ProteomeXchange accession (e.g. ``"PXD000001"``).

        Returns:
            One dict per file (empty if the project has no files).
        """
        data = self._get(f"/projects/{accession}/files")
        return _extract_files(data)


def _extract_files(data: Any) -> list[dict[str, Any]]:
    """Normalize a PRIDE files payload into a plain list of file dicts.

    Args:
        data: The decoded files response (a list or a HAL paged object).

    Returns:
        The file records as a list (empty when none are present).
    """
    if isinstance(data, list):
        return [f for f in data if isinstance(f, dict)]
    if isinstance(data, dict):
        embedded: Mapping[str, Any] = data.get("_embedded") or {}
        files = embedded.get("files")
        if isinstance(files, list):
            return [f for f in files if isinstance(f, dict)]
    return []
