"""The Plugins page's connection check for a metaseed-hub."""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import httpx

from metaseed.hub.client import HubApiError, HubClient, client_from_settings

if TYPE_CHECKING:
    from collections.abc import Mapping

PROBE_TIMEOUT = 5.0


@dataclass(frozen=True)
class ConnectionCheck:
    """Outcome of one connection check, in the shape the Plugins page renders."""

    ok: bool
    message: str
    """One sentence: the account and tenant, or the cause of failure."""
    projects: list[tuple[str, str]] = field(default_factory=list)
    """Always empty: a hub token acts in one tenant, there is nothing to choose."""


def describe_failure(exc: Exception, url: str) -> str:
    """One sentence for the user on why the hub could not be reached."""
    host = urlsplit(url).netloc or url
    text = str(exc)
    if isinstance(exc, socket.gaierror) or "Name or service not known" in text:
        return f"Cannot resolve {host}. It needs a hostname or address this machine can see."
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout):
        return (
            f"Nothing answered at {host}. Check the URL and that the hub is reachable."
        )
    if isinstance(exc, httpx.TimeoutException):
        return f"{host} did not answer within {PROBE_TIMEOUT:g} seconds."
    if isinstance(exc, HubApiError):
        if exc.status_code in (401, 403):
            return "The hub rejected the token. Check it was copied whole and has not been revoked."
        if exc.status_code == 404:
            return (
                f"{host} answered, but not as a metaseed-hub. Give the hub's base URL."
            )
        if exc.status_code >= 500:
            return f"{host} is not serving the hub right now (HTTP {exc.status_code})."
        return f"The hub answered HTTP {exc.status_code}: {exc.detail}"
    return f"Could not reach the hub at {host}: {exc}"


def _missing_endpoint(client: HubClient, config: Mapping[str, str]) -> str:
    """Why a hub answered 404 for the endpoint the exchange needs.

    Either the URL is not a hub at all, or it is one running a version from
    before the endpoint existed. ``/api/health`` answers on an old hub and a
    new one alike and names the version, which is what tells the two apart.

    Args:
        client: The client that just met the 404.
        config: The stored ``hub`` adapter config, for the host in the message.

    Returns:
        One sentence naming the version, or saying the URL is not a hub.
    """
    host = urlsplit(config.get("url", "")).netloc or config.get("url", "")
    try:
        version = client.health().get("version", "an unknown version")
    except Exception:
        return f"{host} answered, but not as a metaseed-hub. Give the hub's base URL."
    return (
        f"{host} is a metaseed-hub running {version}, which does not serve the "
        "endpoints this needs. It has to be updated to a release that has them "
        "before datasets or profiles can be pushed to it."
    )


def check_connection(
    config: Mapping[str, str],
    *,
    timeout: float = PROBE_TIMEOUT,
    http_client: httpx.Client | None = None,
) -> ConnectionCheck:
    """Ask the hub who the token is, and report it or the failure.

    Args:
        config: The stored ``hub`` adapter config (``url``, ``token``).
        timeout: Per-request bound; small, since this runs from a settings page.
        http_client: Injected transport, for tests.
    """
    try:
        client = client_from_settings(config, timeout=timeout, http_client=http_client)
    except ValueError as exc:
        return ConnectionCheck(ok=False, message=str(exc))
    try:
        me = client.me()
    except HubApiError as exc:
        if exc.status_code == 404:
            # A hub from before this endpoint existed is a real hub running an
            # old version, not a wrong URL -- and telling someone to check a
            # URL that is right sends them the wrong way.
            return ConnectionCheck(ok=False, message=_missing_endpoint(client, config))
        return ConnectionCheck(
            ok=False, message=describe_failure(exc, config.get("url", ""))
        )
    except Exception as exc:  # every failure is a diagnosis, not a crash
        return ConnectionCheck(
            ok=False, message=describe_failure(exc, config.get("url", ""))
        )
    return ConnectionCheck(
        ok=True,
        message=f"Connected as {me.get('email', '?')} in tenant {me.get('tenant_name', '?')}.",
    )
