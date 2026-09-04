"""Check stored ENA Webin credentials against the live service.

Submitting to ENA needs a Webin account, and the one question worth answering
before a submission is attempted is whether the credentials work at all. One
request answers it: the Webin authentication endpoint returns a token for a
valid account and ``401`` for anything else.

The check runs against ENA's **test** service. The account is the same one
production uses, so a token from the test service proves the credentials, and
checking there means confirming a password never touches the live archive.
Submission chooses its service separately and deliberately.
"""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING

try:
    import httpx
except (
    ModuleNotFoundError
) as exc:  # pragma: no cover - exercised only without the extra
    raise ModuleNotFoundError(
        "ENA submission requires httpx. Install with: pip install 'metaseed[ena]'"
    ) from exc

from metaseed.connection import PROBE_TIMEOUT, ConnectionCheck
from metaseed.ena.client import USER_AGENT

if TYPE_CHECKING:
    from collections.abc import Mapping

#: ENA's test service. Deliberately the default for a credential check.
WEBIN_TEST_AUTH_URL = "https://wwwdev.ebi.ac.uk/ena/submit/webin/auth/token"
#: The live service. Only a submission the user confirms should reach this.
WEBIN_AUTH_URL = "https://www.ebi.ac.uk/ena/submit/webin/auth/token"


def _describe_failure(exc: Exception) -> str:
    """Name the cause of a failed Webin request."""
    host = "ENA's Webin service"
    if isinstance(exc, socket.gaierror) or "name resolution" in str(exc).lower():
        return f"Cannot resolve {host}. Check this machine's network and DNS."
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout):
        return f"Nothing answered at {host}. Check this machine can reach the internet."
    if isinstance(exc, httpx.TimeoutException):
        return f"{host} did not answer within {PROBE_TIMEOUT:g} seconds."
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return (
                "ENA rejected the Webin credentials. Check the username is the "
                "Webin-NNNNN account and the password was copied whole."
            )
        if code >= 500:
            return (
                f"{host} is not answering right now (HTTP {code}). Try again "
                "once it is back; the credentials were not judged."
            )
        return f"{host} refused the request (HTTP {code})."
    return f"Could not reach {host}: {exc}"


def check_connection(
    config: Mapping[str, str], *, http_client: httpx.Client | None = None
) -> ConnectionCheck:
    """Whether the stored Webin credentials authenticate.

    Args:
        config: The adapter's stored settings, holding ``webin_username`` and
            ``webin_password``.
        http_client: An ``httpx.Client`` to use instead of a new one, for
            hermetic testing.

    Returns:
        A :class:`ConnectionCheck`. ``projects`` is always empty: ENA has no
        equivalent of a project to choose between, so the Plugins page offers
        no choice for this adapter.
    """
    username = str(config.get("webin_username") or "").strip()
    password = str(config.get("webin_password") or "")
    if not username or not password:
        return ConnectionCheck(
            ok=False,
            message="Enter the Webin username (Webin-NNNNN) and password.",
        )

    payload = {"authRealms": ["ENA"], "username": username, "password": password}
    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    try:
        if http_client is not None:
            response = http_client.post(
                WEBIN_TEST_AUTH_URL, json=payload, headers=headers
            )
        else:
            with httpx.Client(timeout=PROBE_TIMEOUT) as client:
                response = client.post(
                    WEBIN_TEST_AUTH_URL, json=payload, headers=headers
                )
        response.raise_for_status()
    except Exception as exc:
        # Every failure becomes a sentence: a settings page must report why it
        # could not check, not raise into the request.
        return ConnectionCheck(ok=False, message=_describe_failure(exc))

    return ConnectionCheck(
        ok=True,
        message=f"ENA accepted {username} on the test service.",
    )
