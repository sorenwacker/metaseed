"""Shared HTTP helper for the repository importer clients.

Issues a GET and returns parsed JSON, retrying transient failures — connection
and timeout errors, and ``429``/``5xx`` responses — with exponential backoff.
Used by the ENA / BrAPI / PRIDE / MetaboLights clients, each of which already
requires ``httpx`` (its respective ``metaseed[...]`` extra), so importing this
module behind those clients is safe.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from collections.abc import Mapping

# Status codes worth retrying: rate limiting and transient server errors.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def request_json(
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = 30.0,
    retries: int = 3,
    backoff: float = 0.5,
    http_client: httpx.Client | None = None,
) -> Any:
    """GET ``url`` and return parsed JSON, retrying transient failures.

    Args:
        url: The URL to request.
        params: Optional query parameters.
        headers: Optional request headers.
        timeout: Per-request timeout in seconds (ignored when ``http_client`` is
            provided, which carries its own configuration).
        retries: Maximum number of retries after the first attempt.
        backoff: Base backoff in seconds; attempt ``n`` waits
            ``backoff * 2**n`` before retrying.
        http_client: Optional pre-configured ``httpx.Client`` (e.g. a mock
            transport for tests).

    Returns:
        The decoded JSON body.

    Raises:
        httpx.HTTPStatusError: On a non-retryable error response, or once
            retries on a retryable status are exhausted.
        httpx.TransportError: On a connection/timeout failure once retries are
            exhausted.
    """
    attempt = 0
    while True:
        try:
            if http_client is not None:
                response = http_client.get(url, params=params, headers=headers)
            else:
                response = httpx.get(
                    url, params=params, headers=headers, timeout=timeout
                )
        except httpx.TransportError:  # TimeoutException is a TransportError subclass
            if attempt >= retries:
                raise
            time.sleep(backoff * 2**attempt)
            attempt += 1
            continue

        if response.status_code in _RETRYABLE_STATUS and attempt < retries:
            time.sleep(backoff * 2**attempt)
            attempt += 1
            continue

        response.raise_for_status()
        return response.json()
