"""Check a stored SEEK configuration against the live instance.

One read-only request (``GET /projects``) answers three questions at once: is
the URL a reachable SEEK API, does the key work, and which projects can the
key write into. :func:`describe_failure` turns the ways that request fails
into sentences that name the cause — a hostname that does not resolve, a port
nothing answers on, a rejected key, a downed instance, and a URL that is not
an API root each have a different fix, so each gets its own message rather
than a shared "check the URL and the key".
"""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import httpx

from metaseed.seek.client import SeekApiError, client_from_settings

if TYPE_CHECKING:
    from collections.abc import Mapping

#: Bound on the probe: a misconfigured host must not stall a settings page.
PROBE_TIMEOUT = 5.0


@dataclass(frozen=True)
class ConnectionCheck:
    """Outcome of one connection check."""

    ok: bool
    message: str
    """One sentence for the user: the project count, or the cause of failure."""
    projects: list[tuple[str, str]] = field(default_factory=list)
    """``(id, title)`` of the projects the key can see; empty on failure."""


def describe_failure(exc: Exception, url: str) -> str:
    """Name the cause of a failed SEEK request at ``url``."""
    host = urlsplit(url).netloc or url
    text = str(exc)
    if (
        isinstance(exc, socket.gaierror)
        or "nodename nor servname" in text
        or "name resolution" in text
        or "Name or service not known" in text
    ):
        return f"Cannot resolve {host}. It needs a hostname or address this machine can see."
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout):
        return (
            f"Nothing answered at {host}. Check the port and that the instance "
            "is running and reachable from this machine."
        )
    if isinstance(exc, httpx.TimeoutException):
        return f"{host} did not answer within {PROBE_TIMEOUT:g} seconds."
    code = (
        exc.status_code
        if isinstance(exc, SeekApiError)
        else exc.response.status_code
        if isinstance(exc, httpx.HTTPStatusError)
        else None
    )
    if code is not None:
        if code in (401, 403):
            return "SEEK rejected the API key. Check it was copied whole and has not expired."
        if code >= 500:
            return (
                f"{host} is not serving SEEK right now (HTTP {code}). The instance "
                "or the proxy in front of it is down; try again once it is back."
            )
        if code == 404:
            return (
                f"{host} answered, but not as a SEEK API. Give the instance's base "
                "URL, without /api or a path."
            )
        return f"SEEK answered HTTP {code} for {host}."
    return f"Could not reach SEEK at {host}: {exc}"


def check_connection(
    config: Mapping[str, str],
    *,
    timeout: float = PROBE_TIMEOUT,
    http_client: httpx.Client | None = None,
) -> ConnectionCheck:
    """Ask the configured SEEK for its projects and report what happened.

    Args:
        config: The stored ``seek`` adapter config (``url``, ``api_key``).
        timeout: Per-request bound; small, since this runs from a settings page.
        http_client: Injected transport, for tests.
    """
    try:
        client = client_from_settings(config, timeout=timeout, http_client=http_client)
    except ValueError as exc:
        return ConnectionCheck(ok=False, message=str(exc))
    try:
        projects = client.list_projects()
    except Exception as exc:  # every failure is a diagnosis, not a crash
        return ConnectionCheck(
            ok=False, message=describe_failure(exc, config.get("url", ""))
        )
    noun = "project" if len(projects) == 1 else "projects"
    return ConnectionCheck(
        ok=True,
        message=f"Connected: {len(projects)} {noun} visible.",
        projects=projects,
    )
