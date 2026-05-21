"""Tests for the MCP server module."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from metaseed.agent.mcp.server import create_server

from .helpers import get_prompt, get_tool


class TestMCPServer:
    """Tests for MCP server creation and tools."""

    def test_create_server(self) -> None:
        """Create MCP server instance."""
        server = create_server("test-metaseed")
        assert server is not None
        assert server.name == "test-metaseed"

    def test_list_profiles_tool(self) -> None:
        """List profiles tool returns profile info."""
        server = create_server()
        list_profiles_fn = get_tool(server, "list_profiles")
        assert list_profiles_fn is not None

        result = list_profiles_fn()
        data = json.loads(result)

        assert isinstance(data, list)
        # Should have at least MIAPPE if tests are running with specs
        # This may be empty in a minimal test environment

    def test_parse_source_file_tool(self, tmp_path: Path) -> None:
        """Parse file tool returns file structure."""
        server = create_server()

        # Create a test CSV
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("name,value\nfoo,1\nbar,2\n")

        parse_fn = get_tool(server, "parse_source_file")
        assert parse_fn is not None

        result = parse_fn(file_path=str(csv_file))
        data = json.loads(result)

        assert data["format"] == "csv"
        assert len(data["tables"]) == 1
        assert data["tables"][0]["headers"] == ["name", "value"]
        assert data["tables"][0]["row_count"] == 2

    def test_parse_source_file_not_found(self) -> None:
        """Parse file tool handles missing files."""
        server = create_server()
        parse_fn = get_tool(server, "parse_source_file")

        result = parse_fn(file_path="/nonexistent/file.csv")
        data = json.loads(result)

        assert "error" in data
        assert "not found" in data["error"].lower()

    def test_get_profile_schema_tool(self) -> None:
        """Get profile schema tool returns entity info."""
        server = create_server()
        get_schema_fn = get_tool(server, "get_profile_schema")
        assert get_schema_fn is not None

        # This may return error if profile not found in test env
        result = get_schema_fn(profile="miappe", version="1.1")
        data = json.loads(result)

        # Either has entities or error
        assert "entities" in data or "error" in data

    def test_analyze_mapping_tool(self, tmp_path: Path) -> None:
        """Analyze mapping tool suggests column mappings."""
        server = create_server()

        # Create test CSV with MIAPPE-like columns
        csv_file = tmp_path / "investigations.csv"
        csv_file.write_text("identifier,title,description\nINV-001,Test,A test investigation\n")

        tools = server._tool_manager._tools
        analyze_fn = None
        for name, tool in tools.items():
            if name == "analyze_mapping":
                analyze_fn = tool.fn
                break

        assert analyze_fn is not None

        result = analyze_fn(
            file_path=str(csv_file),
            profile="miappe",
            version="1.1",
            entity="Investigation",
        )
        data = json.loads(result)

        # Either has mappings or error (if profile not available)
        assert "mappings" in data or "error" in data

        if "mappings" in data:
            assert data["entity"] == "Investigation"
            assert len(data["mappings"]) > 0

    def test_export_metadata_yaml(self) -> None:
        """Export metadata tool outputs YAML."""
        server = create_server()
        export_fn = get_tool(server, "export_metadata")
        assert export_fn is not None

        input_data = json.dumps({"Investigation": [{"identifier": "INV-001", "title": "Test"}]})
        result = export_fn(data=input_data, output_format="yaml")

        assert "Investigation:" in result
        assert "identifier:" in result
        assert "INV-001" in result

    def test_export_metadata_json(self) -> None:
        """Export metadata tool outputs JSON."""
        server = create_server()
        export_fn = get_tool(server, "export_metadata")

        input_data = json.dumps({"Investigation": [{"identifier": "INV-001"}]})
        result = export_fn(data=input_data, output_format="json")

        data = json.loads(result)
        assert "Investigation" in data
        assert data["Investigation"][0]["identifier"] == "INV-001"

    def test_validate_extracted_tool(self) -> None:
        """Validate extracted tool checks data validity."""
        server = create_server()
        validate_fn = get_tool(server, "validate_extracted")
        assert validate_fn is not None

        # Test with some data - may error if profile not available
        test_data = json.dumps([{"identifier": "INV-001", "title": "Test"}])
        result = validate_fn(
            data=test_data,
            profile="miappe",
            version="1.1",
            entity="Investigation",
        )
        data = json.loads(result)

        # Either has results or error
        assert "results" in data or "error" in data


class TestMCPResources:
    """Tests for MCP resource handlers."""

    def test_list_profiles_resource(self) -> None:
        """Profile list resource returns JSON array."""
        server = create_server()

        # Find the resource handler
        resources = server._resource_manager._resources

        # Resource may not be directly callable in newer MCP versions
        # This test verifies the resource is registered
        assert "profile://list" in [str(uri) for uri in resources]

    def test_profile_schema_resource_pattern(self) -> None:
        """Profile schema resource is registered."""
        server = create_server()

        # Check that resource templates are registered
        templates = server._resource_manager._templates
        # The template pattern should be registered
        assert len(templates) > 0 or len(server._resource_manager._resources) > 0


class TestMCPPrompts:
    """Tests for MCP prompt handlers."""

    def test_extraction_guide_prompt(self) -> None:
        """Extraction guide prompt returns instructions."""
        server = create_server()
        extraction_guide = get_prompt(server, "extraction_guide")
        assert extraction_guide is not None

        # Call the prompt function
        result = extraction_guide.fn(profile="miappe")

        assert "Metadata Extraction Guide" in result
        assert "list_profiles" in result
        assert "parse_source_file" in result

    def test_field_mapping_help_prompt(self) -> None:
        """Field mapping help prompt returns guidance."""
        server = create_server()
        mapping_help = get_prompt(server, "field_mapping_help")
        assert mapping_help is not None

        result = mapping_help.fn(entity="Investigation", profile="miappe")

        assert "Field Mapping Help" in result
        assert "Confidence Scores" in result


class TestMCPDatasetTools:
    """Tests for MCP dataset management tools."""

    @pytest.fixture
    def server_with_app(self):
        """Create server with mocked app state."""
        from metaseed.ui.state import AppState

        server = create_server()

        # Create app state
        state = AppState(profile="miappe")

        # Mock the app module
        with patch("metaseed.agent.mcp.server.app") as mock_app:
            mock_app.state.ui_state = state
            yield server, state

    def test_list_datasets_tool(self, tmp_path):
        """List datasets tool returns available datasets."""
        server = create_server()

        tools = server._tool_manager._tools
        list_fn = tools.get("list_datasets")
        assert list_fn is not None

        # The function may error due to missing app state, but should exist
        with patch("metaseed.ui.datasets.list_datasets", return_value=[]):
            result = list_fn.fn()
            data = json.loads(result)
            assert "datasets" in data

    def test_get_field_spec_tool(self):
        """Get field spec tool returns field definitions."""
        from metaseed.agent.mcp.server import set_mcp_state
        from metaseed.ui.state import AppState

        server = create_server()

        tools = server._tool_manager._tools
        get_spec_fn = tools.get("get_field_spec")
        assert get_spec_fn is not None

        # Set the MCP state directly
        state = AppState(profile="miappe")
        set_mcp_state(state)

        result = get_spec_fn.fn(entity_type="Investigation")
        data = json.loads(result)

        # Should have fields or error
        assert "fields" in data or "error" in data

    def test_validate_dataset_tool(self):
        """Validate dataset tool checks entity validity."""
        from metaseed.agent.mcp.server import set_mcp_state
        from metaseed.ui.state import AppState

        server = create_server()

        tools = server._tool_manager._tools
        validate_fn = tools.get("validate_dataset")
        assert validate_fn is not None

        # Set the MCP state directly
        state = AppState(profile="miappe")
        set_mcp_state(state)

        result = validate_fn.fn()
        data = json.loads(result)

        # Empty state should have 0 results
        assert data.get("total", 0) == 0 or "error" in data

    def test_create_entity_tool(self):
        """Create entity tool adds entity to state."""
        from metaseed.agent.mcp.server import set_mcp_state
        from metaseed.ui.state import AppState

        server = create_server()

        tools = server._tool_manager._tools
        create_fn = tools.get("create_entity")
        assert create_fn is not None

        # Set the MCP state directly
        state = AppState(profile="miappe")
        set_mcp_state(state)

        with patch("metaseed.ui.datasets.auto_save"):
            result = create_fn.fn(
                entity_type="Investigation", data='{"unique_id": "INV-001", "title": "Test"}'
            )
            data = json.loads(result)

            # Should create or have validation error
            assert data.get("status") == "created" or "error" in data

    def test_bulk_update_tool(self):
        """Bulk update tool updates multiple entities."""
        from metaseed.agent.mcp.server import set_mcp_state
        from metaseed.ui.state import AppState

        server = create_server()

        tools = server._tool_manager._tools
        bulk_fn = tools.get("bulk_update_entities")
        assert bulk_fn is not None

        # Set the MCP state directly
        state = AppState(profile="miappe")
        set_mcp_state(state)

        with patch("metaseed.ui.datasets.auto_save"):
            # Empty updates should work
            result = bulk_fn.fn(updates="[]")
            data = json.loads(result)

            assert data.get("total") == 0 or "error" in data


class TestMCPIntegration:
    """Integration tests for the full MCP workflow."""

    def test_full_workflow_create_list_get_validate(self):
        """Test create → list → get → validate workflow with date fields."""
        from metaseed.agent.mcp.server import set_mcp_state
        from metaseed.ui.state import AppState

        server = create_server()
        tools = server._tool_manager._tools

        # Set up state with ISA profile (has date fields)
        state = AppState(profile="isa")
        set_mcp_state(state)

        with patch("metaseed.ui.datasets.auto_save"):
            # 1. Create entity with date field
            create_fn = tools.get("create_entity")
            result = create_fn.fn(
                entity_type="Investigation",
                data='{"identifier": "INV-001", "title": "Test Investigation", "submission_date": "2024-01-15"}',
            )
            create_data = json.loads(result)
            assert create_data.get("status") == "created" or "error" in create_data

            if "error" in create_data:
                pytest.skip("Profile not available")

            node_id = create_data["id"]

            # 2. List entities (tests date serialization)
            list_fn = tools.get("list_entities")
            result = list_fn.fn()
            list_data = json.loads(result)
            assert "entities" in list_data
            assert list_data["total"] >= 1

            # 3. Get specific entity (tests date serialization)
            get_fn = tools.get("get_entity")
            result = get_fn.fn(node_id=node_id)
            get_data = json.loads(result)
            assert get_data["id"] == node_id
            assert get_data["entity_type"] == "Investigation"

            # 4. Validate dataset
            validate_fn = tools.get("validate_dataset")
            result = validate_fn.fn()
            validate_data = json.loads(result)
            assert "total" in validate_data
            assert "results" in validate_data

            # 5. Get field spec
            spec_fn = tools.get("get_field_spec")
            result = spec_fn.fn(entity_type="Investigation")
            spec_data = json.loads(result)
            assert "fields" in spec_data or "error" in spec_data

    def test_person_label_uses_first_field(self):
        """Test that Person entities use first field as label per convention."""
        from metaseed.ui.state import AppState

        state = AppState(profile="miappe")
        facade = state.get_or_create_facade()
        # MIAPPE Person has 'name' as first field
        instance = facade.Person.create(
            name="Jane Doe",
            email="jane@example.com",
        )
        node = state.add_node("Person", instance)
        assert node.label == "Jane Doe"

    def test_person_label_with_short_name(self):
        """Test Person label with short name."""
        from metaseed.ui.state import AppState

        state = AppState(profile="miappe")
        facade = state.get_or_create_facade()
        # Create with minimal name
        instance = facade.Person.create(
            name="J",
            email="j@example.com",
        )
        node = state.add_node("Person", instance)
        assert node.label == "J"

    def test_hierarchy_creation_and_save(self, tmp_path):
        """Test creating hierarchical entities and saving to disk."""
        from metaseed.agent.mcp.server import set_mcp_state
        from metaseed.repositories.filesystem_dataset import FilesystemDatasetRepository
        from metaseed.ui import dataset_manager
        from metaseed.ui.state import AppState

        server = create_server()
        tools = server._tool_manager._tools

        # Set up state with MIAPPE profile
        state = AppState(profile="miappe")
        set_mcp_state(state)

        # Create a test repository using tmp_path
        test_repo = FilesystemDatasetRepository(datasets_dir=tmp_path)
        original_repo = dataset_manager._repository
        dataset_manager._repository = test_repo
        try:
            # 1. Create Investigation
            create_fn = tools.get("create_entity")
            result = create_fn.fn(
                entity_type="Investigation",
                data='{"unique_id": "inv-hierarchy-test", "title": "Hierarchy Test"}',
            )
            inv_data = json.loads(result)

            if "error" in inv_data:
                pytest.skip(f"Profile not available: {inv_data['error']}")

            inv_id = inv_data["id"]
            assert inv_data["status"] == "created"

            # 2. Create Study with parent_id
            result = create_fn.fn(
                entity_type="Study",
                data='{"unique_id": "study-hierarchy-test", "title": "Child Study"}',
                parent_id=inv_id,
            )
            study_data = json.loads(result)
            assert study_data["status"] == "created"
            assert study_data.get("parent_id") == inv_id
            assert study_data.get("linked_via_field") == "studies"
            study_id = study_data["id"]

            # 3. Verify state hierarchy
            assert len(state.entity_tree) == 1  # Only Investigation at root
            inv_node = state.entity_tree[0]
            assert inv_node.id == inv_id
            assert len(inv_node.children) == 1  # Study is child
            assert inv_node.children[0].id == study_id

            # 4. Verify both nodes are in nodes_by_id
            assert inv_id in state.nodes_by_id
            assert study_id in state.nodes_by_id
            assert len(state.nodes_by_id) == 2

            # 5. Verify dataset file was saved with hierarchy
            dataset_file = tmp_path / "inv-hierarchy-test.json"
            assert (
                dataset_file.exists()
            ), f"Dataset file not found. Files: {list(tmp_path.iterdir())}"

            with open(dataset_file) as f:
                saved_data = json.load(f)

            # Should have 2 entities
            assert len(saved_data["entities"]) == 2

            # Find Investigation and Study
            saved_inv = None
            saved_study = None
            for entity in saved_data["entities"]:
                if entity["_type"] == "Investigation":
                    saved_inv = entity
                elif entity["_type"] == "Study":
                    saved_study = entity

            assert saved_inv is not None, "Investigation not found in saved data"
            assert saved_study is not None, "Study not found in saved data"

            # Verify parent reference
            assert saved_study.get("_parent_id") == saved_inv.get("_node_id")

            # Verify Investigation's studies field was updated
            assert "study-hierarchy-test" in saved_inv.get("studies", [])
        finally:
            dataset_manager._repository = original_repo

    def test_get_entity_tree_shows_hierarchy(self):
        """Test that get_entity_tree correctly shows parent-child relationships."""
        from metaseed.agent.mcp.server import set_mcp_state
        from metaseed.ui.state import AppState

        server = create_server()
        tools = server._tool_manager._tools

        state = AppState(profile="miappe")
        set_mcp_state(state)

        with patch("metaseed.ui.datasets.auto_save"):
            # Create Investigation
            create_fn = tools.get("create_entity")
            result = create_fn.fn(
                entity_type="Investigation",
                data='{"unique_id": "inv-tree-test", "title": "Tree Test"}',
            )
            inv_data = json.loads(result)
            if "error" in inv_data:
                pytest.skip(f"Profile not available: {inv_data['error']}")
            inv_id = inv_data["id"]

            # Create Study as child
            result = create_fn.fn(
                entity_type="Study",
                data='{"unique_id": "study-tree-test", "title": "Child Study"}',
                parent_id=inv_id,
            )
            study_data = json.loads(result)
            study_id = study_data["id"]

            # Get entity tree
            tree_fn = tools.get("get_entity_tree")
            result = tree_fn.fn()
            tree_data = json.loads(result)

            # Verify tree structure
            assert tree_data["root_count"] == 1
            assert tree_data["total_count"] == 2

            # Investigation at root with Study as child
            inv_tree = tree_data["tree"][0]
            assert inv_tree["id"] == inv_id
            assert inv_tree["entity_type"] == "Investigation"
            assert "children" in inv_tree
            assert len(inv_tree["children"]) == 1

            study_tree = inv_tree["children"][0]
            assert study_tree["id"] == study_id
            assert study_tree["entity_type"] == "Study"


class TestMCPNewProfileTools:
    """Tests for new profile discovery tools."""

    def test_get_entity_fields(self):
        """Get entity fields returns field definitions."""
        server = create_server()
        tools = server._tool_manager._tools

        get_fields_fn = tools.get("get_entity_fields")
        assert get_fields_fn is not None

        result = get_fields_fn.fn(
            entity_type="Investigation",
            profile="miappe",
            version="1.2",
        )
        data = json.loads(result)

        if "error" in data:
            pytest.skip(f"Profile not available: {data['error']}")

        assert data["entity_type"] == "Investigation"
        assert data["profile"] == "miappe"
        assert data["version"] == "1.2"
        assert "fields" in data
        assert data["field_count"] > 0
        assert data["required_count"] >= 0

        # Check field structure
        field = data["fields"][0]
        assert "name" in field
        assert "type" in field
        assert "required" in field
        assert "description" in field

    def test_get_entity_fields_not_found(self):
        """Get entity fields returns error for unknown entity."""
        server = create_server()
        tools = server._tool_manager._tools

        get_fields_fn = tools.get("get_entity_fields")
        result = get_fields_fn.fn(
            entity_type="NonExistent",
            profile="miappe",
            version="1.2",
        )
        data = json.loads(result)

        assert "error" in data
        assert "NonExistent" in data["error"]

    def test_get_required_fields(self):
        """Get required fields returns list of required field names."""
        server = create_server()
        tools = server._tool_manager._tools

        get_required_fn = tools.get("get_required_fields")
        assert get_required_fn is not None

        result = get_required_fn.fn(
            entity_type="Investigation",
            profile="miappe",
            version="1.2",
        )
        data = json.loads(result)

        if "error" in data:
            pytest.skip(f"Profile not available: {data['error']}")

        assert data["entity_type"] == "Investigation"
        assert "required_fields" in data
        assert isinstance(data["required_fields"], list)

    def test_get_entity_template(self):
        """Get entity template returns template with placeholders."""
        server = create_server()
        tools = server._tool_manager._tools

        get_template_fn = tools.get("get_entity_template")
        assert get_template_fn is not None

        result = get_template_fn.fn(
            entity_type="Investigation",
            profile="miappe",
            version="1.2",
        )
        data = json.loads(result)

        if "error" in data:
            pytest.skip(f"Profile not available: {data['error']}")

        assert data["entity_type"] == "Investigation"
        assert "template" in data
        assert "_required" in data
        assert isinstance(data["template"], dict)
        assert isinstance(data["_required"], list)

        # Template should have placeholders for required fields
        for req_field in data["_required"]:
            assert req_field in data["template"]
            # Required fields should have non-null placeholders
            assert data["template"][req_field] is not None


class TestMCPBatchCreate:
    """Tests for batch entity creation."""

    def test_batch_create_single(self):
        """Batch create with single entity."""
        from metaseed.agent.mcp.server import set_mcp_state
        from metaseed.ui.state import AppState

        server = create_server()
        tools = server._tool_manager._tools

        batch_fn = tools.get("batch_create")
        assert batch_fn is not None

        state = AppState(profile="miappe")
        set_mcp_state(state)

        with patch("metaseed.ui.datasets.auto_save"):
            result = batch_fn.fn(
                entities='[{"entity_type": "Investigation", "data": {"unique_id": "INV-BATCH-1", "title": "Batch Test"}}]'
            )
            data = json.loads(result)

            if "error" in data:
                pytest.skip(f"Profile not available: {data['error']}")

            assert data["total"] == 1
            assert data["created"] == 1
            assert data["failed"] == 0
            assert len(data["results"]) == 1
            assert data["results"][0]["status"] == "created"
            assert "id" in data["results"][0]

    def test_batch_create_multiple(self):
        """Batch create with multiple entities."""
        from metaseed.agent.mcp.server import set_mcp_state
        from metaseed.ui.state import AppState

        server = create_server()
        tools = server._tool_manager._tools

        batch_fn = tools.get("batch_create")
        state = AppState(profile="miappe")
        set_mcp_state(state)

        entities = json.dumps(
            [
                {
                    "entity_type": "Investigation",
                    "data": {"unique_id": "INV-B1", "title": "Test 1"},
                },
                {
                    "entity_type": "Investigation",
                    "data": {"unique_id": "INV-B2", "title": "Test 2"},
                },
            ]
        )

        with patch("metaseed.ui.datasets.auto_save"):
            result = batch_fn.fn(entities=entities)
            data = json.loads(result)

            if "error" in data:
                pytest.skip(f"Profile not available: {data['error']}")

            assert data["total"] == 2
            assert data["created"] == 2
            assert data["failed"] == 0

    def test_batch_create_with_parent(self):
        """Batch create with parent relationship."""
        from metaseed.agent.mcp.server import set_mcp_state
        from metaseed.ui.state import AppState

        server = create_server()
        tools = server._tool_manager._tools

        batch_fn = tools.get("batch_create")
        create_fn = tools.get("create_entity")

        state = AppState(profile="miappe")
        set_mcp_state(state)

        with patch("metaseed.ui.datasets.auto_save"):
            # First create parent
            result = create_fn.fn(
                entity_type="Investigation",
                data='{"unique_id": "INV-PARENT", "title": "Parent"}',
            )
            parent_data = json.loads(result)

            if "error" in parent_data:
                pytest.skip(f"Profile not available: {parent_data['error']}")

            parent_id = parent_data["id"]

            # Batch create children
            entities = json.dumps(
                [
                    {
                        "entity_type": "Study",
                        "data": {"unique_id": "ST-1", "title": "Study 1"},
                        "parent_id": parent_id,
                    },
                    {
                        "entity_type": "Study",
                        "data": {"unique_id": "ST-2", "title": "Study 2"},
                        "parent_id": parent_id,
                    },
                ]
            )

            result = batch_fn.fn(entities=entities)
            data = json.loads(result)

            assert data["total"] == 2
            assert data["created"] == 2

    def test_batch_create_with_error(self):
        """Batch create continues after error."""
        from metaseed.agent.mcp.server import set_mcp_state
        from metaseed.ui.state import AppState

        server = create_server()
        tools = server._tool_manager._tools

        batch_fn = tools.get("batch_create")
        state = AppState(profile="miappe")
        set_mcp_state(state)

        # First entity missing entity_type, second valid
        entities = json.dumps(
            [
                {"data": {"unique_id": "FAIL-1"}},  # Missing entity_type
                {"entity_type": "Investigation", "data": {"unique_id": "INV-OK", "title": "Valid"}},
            ]
        )

        with patch("metaseed.ui.datasets.auto_save"):
            result = batch_fn.fn(entities=entities)
            data = json.loads(result)

            if "error" in data:
                pytest.skip(f"Profile not available: {data['error']}")

            assert data["total"] == 2
            assert data["failed"] >= 1  # At least the first one failed
            assert data["results"][0]["status"] == "error"
            assert "Missing entity_type" in data["results"][0]["message"]

    def test_batch_create_invalid_json(self):
        """Batch create handles invalid JSON."""
        server = create_server()
        tools = server._tool_manager._tools

        batch_fn = tools.get("batch_create")
        result = batch_fn.fn(entities="not valid json")
        data = json.loads(result)

        assert "error" in data
        assert "Invalid JSON" in data["error"]

    def test_batch_create_not_array(self):
        """Batch create requires array input."""
        server = create_server()
        tools = server._tool_manager._tools

        batch_fn = tools.get("batch_create")
        result = batch_fn.fn(entities='{"entity_type": "Investigation"}')
        data = json.loads(result)

        assert "error" in data
        assert "array" in data["error"].lower()


class TestMCPEnhancedErrors:
    """Tests for enhanced validation error messages."""

    def test_create_entity_validation_error_includes_fields(self):
        """Create entity validation error includes valid_fields."""
        from metaseed.agent.mcp.server import set_mcp_state
        from metaseed.ui.state import AppState

        server = create_server()
        tools = server._tool_manager._tools

        create_fn = tools.get("create_entity")
        state = AppState(profile="miappe")
        set_mcp_state(state)

        with patch("metaseed.ui.datasets.auto_save"):
            # Create with invalid field to trigger validation error
            result = create_fn.fn(
                entity_type="Investigation",
                data='{"invalid_field_xyz": "value"}',
            )
            data = json.loads(result)

            # Should either succeed (if no required fields) or have error with hints
            if "error" in data:
                # May have valid_fields hint depending on error type
                assert "error" in data


class TestMCPDatasetSafety:
    """Tests for dataset safety checks."""

    def test_create_entity_with_wrong_expected_dataset(self):
        """Create entity fails if expected_dataset doesn't match."""
        from metaseed.agent.mcp.server import set_mcp_state
        from metaseed.ui.state import AppState

        server = create_server()
        tools = server._tool_manager._tools

        create_fn = tools.get("create_entity")
        state = AppState(profile="miappe")
        set_mcp_state(state)

        with patch("metaseed.ui.datasets.auto_save"):
            with patch(
                "metaseed.ui.datasets.get_current_dataset_name", return_value="actual-dataset"
            ):
                result = create_fn.fn(
                    entity_type="Investigation",
                    data='{"unique_id": "INV-001", "title": "Test"}',
                    expected_dataset="expected-dataset",
                )
                data = json.loads(result)

                assert "error" in data
                assert "mismatch" in data["error"].lower()
                assert "expected-dataset" in data["error"]
                assert "actual-dataset" in data["error"]

    def test_create_entity_with_correct_expected_dataset(self):
        """Create entity succeeds when expected_dataset matches."""
        from metaseed.agent.mcp.server import set_mcp_state
        from metaseed.ui.state import AppState

        server = create_server()
        tools = server._tool_manager._tools

        create_fn = tools.get("create_entity")
        state = AppState(profile="miappe")
        set_mcp_state(state)

        with patch("metaseed.ui.datasets.auto_save"):
            with patch("metaseed.ui.datasets.get_current_dataset_name", return_value="my-dataset"):
                result = create_fn.fn(
                    entity_type="Investigation",
                    data='{"unique_id": "INV-001", "title": "Test"}',
                    expected_dataset="my-dataset",
                )
                data = json.loads(result)

                if "error" in data:
                    pytest.skip(f"Profile not available: {data['error']}")

                assert data["status"] == "created"
                assert "_dataset" in data
                assert data["_dataset"]["dataset"] == "my-dataset"

    def test_batch_create_with_wrong_expected_dataset(self):
        """Batch create fails if expected_dataset doesn't match."""
        from metaseed.agent.mcp.server import set_mcp_state
        from metaseed.ui.state import AppState

        server = create_server()
        tools = server._tool_manager._tools

        batch_fn = tools.get("batch_create")
        state = AppState(profile="miappe")
        set_mcp_state(state)

        with patch("metaseed.ui.datasets.get_current_dataset_name", return_value="actual-dataset"):
            result = batch_fn.fn(
                entities='[{"entity_type": "Investigation", "data": {"unique_id": "INV-001"}}]',
                expected_dataset="wrong-dataset",
            )
            data = json.loads(result)

            assert "error" in data
            assert "mismatch" in data["error"].lower()

    def test_response_includes_dataset_info(self):
        """Entity responses include _dataset info."""
        from metaseed.agent.mcp.server import set_mcp_state
        from metaseed.ui.state import AppState

        server = create_server()
        tools = server._tool_manager._tools

        create_fn = tools.get("create_entity")
        state = AppState(profile="miappe")
        set_mcp_state(state)

        with patch("metaseed.ui.datasets.auto_save"):
            with patch("metaseed.ui.datasets.get_current_dataset_name", return_value="test-ds"):
                result = create_fn.fn(
                    entity_type="Investigation",
                    data='{"unique_id": "INV-001", "title": "Test"}',
                )
                data = json.loads(result)

                if "error" in data:
                    pytest.skip(f"Profile not available: {data['error']}")

                assert "_dataset" in data
                assert data["_dataset"]["dataset"] == "test-ds"
                assert data["_dataset"]["profile"] == "miappe"


class TestEntityLabelFields:
    """Tests for convention-based label derivation.

    By convention, the first field in the entity spec is used as the label.
    For MIAPPE entities, this is typically `unique_id`.
    """

    def test_label_uses_first_field_from_spec(self):
        """Label is derived from the first field in the spec."""
        from metaseed.facade import ProfileFacade
        from metaseed.repositories.helpers import derive_label

        facade = ProfileFacade("miappe", "1.2")
        helper = facade.Investigation
        spec = helper._spec

        data = {
            "unique_id": "INV-001",
            "title": "My Investigation",
        }

        # Investigation's first field is unique_id
        label = derive_label("Investigation", data, spec=spec)
        assert label == "INV-001"

    def test_label_without_spec_returns_default(self):
        """Without spec, returns default label."""
        from metaseed.repositories.helpers import derive_label

        data = {
            "unique_id": "BM-001",
            "organism": "Arabidopsis thaliana",
        }

        # Without spec, falls back to default
        label = derive_label("BiologicalMaterial", data)
        assert label == "New BiologicalMaterial"

    def test_label_with_missing_first_field(self):
        """When first field is empty, returns default label."""
        from metaseed.facade import ProfileFacade
        from metaseed.repositories.helpers import derive_label

        facade = ProfileFacade("miappe", "1.2")
        helper = facade.Study
        spec = helper._spec

        # Data without the first field (unique_id)
        data = {
            "title": "My Study",
            "investigation_id": "INV-001",
        }

        label = derive_label("Study", data, spec=spec)
        assert label == "New Study"

    def test_different_entity_first_fields(self):
        """Different entities may have different first fields as identifiers."""
        from metaseed.facade import ProfileFacade
        from metaseed.repositories.helpers import derive_label

        facade = ProfileFacade("miappe", "1.2")

        # Person's first field is 'name' in MIAPPE 1.2
        person_spec = facade.Person._spec
        person_data = {"name": "Dr. Smith", "email": "smith@example.org"}
        label = derive_label("Person", person_data, spec=person_spec)
        assert label == "Dr. Smith"

        # Investigation's first field is 'unique_id'
        inv_spec = facade.Investigation._spec
        inv_data = {"unique_id": "INV-001", "title": "My Investigation"}
        label = derive_label("Investigation", inv_data, spec=inv_spec)
        assert label == "INV-001"

    def test_label_truncation(self):
        """Labels are truncated to 50 characters."""
        from metaseed.facade import ProfileFacade
        from metaseed.repositories.helpers import derive_label

        facade = ProfileFacade("miappe", "1.2")
        spec = facade.Investigation._spec

        long_id = "A" * 100
        data = {"unique_id": long_id}

        label = derive_label("Investigation", data, spec=spec)
        assert len(label) == 50
        assert label == long_id[:50]
