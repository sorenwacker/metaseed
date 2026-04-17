"""Tests for the graph visualization feature."""

import pytest
from httpx import ASGITransport, AsyncClient

from metaseed.ui.routes import create_app
from metaseed.ui.services.graph import build_graph, truncate
from metaseed.ui.state import AppState


class TestTruncate:
    """Tests for truncate helper function."""

    def test_short_text_unchanged(self) -> None:
        """Short text should not be truncated."""
        assert truncate("short", 25) == "short"

    def test_exact_length_unchanged(self) -> None:
        """Text at exactly max length should not be truncated."""
        text = "a" * 25
        assert truncate(text, 25) == text

    def test_long_text_truncated(self) -> None:
        """Long text should be truncated with ellipsis."""
        text = "a" * 30
        result = truncate(text, 25)
        # Truncation takes first 24 chars + "..." = 27 chars total
        assert result.endswith("...")
        assert len(result) < len(text)

    def test_custom_max_length(self) -> None:
        """Custom max length should be respected."""
        assert truncate("abcdefghij", 5) == "abcd..."


class TestBuildGraph:
    """Tests for build_graph function."""

    def test_empty_state_returns_empty_graph(self) -> None:
        """Empty state should return empty nodes and edges."""
        state = AppState(profile="miappe")
        result = build_graph(state)
        assert result == {"nodes": [], "edges": []}

    def test_single_entity_creates_node(self) -> None:
        """Single entity should create one node with no edges."""
        state = AppState(profile="miappe")
        facade = state.get_or_create_facade()
        instance = facade.Investigation.create(
            unique_id="inv1",
            title="Test Investigation",
            miappe_version=facade.version,
        )
        state.add_node("Investigation", instance)

        result = build_graph(state)
        assert len(result["nodes"]) == 1
        assert len(result["edges"]) == 0
        assert result["nodes"][0]["group"] == "Investigation"

    def test_nested_entities_create_edges(self) -> None:
        """Nested entities should create nodes with connecting edges."""
        state = AppState(profile="miappe")
        facade = state.get_or_create_facade()

        instance = facade.Investigation.create(
            unique_id="inv1",
            title="Test Investigation",
            miappe_version=facade.version,
            studies=[
                {
                    "unique_id": "study1",
                    "title": "Test Study",
                    "start_date": "2024-01-01",
                    "investigation_id": "inv1",
                }
            ],
        )
        state.add_node("Investigation", instance)

        result = build_graph(state)
        # Should have Investigation and Study nodes
        assert len(result["nodes"]) >= 2
        # Should have at least one edge connecting them
        assert len(result["edges"]) >= 1

    def test_node_labels_truncated(self) -> None:
        """Long labels should be truncated."""
        state = AppState(profile="miappe")
        facade = state.get_or_create_facade()
        long_title = "A" * 50
        instance = facade.Investigation.create(
            unique_id="inv1",
            title=long_title,
            miappe_version=facade.version,
        )
        state.add_node("Investigation", instance)

        result = build_graph(state)
        # Label should be shorter than original
        assert len(result["nodes"][0]["label"]) < len(long_title)
        # Label should end with ellipsis
        assert result["nodes"][0]["label"].endswith("...")


class TestGraphAPI:
    """Tests for /api/graph endpoint."""

    @pytest.fixture
    def state(self) -> AppState:
        """Create fresh AppState."""
        return AppState(profile="miappe")

    @pytest.fixture
    def app(self, state: AppState):
        """Create app with test state."""
        return create_app(state)

    @pytest.mark.asyncio
    async def test_graph_endpoint_returns_json(self, app, state: AppState) -> None:
        """Graph endpoint should return JSON response."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/graph")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    @pytest.mark.asyncio
    async def test_graph_endpoint_empty_state(self, app, state: AppState) -> None:
        """Graph endpoint with empty state returns empty arrays."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/graph")

        data = response.json()
        assert data == {"nodes": [], "edges": []}

    @pytest.mark.asyncio
    async def test_graph_endpoint_with_entity(self, app, state: AppState) -> None:
        """Graph endpoint with entity returns nodes."""
        facade = state.get_or_create_facade()
        instance = facade.Investigation.create(
            unique_id="inv1",
            title="Test Investigation",
            miappe_version=facade.version,
        )
        state.add_node("Investigation", instance)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/graph")

        data = response.json()
        assert len(data["nodes"]) >= 1
        assert data["nodes"][0]["group"] == "Investigation"


class TestGraphWithNestedData:
    """Tests for graph visualization with nested entity data."""

    def test_graph_with_deeply_nested_entities(self) -> None:
        """Graph should handle multiple levels of nesting."""
        state = AppState(profile="miappe")
        facade = state.get_or_create_facade()

        # Create an investigation with nested studies and observation units
        instance = facade.Investigation.create(
            unique_id="inv1",
            title="Test Investigation",
            miappe_version=facade.version,
            studies=[
                {
                    "unique_id": "study1",
                    "title": "Test Study",
                    "start_date": "2024-01-01",
                    "investigation_id": "inv1",
                    "observation_units": [
                        {
                            "unique_id": "ou1",
                            "study_id": "study1",
                            "observation_unit_type": "plot",
                        }
                    ],
                }
            ],
        )
        state.add_node("Investigation", instance)

        result = build_graph(state)
        # Should have Investigation, Study, and ObservationUnit
        assert len(result["nodes"]) >= 3
        # Should have edges connecting them
        assert len(result["edges"]) >= 2

        # Check entity types
        entity_types = {node["group"] for node in result["nodes"]}
        assert "Investigation" in entity_types
        assert "Study" in entity_types
        assert "ObservationUnit" in entity_types

    def test_graph_nodes_have_required_vis_fields(self) -> None:
        """All nodes should have fields required by vis.js."""
        state = AppState(profile="miappe")
        facade = state.get_or_create_facade()
        instance = facade.Investigation.create(
            unique_id="inv1",
            title="Test",
            miappe_version=facade.version,
        )
        state.add_node("Investigation", instance)

        result = build_graph(state)
        for node in result["nodes"]:
            assert "id" in node
            assert "label" in node
            assert "title" in node
            assert "group" in node

    def test_graph_edges_have_required_vis_fields(self) -> None:
        """All edges should have from and to fields."""
        state = AppState(profile="miappe")
        facade = state.get_or_create_facade()
        instance = facade.Investigation.create(
            unique_id="inv1",
            title="Test",
            miappe_version=facade.version,
            studies=[
                {
                    "unique_id": "study1",
                    "title": "Test Study",
                    "start_date": "2024-01-01",
                    "investigation_id": "inv1",
                }
            ],
        )
        state.add_node("Investigation", instance)

        result = build_graph(state)
        for edge in result["edges"]:
            assert "from" in edge
            assert "to" in edge
