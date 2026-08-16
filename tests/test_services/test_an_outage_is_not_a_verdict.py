""" "Could not ask" must not arrive as "asked, and it is not there".

`check_term` already answers NOT_CHECKED when a source raises, and
`OntologyService.get_term_sync` already raises on a transport or 5xx failure
precisely so an outage is not read as proof of absence. `TermRouter` sat
between them and erased the distinction: it caught every exception, moved on,
and returned ``None`` — the same value that means the term genuinely does not
exist.

The realistic outage is not "OLS is gone". It is OLS answering
``/ontologies/to`` (or that answer sitting in the 600-second cache, which
``_owns`` has just populated on the same request) while ``/ontologies/to/terms/…``
fails. Then `check_term` finds the ontology available, concludes the term is
missing from it, and reports every ontology value in the dataset as invalid
because of someone else's downtime.

Measured against the shipped examples before the fix: 61 of 61 ontology values
across three examples were reported NOT_FOUND — miappe/1.1 26, miappe/1.2 20,
isa/1.0 15. The existing suite missed it because its only failing source also
returned ``None`` from ``has_ontology_sync``, which lands on a different,
already-correct branch.
"""

from __future__ import annotations

import pytest

from metaseed.services.term_check import Outcome, check_term
from metaseed.services.terms import TermRouter


class _TermEndpointDown:
    """OLS with the ontology known and the term endpoint failing."""

    def get_term_sync(self, term_id: str) -> object | None:
        raise RuntimeError("term endpoint unreachable")

    def has_ontology_sync(self, ontology_id: str) -> bool | None:
        return True


class _Absent:
    """A source that carries the ontology and plainly lacks the term."""

    def get_term_sync(self, term_id: str) -> object | None:
        return None

    def has_ontology_sync(self, ontology_id: str) -> bool | None:
        return True


class _Holds:
    def __init__(self, term_id: str) -> None:
        self._term_id = term_id

    def get_term_sync(self, term_id: str) -> object | None:
        return {"id": term_id} if term_id == self._term_id else None

    def has_ontology_sync(self, ontology_id: str) -> bool | None:
        return True


def test_an_outage_is_reported_as_not_checked() -> None:
    """The finding: someone else's downtime called the user's data wrong."""
    verdict = check_term(
        "TO:0000387", ["to"], source=TermRouter(sources=[_TermEndpointDown()])
    )

    assert verdict.outcome is Outcome.NOT_CHECKED
    assert not verdict.is_problem, verdict.message


def test_a_genuine_absence_is_still_not_found() -> None:
    """The fix must not turn every missing term into an excuse."""
    verdict = check_term("TO:0000387", ["to"], source=TermRouter(sources=[_Absent()]))

    assert verdict.outcome is Outcome.NOT_FOUND
    assert verdict.is_problem


def test_a_working_source_still_answers_when_another_is_down() -> None:
    """An outage in one source is irrelevant once another has the term."""
    router = TermRouter(sources=[_TermEndpointDown(), _Holds("TO:0000387")])

    assert check_term("TO:0000387", ["to"], source=router).outcome is Outcome.OK


def test_an_ontology_lookup_that_raises_does_not_escape_check_term() -> None:
    """`has_ontology_sync` is called outside the lookup's try; it must be safe."""

    class _OntologyLookupRaises:
        def get_term_sync(self, term_id: str) -> object | None:
            return None

        def has_ontology_sync(self, ontology_id: str) -> bool | None:
            raise RuntimeError("ontology endpoint unreachable")

    verdict = check_term("TO:0000387", ["to"], source=_OntologyLookupRaises())

    assert verdict.outcome is Outcome.NOT_CHECKED
    assert not verdict.is_problem


def test_the_router_says_it_could_not_ask_rather_than_returning_none() -> None:
    """The router's own contract, independent of who consumes it."""
    from metaseed.services.term_check import TermSourceUnavailableError

    router = TermRouter(sources=[_TermEndpointDown()])

    with pytest.raises(TermSourceUnavailableError):
        router.get_term_sync("TO:0000387")


def test_the_agent_tool_says_unchecked_rather_than_not_found() -> None:
    """The same rule at the MCP surface, where an agent reads the answer.

    `_make_request` returned None for a transport failure exactly as it did for
    a 404, so `get_ontology_term` told the agent "Term not found" when OLS was
    simply unreachable. The suite missed it because the tool's other tests mock
    `_make_request` and never exercised the failure path — and the three that
    reached the network passed only because the router swallowed the blocked
    connection.
    """
    import json
    from unittest.mock import patch

    import httpx

    from metaseed.agent.mcp.tools import ontology as ontology_tools
    from metaseed.services.term_check import TermSourceUnavailableError

    with patch.object(
        ontology_tools.httpx, "Client", side_effect=httpx.ConnectError("down")
    ):
        with pytest.raises(TermSourceUnavailableError):
            ontology_tools._make_request("/ontologies/pato/terms/x")

    def _unreachable(endpoint, params=None):
        raise TermSourceUnavailableError("OLS could not be reached")

    from metaseed.agent.mcp.server import create_server
    from tests.test_agent.helpers import get_tool

    tool = get_tool(create_server(), "get_ontology_term")
    with patch.object(ontology_tools, "_make_request", _unreachable):
        answer = json.loads(tool(term_id="PATO:0000015"))

    assert answer.get("checked") is False
    assert "not found" not in answer.get("error", "").lower()
