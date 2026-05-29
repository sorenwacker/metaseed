"""Tests for the graph visualization feature."""

import pytest
from httpx import ASGITransport, AsyncClient

from metaseed.ui.app import create_app
from metaseed.ui.services.graph import build_graph
from metaseed.ui.state import AppState


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
        """Child entities in tree should create nodes with connecting edges."""
        state = AppState(profile="miappe")
        facade = state.get_or_create_facade()

        # Create Investigation node
        inv_instance = facade.Investigation.create(
            unique_id="inv1",
            title="Test Investigation",
            miappe_version=facade.version,
        )
        inv_node = state.add_node("Investigation", inv_instance)

        # Create Study as child of Investigation
        study_instance = facade.Study.create(
            unique_id="study1",
            title="Test Study",
            start_date="2024-01-01",
            investigation_id="inv1",
        )
        state.add_node("Study", study_instance, parent_id=inv_node.id)

        result = build_graph(state)
        # Should have Investigation and Study nodes
        assert len(result["nodes"]) == 2
        # Should have edges: 1 parent-child + 1 investigation_id reference
        assert len(result["edges"]) == 2

    def test_node_labels_truncated(self) -> None:
        """Long labels should be truncated."""
        state = AppState(profile="miappe")
        facade = state.get_or_create_facade()
        # First field (unique_id) is used as label per convention, so make it long
        long_id = "A" * 50
        instance = facade.Investigation.create(
            unique_id=long_id,
            title="Test Investigation",
            miappe_version=facade.version,
        )
        state.add_node("Investigation", instance)

        result = build_graph(state)
        assert len(result["nodes"]) == 1
        # Label should be shorter than original
        assert len(result["nodes"][0]["label"]) < len(long_id)
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
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["group"] == "Investigation"


class TestGraphWithNestedData:
    """Tests for graph visualization with nested entity data."""

    def test_graph_with_deeply_nested_entities(self) -> None:
        """Graph should handle multiple levels of tree nesting."""
        state = AppState(profile="miappe")
        facade = state.get_or_create_facade()

        # Create Investigation node
        inv_instance = facade.Investigation.create(
            unique_id="inv1",
            title="Test Investigation",
            miappe_version=facade.version,
        )
        inv_node = state.add_node("Investigation", inv_instance)

        # Create Study as child of Investigation
        study_instance = facade.Study.create(
            unique_id="study1",
            title="Test Study",
            start_date="2024-01-01",
            investigation_id="inv1",
        )
        study_node = state.add_node("Study", study_instance, parent_id=inv_node.id)

        # Create ObservationUnit as child of Study
        ou_instance = facade.ObservationUnit.create(
            unique_id="ou1",
            study_id="study1",
            observation_unit_type="plot",
        )
        state.add_node("ObservationUnit", ou_instance, parent_id=study_node.id)

        result = build_graph(state)
        # Should have Investigation, Study, and ObservationUnit
        assert len(result["nodes"]) == 3
        # Should have edges: 2 parent-child + 1 investigation_id ref + 1 study_id ref
        assert len(result["edges"]) == 4

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

        # Create Investigation node
        inv_instance = facade.Investigation.create(
            unique_id="inv1",
            title="Test",
            miappe_version=facade.version,
        )
        inv_node = state.add_node("Investigation", inv_instance)

        # Create Study as child of Investigation
        study_instance = facade.Study.create(
            unique_id="study1",
            title="Test Study",
            start_date="2024-01-01",
            investigation_id="inv1",
        )
        state.add_node("Study", study_instance, parent_id=inv_node.id)

        result = build_graph(state)
        for edge in result["edges"]:
            assert "from" in edge
            assert "to" in edge
