"""Ontology lookup tools for MCP server using OLS4 API.

This module provides tools for searching and retrieving ontology terms
from the EMBL-EBI Ontology Lookup Service (OLS4).

OLS4 API: https://www.ebi.ac.uk/ols4/api
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from typing import TYPE_CHECKING, Any, cast

import httpx

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from metaseed.agent.mcp.context import ResolveContext
    from metaseed.agent.mcp.ui_session import AppState

logger = logging.getLogger(__name__)

OLS4_BASE_URL = "https://www.ebi.ac.uk/ols4/api"
DEFAULT_TIMEOUT = 30.0


def _make_request(
    endpoint: str, params: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Make a request to the OLS4 API.

    Args:
        endpoint: API endpoint path (e.g., "/search").
        params: Query parameters.

    Returns:
        JSON response or None on error.
    """
    url = f"{OLS4_BASE_URL}{endpoint}"
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            return cast("dict[str, Any]", response.json())
    except httpx.HTTPStatusError as e:
        logger.warning("OLS4 API error: %s %s", e.response.status_code, e.response.text)
        return None
    except httpx.RequestError as e:
        logger.warning("OLS4 request failed: %s", e)
        return None


def register_ontology_tools(  # noqa: C901
    mcp: FastMCP, resolve_context: ResolveContext
) -> None:
    """Register ontology lookup tools with the MCP server.

    Lookups hit OLS4 and need no session, but ``validate_ontology_terms``
    checks the active dataset's terms, so this registrar is not stateless
    despite looking it.

    Args:
        mcp: FastMCP server instance.
        resolve_context: Returns the context for the call being served.
    """

    def current_state() -> AppState:
        """The state of the session this call is serving.

        Named to avoid colliding with the ``state`` locals several tools use.
        """
        return resolve_context().state

    @mcp.tool()
    def search_ontology(query: str, ontology: str | None = None, rows: int = 10) -> str:
        """Search the configured ontology sources for terms matching a query.

        Searches across term labels and, where the source offers it, synonyms
        and descriptions. Use this to find ontology terms when you know what
        concept you are looking for but not the exact term ID.

        OLS4 is one source. Vocabularies configured locally are searched first,
        so a project's own terms are findable here too.

        Args:
            query: Search query (e.g., "drought", "plant growth").
            ontology: Optional ontology ID to restrict search (e.g., "pato", "go", "obi").
                If not provided, searches across all configured sources.
            rows: Maximum number of results to return (default: 10, max: 100).

        Returns:
            JSON with search results including term IDs, labels, and which
            source answered.
        """
        from metaseed.services.terms import get_term_source

        rows = min(max(1, rows), 100)
        hits = get_term_source().search_sync(query, ontology, rows)

        return json.dumps(
            {
                "query": query,
                "ontology": ontology,
                "total_found": len(hits),
                "results": [
                    {
                        "id": hit.id,
                        "label": hit.label,
                        "ontology": hit.ontology,
                        "description": hit.description,
                        "source": hit.source,
                    }
                    for hit in hits
                ],
            },
            indent=2,
        )

    @mcp.tool()
    def get_ontology_term(term_id: str) -> str:
        """Get detailed information about an ontology term by its ID.

        Retrieves the term definition, synonyms, parent terms, and other metadata.
        The term_id can be in CURIE format (PREFIX:ID) or a full IRI.

        Args:
            term_id: Term identifier in CURIE format (e.g., "PATO:0000015", "GO:0008150")
                or full IRI (e.g., "http://purl.obolibrary.org/obo/PATO_0000015").

        Returns:
            JSON with term details including label, description, and synonyms.
        """
        from metaseed.services.ontology import OntologyTerm
        from metaseed.services.terms import get_term_source

        # Ask the configured sources first. A term held in a local vocabulary
        # is answered from there; only OLS terms continue to the detail request
        # below, which asks for the parts — obsolescence, annotations — that
        # only OLS has.
        found = get_term_source().get_term_sync(term_id)
        if found is not None and not isinstance(found, OntologyTerm):
            return json.dumps(
                {
                    "id": getattr(found, "id", term_id),
                    "label": getattr(found, "label", ""),
                    "source": type(found).__name__,
                },
                indent=2,
            )

        # Determine if it's a CURIE or IRI
        if term_id.startswith("http://") or term_id.startswith("https://"):
            iri = term_id
            # Try to extract ontology from IRI
            if "/obo/" in iri:
                # OBO format: http://purl.obolibrary.org/obo/PATO_0000015
                parts = iri.split("/obo/")[-1].split("_")
                ontology = parts[0].lower() if parts else None
            else:
                ontology = None
        elif ":" in term_id:
            prefix, local_id = term_id.split(":", 1)
            ontology = prefix.lower()
            # Convert to OBO IRI format
            iri = f"http://purl.obolibrary.org/obo/{prefix}_{local_id}"
        else:
            return json.dumps({"error": f"Invalid term ID format: {term_id}"})

        if not ontology:
            return json.dumps({"error": "Could not determine ontology from term ID"})

        # URL encode the IRI twice (OLS4 requirement)
        encoded_iri = urllib.parse.quote(urllib.parse.quote(iri, safe=""), safe="")

        data = _make_request(f"/ontologies/{ontology}/terms/{encoded_iri}")
        if data is None:
            return json.dumps({"error": f"Term not found: {term_id}"})

        result = {
            "id": data.get("obo_id") or data.get("short_form"),
            "label": data.get("label"),
            "ontology": data.get("ontology_prefix") or data.get("ontology_name"),
            "iri": data.get("iri"),
            "is_obsolete": data.get("is_obsolete", False),
        }

        if data.get("description"):
            descriptions = data["description"]
            if isinstance(descriptions, list) and descriptions:
                result["definition"] = descriptions[0]
            elif isinstance(descriptions, str):
                result["definition"] = descriptions

        if data.get("synonyms"):
            result["synonyms"] = data["synonyms"]

        if data.get("annotation"):
            # Extract useful annotations
            annotations = data["annotation"]
            if "has_obo_namespace" in annotations:
                result["namespace"] = annotations["has_obo_namespace"]
            if "created_by" in annotations:
                result["created_by"] = annotations["created_by"]

        return json.dumps(result, indent=2)

    @mcp.tool()
    def list_ontologies(rows: int = 50) -> str:
        """List available ontologies in OLS4.

        Returns a list of ontologies with their IDs, names, and descriptions.
        Use this to discover what ontologies are available for searching.

        Args:
            rows: Maximum number of ontologies to return (default: 50, max: 500).

        Returns:
            JSON with list of ontologies including ID, name, and description.
        """
        rows = min(max(1, rows), 500)

        params = {"size": rows}
        data = _make_request("/ontologies", params)
        if data is None:
            return json.dumps({"error": "Failed to list ontologies"})

        embedded = data.get("_embedded", {})
        ontologies = embedded.get("ontologies", [])

        results = []
        for ont in ontologies:
            config = ont.get("config", {})
            result = {
                "id": ont.get("ontologyId"),
                "name": config.get("title") or config.get("preferredPrefix"),
                "prefix": config.get("preferredPrefix"),
            }
            if config.get("description"):
                result["description"] = config["description"]
            if config.get("homepage"):
                result["homepage"] = config["homepage"]
            results.append(result)

        page_info = data.get("page", {})

        return json.dumps(
            {
                "total": page_info.get("totalElements", len(results)),
                "ontologies": results,
            },
            indent=2,
        )

    @mcp.tool()
    def suggest_ontology_term(query: str, ontology: str | None = None) -> str:
        """Get autocomplete suggestions for ontology terms.

        Provides fast suggestions as you type, useful for building
        autocomplete functionality or quickly finding term matches. Asks the
        configured sources, so a project's own vocabulary is suggested too.

        Args:
            query: Partial term to get suggestions for (e.g., "drou" for drought).
            ontology: Optional ontology ID to restrict suggestions (e.g., "pato", "go").

        Returns:
            JSON with suggested terms including IDs and labels.
        """
        from metaseed.services.terms import get_term_source

        hits = get_term_source().search_sync(query, ontology, 10)

        return json.dumps(
            {
                "query": query,
                "ontology": ontology,
                "suggestions": [
                    {
                        "id": hit.id,
                        "label": hit.label,
                        "ontology": hit.ontology,
                        "source": hit.source,
                    }
                    for hit in hits
                ],
            },
            indent=2,
        )

    @mcp.tool()
    def validate_ontology_terms() -> str:
        """Check ontology_term field values against the configured term sources.

        For every ontology_term field that has a value, asks the application's
        term router (local vocabularies first, then OLS) whether the value is a
        real term in the ontologies the field declares, and within the branch
        it declares if any. Three outcomes per value, never two:

        - ``valid: true`` — confirmed a term where the field allows.
        - ``valid: false`` — demonstrably wrong, with a message saying why and
          suggested replacements.
        - ``checked: false`` (``valid: null``) — nobody could say: the service
          did not answer, or no configured source carries the ontology. An
          outage must never be reported as invalid data.

        Returns:
            JSON with total_checked and results of {entity, type, field, value,
            valid, checked, message, suggestions:[{id, label, source}]}.
        """
        from metaseed.services.term_check import Outcome, check_term
        from metaseed.services.terms import get_term_source

        session = current_state()
        try:
            facade = session.get_or_create_facade()
            source = get_term_source()
            results = []
            for node in session.nodes_by_id.values():
                helper = getattr(facade, node.entity_type, None)
                if not helper or not node.instance:
                    continue
                data = node.instance.model_dump(exclude_none=True)
                for field in helper.all_fields:
                    info = helper.field_info(field)
                    if info.get("type") != "ontology_term":
                        continue
                    value = data.get(field)
                    if not value or not isinstance(value, str):
                        continue

                    ontologies = info.get("ontologies")
                    verdict = check_term(
                        value, ontologies, source, within=info.get("within")
                    )

                    suggestions: list[dict[str, Any]] = []
                    if verdict.is_problem:
                        # Only a wrong value needs replacements; suggesting
                        # alternatives for a term nobody could check would
                        # read as doubt the check has not earned.
                        try:
                            hits = source.search_sync(
                                value,
                                ",".join(o.lower() for o in ontologies)
                                if ontologies
                                else None,
                                5,
                            )
                        except Exception:
                            hits = []
                        suggestions = [
                            {"id": h.id, "label": h.label, "source": h.source}
                            for h in hits
                        ]

                    checked = verdict.outcome is not Outcome.NOT_CHECKED
                    results.append(
                        {
                            "entity": node.label or node.id,
                            "type": node.entity_type,
                            "field": field,
                            "value": value,
                            "valid": (verdict.outcome is Outcome.OK)
                            if checked
                            else None,
                            "checked": checked,
                            "message": verdict.message,
                            "suggestions": suggestions,
                        }
                    )

            return json.dumps(
                {"total_checked": len(results), "results": results}, indent=2
            )
        except Exception as e:
            return json.dumps({"error": str(e)})
