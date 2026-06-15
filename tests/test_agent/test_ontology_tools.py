"""Tests for ontology lookup MCP tools."""

import json
from unittest.mock import patch

import pytest

from metaseed.agent.mcp.server import create_server

from .helpers import get_tool


class TestOntologyTools:
    """Tests for OLS4 ontology lookup tools."""

    @pytest.fixture
    def server(self):
        """Create MCP server instance."""
        return create_server()

    def test_search_ontology_tool_exists(self, server) -> None:
        """Search ontology tool is registered."""
        search_fn = get_tool(server, "search_ontology")
        assert search_fn is not None

    def test_get_ontology_term_tool_exists(self, server) -> None:
        """Get ontology term tool is registered."""
        get_term_fn = get_tool(server, "get_ontology_term")
        assert get_term_fn is not None

    def test_list_ontologies_tool_exists(self, server) -> None:
        """List ontologies tool is registered."""
        list_fn = get_tool(server, "list_ontologies")
        assert list_fn is not None

    def test_suggest_ontology_term_tool_exists(self, server) -> None:
        """Suggest ontology term tool is registered."""
        suggest_fn = get_tool(server, "suggest_ontology_term")
        assert suggest_fn is not None

    def test_search_ontology_returns_results(self, server) -> None:
        """Search ontology returns structured results."""
        search_fn = get_tool(server, "search_ontology")

        mock_response = {
            "response": {
                "numFound": 2,
                "docs": [
                    {
                        "obo_id": "PATO:0000015",
                        "label": "temperature",
                        "ontology_prefix": "PATO",
                        "iri": "http://purl.obolibrary.org/obo/PATO_0000015",
                        "description": ["A quality of thermal energy"],
                    },
                    {
                        "obo_id": "PATO:0000146",
                        "label": "cold",
                        "ontology_prefix": "PATO",
                        "iri": "http://purl.obolibrary.org/obo/PATO_0000146",
                    },
                ],
            }
        }

        with patch(
            "metaseed.agent.mcp.tools.ontology._make_request",
            return_value=mock_response,
        ):
            result = search_fn(query="temperature", ontology="pato")
            data = json.loads(result)

            assert data["query"] == "temperature"
            assert data["ontology"] == "pato"
            assert data["total_found"] == 2
            assert len(data["results"]) == 2
            assert data["results"][0]["id"] == "PATO:0000015"
            assert data["results"][0]["label"] == "temperature"
            assert data["results"][0]["ontology"] == "PATO"

    def test_search_ontology_handles_error(self, server) -> None:
        """Search ontology handles API errors."""
        search_fn = get_tool(server, "search_ontology")

        with patch(
            "metaseed.agent.mcp.tools.ontology._make_request", return_value=None
        ):
            result = search_fn(query="test")
            data = json.loads(result)

            assert "error" in data

    def test_get_ontology_term_curie_format(self, server) -> None:
        """Get ontology term accepts CURIE format."""
        get_fn = get_tool(server, "get_ontology_term")

        mock_response = {
            "obo_id": "PATO:0000015",
            "label": "temperature",
            "ontology_prefix": "PATO",
            "iri": "http://purl.obolibrary.org/obo/PATO_0000015",
            "description": ["A quality of thermal energy"],
            "synonyms": ["thermal quality"],
            "is_obsolete": False,
        }

        with patch(
            "metaseed.agent.mcp.tools.ontology._make_request",
            return_value=mock_response,
        ):
            result = get_fn(term_id="PATO:0000015")
            data = json.loads(result)

            assert data["id"] == "PATO:0000015"
            assert data["label"] == "temperature"
            assert data["definition"] == "A quality of thermal energy"
            assert data["synonyms"] == ["thermal quality"]
            assert data["is_obsolete"] is False

    def test_get_ontology_term_iri_format(self, server) -> None:
        """Get ontology term accepts IRI format."""
        get_fn = get_tool(server, "get_ontology_term")

        mock_response = {
            "obo_id": "GO:0008150",
            "label": "biological_process",
            "ontology_prefix": "GO",
            "iri": "http://purl.obolibrary.org/obo/GO_0008150",
        }

        with patch(
            "metaseed.agent.mcp.tools.ontology._make_request",
            return_value=mock_response,
        ):
            result = get_fn(term_id="http://purl.obolibrary.org/obo/GO_0008150")
            data = json.loads(result)

            assert data["id"] == "GO:0008150"
            assert data["label"] == "biological_process"

    def test_get_ontology_term_invalid_format(self, server) -> None:
        """Get ontology term handles invalid format."""
        get_fn = get_tool(server, "get_ontology_term")

        result = get_fn(term_id="invalid")
        data = json.loads(result)

        assert "error" in data
        assert "Invalid" in data["error"]

    def test_get_ontology_term_not_found(self, server) -> None:
        """Get ontology term handles not found."""
        get_fn = get_tool(server, "get_ontology_term")

        with patch(
            "metaseed.agent.mcp.tools.ontology._make_request", return_value=None
        ):
            result = get_fn(term_id="PATO:9999999")
            data = json.loads(result)

            assert "error" in data
            assert "not found" in data["error"].lower()

    def test_list_ontologies_returns_list(self, server) -> None:
        """List ontologies returns structured list."""
        list_fn = get_tool(server, "list_ontologies")

        mock_response = {
            "_embedded": {
                "ontologies": [
                    {
                        "ontologyId": "go",
                        "config": {
                            "title": "Gene Ontology",
                            "preferredPrefix": "GO",
                            "description": "The Gene Ontology",
                            "homepage": "http://geneontology.org",
                        },
                    },
                    {
                        "ontologyId": "pato",
                        "config": {
                            "title": "Phenotype And Trait Ontology",
                            "preferredPrefix": "PATO",
                        },
                    },
                ]
            },
            "page": {"totalElements": 2},
        }

        with patch(
            "metaseed.agent.mcp.tools.ontology._make_request",
            return_value=mock_response,
        ):
            result = list_fn(rows=10)
            data = json.loads(result)

            assert data["total"] == 2
            assert len(data["ontologies"]) == 2
            assert data["ontologies"][0]["id"] == "go"
            assert data["ontologies"][0]["name"] == "Gene Ontology"
            assert data["ontologies"][0]["prefix"] == "GO"

    def test_list_ontologies_handles_error(self, server) -> None:
        """List ontologies handles API errors."""
        list_fn = get_tool(server, "list_ontologies")

        with patch(
            "metaseed.agent.mcp.tools.ontology._make_request", return_value=None
        ):
            result = list_fn()
            data = json.loads(result)

            assert "error" in data

    def test_suggest_ontology_term_returns_suggestions(self, server) -> None:
        """Suggest ontology term returns suggestions."""
        suggest_fn = get_tool(server, "suggest_ontology_term")

        mock_response = {
            "response": {
                "docs": [
                    {
                        "obo_id": "PATO:0000015",
                        "label": "temperature",
                        "ontology_prefix": "PATO",
                    },
                    {
                        "obo_id": "PATO:0000016",
                        "label": "temperature tolerance",
                        "ontology_prefix": "PATO",
                    },
                ]
            }
        }

        with patch(
            "metaseed.agent.mcp.tools.ontology._make_request",
            return_value=mock_response,
        ):
            result = suggest_fn(query="temp", ontology="pato")
            data = json.loads(result)

            assert data["query"] == "temp"
            assert data["ontology"] == "pato"
            assert len(data["suggestions"]) == 2
            assert data["suggestions"][0]["label"] == "temperature"

    def test_validate_ontology_terms_checks_filled_values(self, server) -> None:
        """Ontology-term fields are checked against OLS with suggestions."""
        from metaseed.agent.mcp.server import get_entity_service, set_mcp_state
        from metaseed.ui.state import AppState

        set_mcp_state(AppState(profile="miappe", version="1.2"))
        server = create_server()
        svc = get_entity_service()
        inv = svc.create_entity("Investigation", {"unique_id": "INV-1", "title": "I"})
        stu = svc.create_entity(
            "Study",
            {"unique_id": "STU-1", "investigation_id": "INV-1", "title": "S"},
            parent_id=inv["id"],
        )
        svc.create_entity(
            "ObservedVariable",
            {
                "unique_id": "var-1",
                "study_id": "STU-1",
                "name": "plant height",
                "trait_accession_number": "plant height",
            },
            parent_id=stu["id"],
        )

        fake = {"response": {"docs": [{"obo_id": "TO:0000207", "label": "plant height"}]}}
        with patch(
            "metaseed.agent.mcp.tools.ontology._make_request", return_value=fake
        ):
            out = json.loads(get_tool(server, "validate_ontology_terms")())

        assert out["total_checked"] == 1
        result = out["results"][0]
        assert result["field"] == "trait_accession_number"
        assert result["valid"] is True
        assert result["suggestions"][0]["id"] == "TO:0000207"

    def test_validate_ontology_terms_fails_open(self, server) -> None:
        """When OLS is unreachable, fields are reported without suggestions."""
        from metaseed.agent.mcp.server import get_entity_service, set_mcp_state
        from metaseed.ui.state import AppState

        set_mcp_state(AppState(profile="miappe", version="1.2"))
        server = create_server()
        svc = get_entity_service()
        inv = svc.create_entity("Investigation", {"unique_id": "INV-1", "title": "I"})
        stu = svc.create_entity(
            "Study",
            {"unique_id": "STU-1", "investigation_id": "INV-1", "title": "S"},
            parent_id=inv["id"],
        )
        svc.create_entity(
            "ObservedVariable",
            {
                "unique_id": "var-1",
                "study_id": "STU-1",
                "name": "h",
                "trait_accession_number": "obscure value",
            },
            parent_id=stu["id"],
        )

        with patch(
            "metaseed.agent.mcp.tools.ontology._make_request", return_value=None
        ):
            out = json.loads(get_tool(server, "validate_ontology_terms")())

        result = out["results"][0]
        assert result["valid"] is False
        assert result["suggestions"] == []

    def test_search_limits_rows(self, server) -> None:
        """Search ontology limits rows to max 100."""
        search_fn = get_tool(server, "search_ontology")

        with patch(
            "metaseed.agent.mcp.tools.ontology._make_request",
            return_value={"response": {"numFound": 0, "docs": []}},
        ) as mock:
            search_fn(query="test", rows=200)

            # Check that rows was capped at 100
            call_args = mock.call_args
            # Args format: call('/search', {'q': ..., 'rows': 100, ...})
            params = call_args[0][1]  # Second positional argument
            assert params["rows"] == 100


class TestOntologyToolsIntegration:
    """Integration tests for ontology tools (require network)."""

    @pytest.fixture
    def server(self):
        """Create MCP server instance."""
        return create_server()

    @pytest.mark.skip(reason="Requires network access to OLS4 API")
    def test_search_real_api(self, server) -> None:
        """Search using real OLS4 API."""
        search_fn = get_tool(server, "search_ontology")

        result = search_fn(query="drought", ontology="pato", rows=5)
        data = json.loads(result)

        assert "results" in data
        assert data["total_found"] > 0

    @pytest.mark.skip(reason="Requires network access to OLS4 API")
    def test_get_term_real_api(self, server) -> None:
        """Get term using real OLS4 API."""
        get_fn = get_tool(server, "get_ontology_term")

        result = get_fn(term_id="PATO:0000015")
        data = json.loads(result)

        assert data["id"] == "PATO:0000015"
        assert "label" in data

    @pytest.mark.skip(reason="Requires network access to OLS4 API")
    def test_list_ontologies_real_api(self, server) -> None:
        """List ontologies using real OLS4 API."""
        list_fn = get_tool(server, "list_ontologies")

        result = list_fn(rows=10)
        data = json.loads(result)

        assert data["total"] > 0
        assert len(data["ontologies"]) > 0
