"""A search no source could answer must not arrive as "nothing matches".

OntologyService.search_sync returned [] on a transport or HTTP failure, and
TermRouter.search_sync caught every source error and moved on, so an OLS outage
showed the picker "No terms found" and gave agents an empty result list.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from metaseed.services.ontology import OntologyService
from metaseed.services.term_check import TermSourceUnavailableError
from metaseed.services.terms import TermRouter, _router_var


class _Down:
    def search_sync(self, query, ontology=None, limit=20):
        raise TermSourceUnavailableError("search endpoint unreachable")


class _Empty:
    def search_sync(self, query, ontology=None, limit=20):
        return []


class _Finds:
    def search_sync(self, query, ontology=None, limit=20):
        return [SimpleNamespace(term_id="PO:0009005", label="root")]


@pytest.fixture
def router():
    def install(*sources):
        _router_var.set(TermRouter(sources=list(sources)))

    yield install
    _router_var.set(None)


def test_ols_search_raises_when_ols_does_not_answer(monkeypatch) -> None:
    def refuse(self, url, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.Client, "get", refuse)

    with pytest.raises(TermSourceUnavailableError):
        OntologyService().search_sync("root-outage-probe", ontology="po")


def test_router_raises_when_no_source_could_be_asked() -> None:
    with pytest.raises(TermSourceUnavailableError):
        TermRouter(sources=[_Down()]).search_sync("root")


def test_router_returns_what_the_reachable_sources_found() -> None:
    hits = TermRouter(sources=[_Down(), _Finds()]).search_sync("root")

    assert [h.id for h in hits] == ["PO:0009005"]


def test_router_returns_empty_when_every_source_answered_nothing() -> None:
    assert TermRouter(sources=[_Empty()]).search_sync("root") == []


def test_mcp_search_reports_not_searched(router) -> None:
    from metaseed.agent.mcp.server import create_server

    router(_Down())
    tools = create_server()._tool_manager._tools

    result = json.loads(tools["search_ontology"].fn(query="root"))

    assert result["status"] == "not_searched"
    assert "unreachable" in result["reason"]


def test_ui_picker_reports_not_searched(router) -> None:
    from metaseed.ui.app import create_app

    router(_Down())
    response = TestClient(create_app()).get(
        "/api/ontology/search", params={"q": "root"}
    )

    assert response.status_code == 503
    body = response.json()
    assert body["results"] == []
    assert "unreachable" in body["unavailable"]


def test_seek_provisioning_falls_back_to_label_only_when_no_source_answers() -> None:
    """Provisioning promises label-only CV terms without a network; the
    outage must not abort it now that a failed search raises."""
    from metaseed.seek.provision import _cv_terms
    from metaseed.specs.schema import FieldSpec

    field = FieldSpec.model_validate(
        {
            "name": "growth_stage",
            "type": "string",
            "ontologies": ["po"],
            "constraints": {"enum": ["root", "leaf"]},
        }
    )

    terms = _cv_terms(field, TermRouter(sources=[_Down()]))

    assert [(t.label, t.iri) for t in terms] == [("root", None), ("leaf", None)]


def test_cli_search_reports_not_searched(router) -> None:
    from typer.testing import CliRunner

    from metaseed.cli import app
    from metaseed.cli.output import ExitCode

    router(_Down())
    result = CliRunner().invoke(app, ["ontology", "search", "root"])

    assert result.exit_code == ExitCode.UNAVAILABLE
    assert "Not searched" in result.output
