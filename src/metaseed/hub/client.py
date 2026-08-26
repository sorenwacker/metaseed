"""HTTP client for a metaseed-hub's REST API (``/api``, bearer token).

Requires ``httpx`` (the ``metaseed[hub]`` extra). An ``httpx.Client`` can be
injected for tests; otherwise one is opened per request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    import httpx
except ImportError as _exc:  # pragma: no cover - exercised by the extras gate
    raise ImportError(
        "Hub support requires httpx. Install with: pip install 'metaseed[hub]'"
    ) from _exc

if TYPE_CHECKING:
    from collections.abc import Mapping

DEFAULT_TIMEOUT = 30.0


class HubApiError(RuntimeError):
    """The hub answered with an error status."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


def client_from_settings(
    config: Mapping[str, str],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    http_client: httpx.Client | None = None,
) -> HubClient:
    """Build a client from the stored ``hub`` adapter config.

    Raises:
        ValueError: If the URL or the token is not configured.
    """
    url = (config.get("url") or "").strip()
    if not url:
        raise ValueError("Hub URL is not configured (set it on the Plugins page)")
    token = (config.get("token") or "").strip()
    if not token:
        raise ValueError(
            "Hub access token is not configured (set it on the Plugins page)"
        )
    return HubClient(url, token, timeout=timeout, http_client=http_client)


class HubClient:
    """The subset of the hub's REST API the push/pull needs."""

    def __init__(
        self,
        url: str,
        token: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._http_client = http_client

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        url = f"{self.url}/api{path}"
        if self._http_client is not None:
            response = self._http_client.request(method, url, headers=headers, **kwargs)
        else:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.request(method, url, headers=headers, **kwargs)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise HubApiError(response.status_code, str(detail))
        return response

    def me(self) -> dict[str, str]:
        """The account and tenant the token acts in."""
        data: dict[str, str] = self._request("GET", "/me").json()
        return data

    def list_datasets(self, tenant_id: str) -> list[dict[str, Any]]:
        """The caller's datasets in ``tenant_id``."""
        rows: list[dict[str, Any]] = self._request(
            "GET", "/datasets", params={"tenant_id": tenant_id}
        ).json()
        return rows

    def get_dataset(self, dataset_id: str) -> dict[str, Any]:
        row: dict[str, Any] = self._request("GET", f"/datasets/{dataset_id}").json()
        return row

    def create_dataset(
        self,
        *,
        tenant_id: str,
        name: str,
        profile: str,
        version: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        row: dict[str, Any] = self._request(
            "POST",
            "/datasets",
            json={
                "tenant_id": tenant_id,
                "name": name,
                "profile": profile,
                "version": version,
                "data": data,
            },
        ).json()
        return row

    def update_dataset(
        self, dataset_id: str, *, data: dict[str, Any]
    ) -> dict[str, Any]:
        row: dict[str, Any] = self._request(
            "PATCH", f"/datasets/{dataset_id}", json={"data": data}
        ).json()
        return row

    def list_specs(self) -> list[dict[str, Any]]:
        """Every published specification."""
        rows: list[dict[str, Any]] = self._request("GET", "/specs").json()
        return rows

    def get_spec(self, name: str, version: str) -> str:
        """One published specification as its YAML document."""
        return self._request("GET", f"/specs/{name}/{version}").text

    def publish_spec(self, yaml_text: str) -> tuple[dict[str, Any], bool]:
        """Publish a profile document.

        Returns:
            The published row and whether it was created now (False when the
            same content was already published at that name and version).
        """
        response = self._request("POST", "/specs", json={"yaml": yaml_text})
        row: dict[str, Any] = response.json()
        return row, response.status_code == 201
