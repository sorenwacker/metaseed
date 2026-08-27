"""The hub client speaks the hub's REST API; the connection check explains failures."""

from __future__ import annotations

import json

import httpx
import pytest

from metaseed.hub.client import HubApiError, HubClient, client_from_settings
from metaseed.hub.connection import check_connection


def _hub(handler):
    """A HubClient over an httpx MockTransport handled by ``handler``."""
    return HubClient(
        "https://hub.test/",
        "msh_x",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_every_call_carries_the_token_and_the_api_prefix() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (request.method, str(request.url), request.headers.get("authorization"))
        )
        return httpx.Response(
            200,
            json={"email": "a@b", "tenant_id": "t", "tenant_name": "T", "name": "A"},
        )

    assert _hub(handler).me()["tenant_id"] == "t"
    assert seen == [("GET", "https://hub.test/api/me", "Bearer msh_x")]


def test_dataset_calls_use_the_hubs_shapes() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, dict(request.url.params), body))
        return httpx.Response(200, json={"id": "d1", "data": body or {}})

    hub = _hub(handler)
    hub.list_datasets("t1")
    hub.create_dataset(
        tenant_id="t1", name="n", profile="isa", version="1.0", data={"entities": []}
    )
    hub.update_dataset("d1", data={"entities": [1]})
    hub.get_dataset("d1")
    assert calls == [
        ("GET", "/api/datasets", {"tenant_id": "t1"}, None),
        (
            "POST",
            "/api/datasets",
            {},
            {
                "tenant_id": "t1",
                "name": "n",
                "profile": "isa",
                "version": "1.0",
                "data": {"entities": []},
            },
        ),
        ("PATCH", "/api/datasets/d1", {}, {"data": {"entities": [1]}}),
        ("GET", "/api/datasets/d1", {}, None),
    ]


def test_a_pushed_spec_is_sent_as_a_draft_unless_publishing_is_asked_for() -> None:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/specs":
            bodies.append(json.loads(request.content))
            return httpx.Response(
                201,
                json={
                    "name": "p",
                    "version": "1.0",
                    "content_hash": "h",
                    "visibility": "draft",
                },
            )
        if request.url.path.endswith("/unpublish"):
            return httpx.Response(200, json={"id": "s1", "visibility": "draft"})
        return httpx.Response(200, text="name: p\n")

    hub = _hub(handler)
    row, created = hub.push_spec("name: p\n")
    assert (row["visibility"], created) == ("draft", True)
    hub.push_spec("name: p\n", publish=True)
    assert [b["publish"] for b in bodies] == [False, True]
    assert hub.unpublish_spec("s1")["visibility"] == "draft"
    assert hub.get_spec("p", "1.0") == "name: p\n"


def test_an_error_status_becomes_a_hub_api_error_with_the_detail() -> None:
    hub = _hub(lambda _r: httpx.Response(409, json={"detail": "bump the version"}))
    with pytest.raises(HubApiError) as excinfo:
        hub.push_spec("x: 1", publish=True)
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == "bump the version"


def test_settings_without_url_or_token_are_refused() -> None:
    with pytest.raises(ValueError):
        client_from_settings({"token": "msh_x"})
    with pytest.raises(ValueError):
        client_from_settings({"url": "https://hub.test"})


class TestTheConnectionCheck:
    def test_success_names_the_account_and_tenant(self) -> None:
        transport = httpx.MockTransport(
            lambda _r: httpx.Response(
                200,
                json={
                    "email": "me@example.org",
                    "name": "Me",
                    "tenant_id": "t",
                    "tenant_name": "Plants",
                },
            )
        )
        check = check_connection(
            {"url": "https://hub.test", "token": "msh_x"},
            http_client=httpx.Client(transport=transport),
        )
        assert check.ok
        assert "me@example.org" in check.message and "Plants" in check.message
        assert check.projects == []

    def test_a_rejected_token_is_said_so(self) -> None:
        transport = httpx.MockTransport(
            lambda _r: httpx.Response(401, json={"detail": "no"})
        )
        check = check_connection(
            {"url": "https://hub.test", "token": "msh_x"},
            http_client=httpx.Client(transport=transport),
        )
        assert not check.ok
        assert "rejected the token" in check.message

    def test_a_hub_too_old_for_the_endpoint_is_told_apart_from_a_wrong_url(
        self,
    ) -> None:
        # The deployed hub answered 404 for /api/me while being a perfectly
        # real hub; "check the URL" would have sent the user the wrong way.
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/health"):
                return httpx.Response(
                    200, json={"status": "healthy", "version": "0.40.0"}
                )
            return httpx.Response(404, text="Not Found")

        check = check_connection(
            {"url": "https://hub.test", "token": "msh_x"},
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        assert not check.ok
        assert "0.40.0" in check.message
        assert "updated" in check.message
        assert "base URL" not in check.message

    def test_a_host_that_is_not_a_hub_is_said_so(self) -> None:
        # Nothing answers /api/health either, so there is nothing to update.
        transport = httpx.MockTransport(lambda _r: httpx.Response(404, text="nope"))
        check = check_connection(
            {"url": "https://example.org", "token": "msh_x"},
            http_client=httpx.Client(transport=transport),
        )
        assert "not as a metaseed-hub" in check.message

    def test_nothing_answering_is_said_so(self) -> None:
        def handler(_r: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        check = check_connection(
            {"url": "http://localhost:1", "token": "msh_x"},
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        assert "Nothing answered at localhost:1" in check.message

    def test_missing_config_is_reported_not_raised(self) -> None:
        check = check_connection({})
        assert not check.ok and "URL" in check.message
