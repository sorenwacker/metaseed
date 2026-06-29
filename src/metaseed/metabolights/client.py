"""HTTP client for the MetaboLights REST API.

Fetches the full metadata document for a MetaboLights study accession from the
EBI MetaboLights web service ``studies`` endpoint. Requires ``httpx`` (the
``metaseed[metabolights]`` extra). An ``httpx.Client`` can be injected for
hermetic testing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    import httpx
except (
    ModuleNotFoundError
) as exc:  # pragma: no cover - exercised only without the extra
    raise ModuleNotFoundError(
        "MetaboLights import requires httpx. "
        "Install with: pip install 'metaseed[metabolights]'"
    ) from exc

from metaseed._http import request_json

if TYPE_CHECKING:
    from collections.abc import Mapping

WS_BASE_URL = "https://www.ebi.ac.uk/metabolights/ws"
USER_AGENT = "metaseed (+https://github.com/sorenwacker/metaseed)"


class MetaboLightsClient:
    """Minimal client for the MetaboLights web service ``studies`` endpoint."""

    def __init__(
        self,
        *,
        base_url: str = WS_BASE_URL,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: MetaboLights web service base URL.
            timeout: Per-request timeout in seconds.
            http_client: Optional pre-configured ``httpx.Client`` (e.g. with a
                mock transport for tests). When omitted, a request is issued
                directly via ``httpx``.
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = http_client

    def study(self, accession: str) -> dict[str, Any]:
        """Return the metadata document for a MetaboLights study.

        Args:
            accession: A MetaboLights study accession (e.g. ``"MTBLS1"``).

        Returns:
            The parsed study metadata document. If the response is wrapped in a
            top-level ``content`` envelope, the inner content is returned;
            otherwise the parsed body is returned unchanged.
        """
        url = f"{self._base_url}/studies/{accession}"
        headers: Mapping[str, str] = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        data: object = request_json(
            url,
            headers=headers,
            timeout=self._timeout,
            http_client=self._client,
        )
        if not isinstance(data, dict):
            return {}
        content = data.get("content")
        if isinstance(content, dict):
            return content
        return data
