"""Stored Webin credentials are checked against ENA, and never against production.

Credentials that are stored but never exercised are worth nothing: the point of
holding them is to be able to answer "will a submission authenticate?" before
one is attempted. One request answers it, and it goes to ENA's **test** service
so confirming a password never touches the live archive.

Hermetic: an ``httpx.MockTransport`` stands in for ENA, as in ``test_client``.
"""

from __future__ import annotations

import httpx
import pytest

from metaseed.adapters import get_adapter
from metaseed.ena.connection import (
    WEBIN_AUTH_URL,
    WEBIN_TEST_AUTH_URL,
    check_connection,
)

CREDENTIALS = {"webin_username": "Webin-12345", "webin_password": "s3cret"}


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class TestWhatItAsksEna:
    def test_it_posts_the_credentials_to_the_test_service(self) -> None:
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["body"] = request.read().decode()
            return httpx.Response(200, json={"token": "a.jwt.token"})

        check_connection(CREDENTIALS, http_client=_client(handler))

        assert seen["url"] == WEBIN_TEST_AUTH_URL
        assert "Webin-12345" in str(seen["body"])
        assert '"authRealms"' in str(seen["body"])

    def test_the_live_service_is_never_the_one_checked(self) -> None:
        """A password confirmation must not reach the live archive."""
        assert WEBIN_TEST_AUTH_URL != WEBIN_AUTH_URL
        assert "wwwdev" in WEBIN_TEST_AUTH_URL


class TestWhatItReports:
    def test_a_token_means_the_credentials_work(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"token": "a.jwt.token"})

        result = check_connection(CREDENTIALS, http_client=_client(handler))

        assert result.ok
        assert "Webin-12345" in result.message

    def test_a_rejection_names_the_credentials_as_the_cause(self) -> None:
        """ENA answers 401 'Bad credentials' — verified against the live test service."""

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="Bad credentials")

        result = check_connection(CREDENTIALS, http_client=_client(handler))

        assert not result.ok
        assert "rejected" in result.message.lower()

    def test_an_outage_does_not_blame_the_credentials(self) -> None:
        """Someone else's downtime must not read as a wrong password."""

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="upstream down")

        result = check_connection(CREDENTIALS, http_client=_client(handler))

        assert not result.ok
        assert "not answering" in result.message
        assert "were not judged" in result.message

    def test_an_unreachable_service_is_reported_not_raised(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host")

        result = check_connection(CREDENTIALS, http_client=_client(handler))

        assert not result.ok
        assert "Nothing answered" in result.message

    @pytest.mark.parametrize(
        "config",
        [{}, {"webin_username": "Webin-1"}, {"webin_password": "p"}],
    )
    def test_missing_credentials_ask_for_them_without_calling_ena(
        self, config: dict[str, str]
    ) -> None:
        def handler(_: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("ENA must not be called without credentials")

        result = check_connection(config, http_client=_client(handler))

        assert not result.ok
        assert "Webin-NNNNN" in result.message

    def test_it_offers_no_project_choice(self) -> None:
        """ENA has no project to pick between, unlike SEEK."""

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"token": "t"})

        assert (
            check_connection(CREDENTIALS, http_client=_client(handler)).projects == []
        )


class TestItIsReachableFromTheSettingsPage:
    def test_the_adapter_declares_the_fields_and_the_check(self) -> None:
        """Stored credentials with nothing to use them are dead weight."""
        adapter = get_adapter("ena")

        keys = {field.key for field in adapter.config_fields}
        assert keys == {"webin_username", "webin_password"}
        assert adapter.check_ref is not None

    def test_the_password_is_declared_secret(self) -> None:
        """The Plugins page masks a field only when the registry says to."""
        adapter = get_adapter("ena")
        secret = {f.key for f in adapter.config_fields if f.secret}

        assert secret == {"webin_password"}

    def test_the_declared_check_resolves_to_this_one(self) -> None:
        """By name, not identity: the registry imports the module afresh, so a
        full-suite run can hold two equal-but-distinct function objects."""
        resolved = get_adapter("ena").resolve_check()

        assert (resolved.__module__, resolved.__qualname__) == (
            check_connection.__module__,
            check_connection.__qualname__,
        )
