"""Test reference-linked children (e.g., File linked to Run via run_ref)."""

from metaseed.facade import ProfileFacade
from metaseed.ui.helpers.entity_helpers import (
    extract_nested_from_tree,
    get_nested_items_for_edit,
)
from metaseed.ui.helpers.validation import process_reference_linked_children
from metaseed.ui.state import AppState


class TestNestedEntityItemsBecomeChildNodes:
    """Saving a spec nested entity field (e.g. Run.files) must create child nodes.

    The tree and exports count standalone child nodes; the MCP creates them.
    The form-save path must do the same, otherwise an item added in the inline
    table is never reflected as an entity in the tree.
    """

    def _run_node(self, state):
        facade = state.get_or_create_facade()
        run = facade.Run.create(alias="run1", experiment_ref="exp1")
        return facade, state.add_node("Run", run)

    def test_nested_file_item_creates_one_child_node(self):
        state = AppState(profile="ena", version="1.0")
        facade, run_node = self._run_node(state)

        state.current_nested_items = {
            "files": [
                {
                    "filename": "r1.fastq.gz",
                    "filetype": "fastq",
                    "checksum_method": "MD5",
                    "checksum": "a" * 32,
                }
            ]
        }
        process_reference_linked_children(
            state=state,
            facade=facade,
            node_id=run_node.id,
            entity_type="Run",
            parent_identifier="run1",
        )

        files = [n for n in state.nodes_by_id.values() if n.entity_type == "File"]
        assert len(files) == 1
        assert files[0].instance.run_ref == "run1"
        assert files[0].parent_id == run_node.id

    def test_nested_file_item_is_not_duplicated_in_edit_view(self):
        state = AppState(profile="ena", version="1.0")
        facade, run_node = self._run_node(state)

        state.current_nested_items = {
            "files": [
                {
                    "filename": "r1.fastq.gz",
                    "filetype": "fastq",
                    "checksum_method": "MD5",
                    "checksum": "a" * 32,
                }
            ]
        }
        process_reference_linked_children(
            state=state,
            facade=facade,
            node_id=run_node.id,
            entity_type="Run",
            parent_identifier="run1",
        )

        items = get_nested_items_for_edit(
            state.nodes_by_id[run_node.id], facade.Run, facade
        )
        assert len(items.get("files", [])) == 1


class TestReferenceLinkedChildren:
    """Test that reference-linked children are properly handled."""

    def test_facade_adds_child_to_parent_children_list(self):
        """Test that facade.add_entity properly links child to parent."""
        facade = ProfileFacade("ena", "1.0")

        # Create Run
        run_node = facade.add_entity(
            "Run",
            {
                "alias": "run1",
                "experiment_ref": "exp1",  # Reference to non-existent parent is OK
            },
        )

        # Add File with run_ref pointing to run1
        file_node = facade.add_entity(
            "File",
            {
                "filename": "test.fastq.gz",
                "filetype": "fastq",
                "run_ref": "run1",
                "checksum_method": "MD5",
                "checksum": "0123456789abcdef0123456789abcdef",
            },
        )

        # File should be linked to Run via reference field
        assert file_node.parent_id == run_node.id
        assert file_node in run_node.children

    def test_add_node_updates_tree_cache_with_children(self):
        """Test that state.add_node properly updates TreeNode cache."""
        state = AppState()
        state.profile = "ena"
        state.version = "1.0"

        # Add Run
        run_instance = state.get_or_create_facade().Run.create(
            alias="run1",
            experiment_ref="exp1",
        )
        run_node = state.add_node("Run", run_instance)

        # Verify Run is in tree
        assert run_node.id in state.nodes_by_id

        # Add File linked to Run
        file_instance = state.get_or_create_facade().File.create(
            filename="test.fastq.gz",
            filetype="fastq",
            run_ref="run1",
            checksum_method="MD5",
            checksum="0123456789abcdef0123456789abcdef",
        )
        file_node = state.add_node("File", file_instance, parent_id=run_node.id)

        # File should be in cache
        assert file_node.id in state.nodes_by_id

        # Run's TreeNode should have File as child
        run_tree_node = state.nodes_by_id[run_node.id]
        assert len(run_tree_node.children) == 1
        assert run_tree_node.children[0].id == file_node.id

    def test_cache_rebuild_preserves_children(self):
        """Test that cache rebuild preserves children relationships."""
        state = AppState()
        state.profile = "ena"
        state.version = "1.0"
        facade = state.get_or_create_facade()

        # Add Run
        run_instance = facade.Run.create(alias="run1", experiment_ref="exp1")
        run_node = state.add_node("Run", run_instance)

        # Add File linked to Run
        file_instance = facade.File.create(
            filename="test.fastq.gz",
            filetype="fastq",
            run_ref="run1",
            checksum_method="MD5",
            checksum="0123456789abcdef0123456789abcdef",
        )
        state.add_node("File", file_instance, parent_id=run_node.id)

        # Invalidate and rebuild cache
        state._invalidate_cache()
        state._rebuild_cache()

        # After rebuild, Run should still have File as child
        run_tree_node = state.nodes_by_id[run_node.id]
        assert len(run_tree_node.children) == 1, (
            f"Expected 1 child, got {len(run_tree_node.children)}"
        )

    def test_get_nested_items_finds_reference_linked_children(self):
        """Test that get_nested_items_for_edit finds reference-linked children."""
        state = AppState()
        state.profile = "ena"
        state.version = "1.0"
        facade = state.get_or_create_facade()

        # Add Run
        run_instance = facade.Run.create(alias="run1", experiment_ref="exp1")
        run_node = state.add_node("Run", run_instance)

        # Add File linked to Run
        file_instance = facade.File.create(
            filename="test.fastq.gz",
            filetype="fastq",
            run_ref="run1",
            checksum_method="MD5",
            checksum="0123456789abcdef0123456789abcdef",
        )
        state.add_node("File", file_instance, parent_id=run_node.id)

        # Get Run's TreeNode
        run_tree_node = state.nodes_by_id[run_node.id]
        run_helper = facade.Run

        # get_nested_items_for_edit should find the File
        nested_items = get_nested_items_for_edit(run_tree_node, run_helper, facade)

        # Files should be in nested_items under "files" key
        assert "files" in nested_items, (
            f"Expected 'files' in nested_items, got {list(nested_items.keys())}"
        )
        assert len(nested_items["files"]) == 1

    def test_update_node_then_add_child_preserves_relationship(self):
        """Test the exact sequence that happens during save: update then add children."""
        state = AppState()
        state.profile = "ena"
        state.version = "1.0"
        facade = state.get_or_create_facade()

        # Add Run
        run_instance = facade.Run.create(alias="run1", experiment_ref="exp1")
        run_node = state.add_node("Run", run_instance)

        # Simulate save: first update the node (which invalidates cache)
        updated_run = facade.Run.create(
            alias="run1", experiment_ref="exp1", center_name="Test"
        )
        state.update_node(run_node.id, updated_run)

        # Then add a new child (File)
        file_instance = facade.File.create(
            filename="test.fastq.gz",
            filetype="fastq",
            run_ref="run1",
            checksum_method="MD5",
            checksum="0123456789abcdef0123456789abcdef",
        )
        file_node = state.add_node("File", file_instance, parent_id=run_node.id)

        # Now get the updated node (this may trigger cache rebuild)
        updated_run_node = state.nodes_by_id.get(run_node.id)

        # Run should have File as child
        assert len(updated_run_node.children) == 1, (
            f"Expected 1 child after update+add, got {len(updated_run_node.children)}. "
            f"Cache valid: {state._cache_valid}"
        )
        assert updated_run_node.children[0].id == file_node.id

        # Get nested items should also work
        run_helper = facade.Run
        nested_items = get_nested_items_for_edit(updated_run_node, run_helper, facade)
        assert "files" in nested_items, "Expected 'files' in nested_items after save"

    def test_extract_nested_from_tree_with_reference_children(self):
        """Test that extract_nested_from_tree finds reference-linked children."""
        state = AppState()
        state.profile = "ena"
        state.version = "1.0"
        facade = state.get_or_create_facade()

        # Add Run
        run_instance = facade.Run.create(alias="run1", experiment_ref="exp1")
        run_node = state.add_node("Run", run_instance)

        # Add File linked to Run
        file_instance = facade.File.create(
            filename="test.fastq.gz",
            filetype="fastq",
            run_ref="run1",
            checksum_method="MD5",
            checksum="0123456789abcdef0123456789abcdef",
        )
        state.add_node("File", file_instance, parent_id=run_node.id)

        # Get Run's TreeNode
        run_tree_node = state.nodes_by_id[run_node.id]
        run_helper = facade.Run

        # extract_nested_from_tree should find the File
        tree_items = extract_nested_from_tree(run_tree_node, run_helper, facade)

        # Files should be found (Run doesn't have "files" in nested_fields, but File.run_ref -> Run)
        assert "files" in tree_items, (
            f"Expected 'files' in tree_items, got {list(tree_items.keys())}"
        )

    def test_save_flow_with_existing_and_new_files(self):
        """Test the exact flow: existing files + add new file via table, then save."""
        state = AppState()
        state.profile = "ena"
        state.version = "1.0"
        facade = state.get_or_create_facade()

        # Create Run with existing File children
        run_instance = facade.Run.create(alias="run1", experiment_ref="exp1")
        run_node = state.add_node("Run", run_instance)

        # Add existing File as child
        existing_file = facade.File.create(
            filename="existing.fastq.gz",
            filetype="fastq",
            run_ref="run1",
            checksum_method="MD5",
            checksum="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        )
        _existing_file_node = state.add_node(
            "File", existing_file, parent_id=run_node.id
        )

        # Simulate user opening edit form for Run
        state.editing_node_id = run_node.id
        run_tree_node = state.nodes_by_id[run_node.id]
        run_helper = facade.Run

        # get_nested_items_for_edit called when opening form
        state.current_nested_items = get_nested_items_for_edit(
            run_tree_node, run_helper, facade
        )

        assert "files" in state.current_nested_items
        assert len(state.current_nested_items["files"]) == 1

        # Simulate user adding new row via +Row (creates a dict in current_nested_items)
        new_file_dict = {
            "filename": "new.fastq.gz",
            "filetype": "fastq",
            "checksum_method": "MD5",
            "checksum": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            # run_ref will be set during save
        }
        state.current_nested_items["files"].append(new_file_dict)
        assert len(state.current_nested_items["files"]) == 2

        # === SAVE FLOW (from update_entity in core.py) ===

        # 1. Update the Run node (invalidates cache)
        updated_run = facade.Run.create(
            alias="run1", experiment_ref="exp1", center_name="Updated"
        )
        state.update_node(run_node.id, updated_run)

        # 2. For each item in current_nested_items["files"]:
        parent_identifier = "run1"
        for item in state.current_nested_items["files"]:
            if not isinstance(item, dict):
                continue

            # Check if existing node
            item_id = item.get("_node_id") or item.get("alias")
            existing_node = state.nodes_by_id.get(item_id) if item_id else None

            # Clean item
            cleaned = {k: v for k, v in item.items() if not k.startswith("_") and v}
            if not cleaned:
                continue

            # Set parent reference
            cleaned["run_ref"] = parent_identifier

            if existing_node:
                # Update existing
                child_instance = facade.File.create(**cleaned)
                state.update_node(existing_node.id, child_instance)
            else:
                # Create new
                child_instance = facade.File.create(**cleaned)
                state.add_node("File", child_instance, parent_id=run_node.id)

        # 3. Rebuild nested items from tree
        updated_run_node = state.nodes_by_id.get(run_node.id)
        assert updated_run_node is not None

        state.current_nested_items = get_nested_items_for_edit(
            updated_run_node, run_helper, facade
        )

        # After save, should have both files
        assert "files" in state.current_nested_items, (
            f"Expected 'files' in current_nested_items after save. "
            f"Got keys: {list(state.current_nested_items.keys())}. "
            f"Updated node children: {len(updated_run_node.children)}"
        )
        assert len(state.current_nested_items["files"]) == 2, (
            f"Expected 2 files after save, got {len(state.current_nested_items['files'])}"
        )

    def test_check_nodes_by_id_after_add_node(self):
        """Debug test: check state of nodes_by_id after add_node during invalidated cache."""
        state = AppState()
        state.profile = "ena"
        state.version = "1.0"
        facade = state.get_or_create_facade()

        # Create Run
        run_instance = facade.Run.create(alias="run1", experiment_ref="exp1")
        run_node = state.add_node("Run", run_instance)

        # Invalidate cache (simulating update_node)
        state._invalidate_cache()
        assert not state._cache_valid

        # Add File while cache is invalid
        file_instance = facade.File.create(
            filename="test.fastq.gz",
            filetype="fastq",
            run_ref="run1",
            checksum_method="MD5",
            checksum="0123456789abcdef0123456789abcdef",
        )
        _file_node = state.add_node("File", file_instance, parent_id=run_node.id)

        # Check facade state
        run_entity_node = facade.get_entity(run_node.id)
        assert run_entity_node is not None
        assert len(run_entity_node.children) == 1, (
            f"Facade Run should have 1 child, got {len(run_entity_node.children)}"
        )

        # Now access nodes_by_id (triggers rebuild)
        all_nodes = state.nodes_by_id

        # Verify Run TreeNode has children after rebuild
        run_tree_node = all_nodes.get(run_node.id)
        assert run_tree_node is not None
        assert len(run_tree_node.children) == 1, (
            f"After rebuild, Run TreeNode should have 1 child, got {len(run_tree_node.children)}"
        )

    def test_loaded_dataset_with_files(self):
        """Test loading a dataset that already has Files under Runs."""
        state = AppState()
        state.profile = "ena"
        state.version = "1.0"
        facade = state.get_or_create_facade()

        # Simulate loading a dataset with Run and Files
        # This is how data comes from facade.load_from_dict
        entities = [
            {
                "_type": "Run",
                "alias": "DRR000618",
                "experiment_ref": "DRX000325",
            },
            {
                "_type": "File",
                "filename": "DRR000618_1.fastq.gz",
                "filetype": "fastq",
                "run_ref": "DRR000618",
                "checksum_method": "MD5",
                "checksum": "0123456789abcdef0123456789abcdef",
                "_parent_unique_id": "DRR000618",
            },
            {
                "_type": "File",
                "filename": "DRR000618_2.fastq.gz",
                "filetype": "fastq",
                "run_ref": "DRR000618",
                "checksum_method": "MD5",
                "checksum": "cccccccccccccccccccccccccccccccc",
                "_parent_unique_id": "DRR000618",
            },
        ]

        # Load via facade
        count = facade.load_from_dict(entities)
        assert count == 3

        # Invalidate state cache so it rebuilds from facade
        state._invalidate_cache()

        # Get Run's TreeNode
        run_entity = facade.get_entity_by_ref("DRR000618")
        assert run_entity is not None

        run_tree_node = state.nodes_by_id.get(run_entity.id)
        assert run_tree_node is not None
        assert len(run_tree_node.children) == 2, (
            f"Expected 2 File children, got {len(run_tree_node.children)}"
        )

        # Now simulate editing the Run
        state.editing_node_id = run_entity.id
        run_helper = facade.Run
        state.current_nested_items = get_nested_items_for_edit(
            run_tree_node, run_helper, facade
        )

        assert "files" in state.current_nested_items
        assert len(state.current_nested_items["files"]) == 2

        # Verify Files have _node_id
        for file_dict in state.current_nested_items["files"]:
            assert "_node_id" in file_dict, (
                f"File dict should have _node_id: {file_dict}"
            )

    def test_lookup_existing_file_by_node_id(self):
        """Test that we can look up existing Files by _node_id during save."""
        state = AppState()
        state.profile = "ena"
        state.version = "1.0"
        facade = state.get_or_create_facade()

        # Load dataset
        entities = [
            {"_type": "Run", "alias": "run1", "experiment_ref": "exp1"},
            {
                "_type": "File",
                "filename": "file1.fastq.gz",
                "filetype": "fastq",
                "run_ref": "run1",
                "checksum_method": "MD5",
                "checksum": "dddddddddddddddddddddddddddddddd",
                "_parent_unique_id": "run1",
            },
        ]
        facade.load_from_dict(entities)
        state._invalidate_cache()

        # Get Run and set up editing state
        run_entity = facade.get_entity_by_ref("run1")
        run_tree_node = state.nodes_by_id[run_entity.id]
        run_helper = facade.Run

        state.editing_node_id = run_entity.id
        state.current_nested_items = get_nested_items_for_edit(
            run_tree_node, run_helper, facade
        )

        # Get the File's _node_id from current_nested_items
        file_dict = state.current_nested_items["files"][0]
        file_node_id = file_dict["_node_id"]
        assert file_node_id is not None

        # Now simulate save: update Run (invalidates cache)
        updated_run = facade.Run.create(
            alias="run1", experiment_ref="exp1", center_name="Updated"
        )
        state.update_node(run_entity.id, updated_run)

        # Try to look up the File by _node_id (this triggers cache rebuild)
        item_id = file_dict.get("_node_id") or file_dict.get("alias")
        existing_node = state.nodes_by_id.get(item_id)

        assert existing_node is not None, (
            f"Should find existing File by _node_id={item_id}. "
            f"nodes_by_id keys: {list(state.nodes_by_id.keys())[:10]}"
        )
        assert existing_node.entity_type == "File"

    def test_update_existing_then_add_new_child(self):
        """Test updating existing children then adding new ones (exact save flow)."""
        state = AppState()
        state.profile = "ena"
        state.version = "1.0"
        facade = state.get_or_create_facade()

        # Load dataset with Run and existing File
        entities = [
            {"_type": "Run", "alias": "run1", "experiment_ref": "exp1"},
            {
                "_type": "File",
                "filename": "existing.fastq.gz",
                "filetype": "fastq",
                "run_ref": "run1",
                "checksum_method": "MD5",
                "checksum": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "_parent_unique_id": "run1",
            },
        ]
        facade.load_from_dict(entities)
        state._invalidate_cache()

        # Get Run and set up editing state
        run_entity = facade.get_entity_by_ref("run1")
        run_tree_node = state.nodes_by_id[run_entity.id]
        run_helper = facade.Run

        state.editing_node_id = run_entity.id
        state.current_nested_items = get_nested_items_for_edit(
            run_tree_node, run_helper, facade
        )

        # Verify initial state
        assert len(state.current_nested_items["files"]) == 1
        _existing_file_node_id = state.current_nested_items["files"][0]["_node_id"]

        # Add new file dict (simulates +Row in UI)
        new_file_dict = {
            "filename": "new.fastq.gz",
            "filetype": "fastq",
            "checksum_method": "MD5",
            "checksum": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        }
        state.current_nested_items["files"].append(new_file_dict)

        # === SAVE FLOW ===
        # 1. Update Run
        updated_run = facade.Run.create(
            alias="run1", experiment_ref="exp1", center_name="Updated"
        )
        state.update_node(run_entity.id, updated_run)

        # 2. Process each file
        parent_identifier = "run1"
        for item in state.current_nested_items["files"]:
            if not isinstance(item, dict):
                continue

            item_id = item.get("_node_id") or item.get("alias")
            existing_node = state.nodes_by_id.get(item_id) if item_id else None

            cleaned = {k: v for k, v in item.items() if not k.startswith("_") and v}
            if not cleaned:
                continue
            cleaned["run_ref"] = parent_identifier

            if existing_node:
                # Update existing File - THIS INVALIDATES CACHE
                child_instance = facade.File.create(**cleaned)
                state.update_node(existing_node.id, child_instance)
            else:
                # Create new File
                child_instance = facade.File.create(**cleaned)
                state.add_node("File", child_instance, parent_id=run_entity.id)

        # 3. Rebuild nested items
        updated_run_node = state.nodes_by_id.get(run_entity.id)
        state.current_nested_items = get_nested_items_for_edit(
            updated_run_node, run_helper, facade
        )

        # Verify both files are in nested items
        assert "files" in state.current_nested_items, (
            f"Expected 'files' in current_nested_items. Got: {list(state.current_nested_items.keys())}"
        )
        assert len(state.current_nested_items["files"]) == 2, (
            f"Expected 2 files after save, got {len(state.current_nested_items['files'])}. "
            f"Run children count: {len(updated_run_node.children)}"
        )

    def test_facade_preserves_children_after_update(self):
        """Test that facade preserves children when updating parent."""
        facade = ProfileFacade("ena", "1.0")

        # Add Run with File children
        run_node = facade.add_entity("Run", {"alias": "run1", "experiment_ref": "exp1"})
        _file1 = facade.add_entity(
            "File",
            {
                "filename": "f1.fastq.gz",
                "filetype": "fastq",
                "run_ref": "run1",
                "checksum_method": "MD5",
                "checksum": "dddddddddddddddddddddddddddddddd",
            },
        )
        _file2 = facade.add_entity(
            "File",
            {
                "filename": "f2.fastq.gz",
                "filetype": "fastq",
                "run_ref": "run1",
                "checksum_method": "MD5",
                "checksum": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
            },
        )

        assert len(run_node.children) == 2

        # Update Run
        facade.update_entity(
            run_node.id,
            {"alias": "run1", "experiment_ref": "exp1", "center_name": "Updated"},
        )

        # Children should still be there
        assert len(run_node.children) == 2, (
            f"Expected 2 children after update, got {len(run_node.children)}"
        )

    def test_switching_entities_refreshes_nested_items(self):
        """Test that current_nested_items is refreshed when switching between entities."""
        state = AppState()
        state.profile = "ena"
        state.version = "1.0"
        facade = state.get_or_create_facade()

        # Create Experiment with Run, and Run with File
        exp_node = facade.add_entity(
            "Experiment",
            {
                "alias": "exp1",
                "title": "Test Experiment",
                "study_ref": "study1",
                "sample_ref": "sample1",
                "library_strategy": "WGS",
                "library_source": "GENOMIC",
                "library_selection": "RANDOM",
                "library_layout": "SINGLE",
                "platform": "ILLUMINA",
                "instrument_model": "Illumina HiSeq 2500",
            },
        )
        run_node = facade.add_entity(
            "Run",
            {"alias": "run1", "experiment_ref": "exp1"},
            parent_id=exp_node.id,
        )
        _file_node = facade.add_entity(
            "File",
            {
                "filename": "file1.fastq.gz",
                "filetype": "fastq",
                "run_ref": "run1",
                "checksum_method": "MD5",
                "checksum": "dddddddddddddddddddddddddddddddd",
            },
            parent_id=run_node.id,
        )

        state._invalidate_cache()

        # Simulate opening Experiment edit form
        exp_tree_node = state.nodes_by_id[exp_node.id]
        exp_helper = facade.Experiment

        state.editing_node_id = exp_node.id
        state.current_nested_items = get_nested_items_for_edit(
            exp_tree_node, exp_helper, facade
        )

        # Experiment should have "runs" in nested items
        assert "runs" in state.current_nested_items

        # Now simulate switching to Run edit form
        # The BUG was: current_nested_items wouldn't be refreshed because it's not empty
        switching_entity = state.editing_node_id != run_node.id
        assert switching_entity  # Verify we are switching

        # Simulate what edit_entity_form does:
        if switching_entity or not state.current_nested_items:
            run_tree_node = state.nodes_by_id[run_node.id]
            run_helper = facade.Run
            state.editing_node_id = run_node.id
            state.current_nested_items = get_nested_items_for_edit(
                run_tree_node, run_helper, facade
            )

        # Run should have "files" in nested items
        assert "files" in state.current_nested_items, (
            f"Expected 'files' after switching to Run. Got: {list(state.current_nested_items.keys())}"
        )
        assert len(state.current_nested_items["files"]) == 1


class TestParentIdFillsReference:
    """Creating a child under an explicit parent auto-fills its parent reference.

    Before this, ``create_entity('Study', {...}, parent_id=inv)`` failed because
    the required ``investigation_id`` was not derived from the parent -- only the
    MCP tool layer filled it, so the shared client/facade was inconsistent.
    """

    def test_child_under_parent_gets_reference_filled(self) -> None:
        import yaml

        from metaseed import MetaseedClient

        client = MetaseedClient("miappe", "1.2")
        inv = client.create_entity(
            "Investigation", {"unique_id": "INV-1", "title": "T"}
        )
        inv_id = inv["id"] if isinstance(inv, dict) else inv.id
        # No investigation_id supplied; the explicit parent must provide it.
        client.create_entity(
            "Study", {"unique_id": "STU-1", "title": "S"}, parent_id=inv_id
        )
        assert "investigation_id: INV-1" in yaml.safe_dump(client.serialize())

    def test_a_study_without_a_parent_is_saved_and_reported(self) -> None:
        """Placing a child under its parent is what links them, not the back-reference.

        A study created on its own has nowhere to point yet. Whether it must
        carry a reference back to its investigation is the profile's decision,
        reported by validation, rather than something creation refuses.
        """
        from metaseed import MetaseedClient
        from metaseed.validators.api import validate_entity

        client = MetaseedClient("miappe", "1.2")
        study = client.create_entity("Study", {"unique_id": "STU-1", "title": "S"})

        assert study.data.get("unique_id") == "STU-1"
        assert any(
            issue.field == "investigation_id"
            for issue in validate_entity(
                {"unique_id": "STU-1", "title": "S"},
                "Study",
                profile="miappe",
                version="1.2",
            )
        )

    def test_caller_supplied_reference_is_not_overridden(self) -> None:
        import yaml

        from metaseed import MetaseedClient

        client = MetaseedClient("miappe", "1.2")
        inv = client.create_entity(
            "Investigation", {"unique_id": "INV-1", "title": "T"}
        )
        inv_id = inv["id"] if isinstance(inv, dict) else inv.id
        client.create_entity(
            "Study",
            {"unique_id": "STU-1", "title": "S", "investigation_id": "OTHER"},
            parent_id=inv_id,
        )
        assert "investigation_id: OTHER" in yaml.safe_dump(client.serialize())

    def test_reference_field_not_named_by_id_convention_is_filled(self) -> None:
        """The fill must follow the reference map, not a ``<parent>_id`` guess.

        ENA links Sample -> Study through ``study_ref`` (not ``study_id``) and
        copies the parent's ``alias`` (not an identifier named ``*_id``). A
        convention-based fill silently skips this; the reference-map fill must
        populate it from the explicit parent.
        """
        import yaml

        from metaseed import MetaseedClient

        client = MetaseedClient("ena", "1.0")
        study = client.create_entity(
            "Study", {"alias": "STU-A", "title": "t", "description": "d"}
        )
        study_id = study["id"] if isinstance(study, dict) else study.id
        client.create_entity(
            "Sample",
            {"alias": "SAM-1", "title": "t", "taxon_id": 1},
            parent_id=study_id,
        )
        assert "study_ref: STU-A" in yaml.safe_dump(client.serialize())
