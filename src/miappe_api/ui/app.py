"""Main NiceGUI application for MIAPPE-API.

Provides a web interface for creating and validating MIAPPE/ISA entities.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import yaml
from nicegui import ui
from pydantic import ValidationError

from miappe_api.facade import ProfileFacade


@dataclass
class TreeNode:
    """A node in the entity tree."""

    id: str
    entity_type: str
    instance: Any
    label: str
    children: list[TreeNode] = field(default_factory=list)
    parent_id: str | None = None

    @classmethod
    def create(cls, entity_type: str, instance: Any, parent_id: str | None = None) -> TreeNode:
        """Create a new tree node from an entity instance."""
        # Try to get a label from common fields
        label = ""
        if hasattr(instance, "model_dump"):
            data = instance.model_dump()
            for key in ["title", "name", "unique_id", "identifier", "filename"]:
                if key in data and data[key]:
                    label = str(data[key])
                    break
        if not label:
            label = f"New {entity_type}"

        return cls(
            id=str(uuid.uuid4())[:8],
            entity_type=entity_type,
            instance=instance,
            label=label,
            parent_id=parent_id,
        )


class EntityForm:
    """Dynamic form for creating entities."""

    def __init__(
        self,
        facade: ProfileFacade,
        entity_name: str,
        on_save: Any = None,
        is_nested: bool = False,
        app: Any = None,
    ) -> None:
        """Initialize form for an entity.

        Args:
            facade: Profile facade instance.
            entity_name: Name of entity to create form for.
            on_save: Callback when entity is saved (for nested forms).
            is_nested: Whether this is a nested form (in dialog).
            app: Reference to MIAPPEApp for navigation.
        """
        self.facade = facade
        self.entity_name = entity_name
        self.helper = getattr(facade, entity_name)
        self.inputs: dict[str, Any] = {}
        self.nested_items: dict[str, list[Any]] = {}  # Store nested entities
        self.result_container: ui.element | None = None
        self.on_save = on_save
        self.is_nested = is_nested
        self.app = app

    def render(self) -> None:
        """Render the form UI."""
        ui.label(self.entity_name).classes("text-2xl font-bold mb-2")
        ui.label(self.helper.description).classes("text-gray-600 mb-4")

        if self.helper.ontology_term:
            ui.label(f"Ontology: {self.helper.ontology_term}").classes("text-sm text-blue-600 mb-4")

        # Required fields section
        with ui.card().classes("w-full mb-4"):
            ui.label("Required Fields").classes("text-lg font-semibold mb-2")
            for field_name in self.helper.required_fields:
                self._render_field(field_name, required=True)

        # Optional fields section (collapsible)
        with ui.expansion("Optional Fields", icon="tune").classes("w-full mb-4"):
            for field_name in self.helper.optional_fields:
                self._render_field(field_name, required=False)

        # Action buttons
        with ui.row().classes("gap-4 mt-4"):
            if self.is_nested:
                # Nested form - Save button calls callback
                ui.button("Save", on_click=self._on_save_nested, icon="save").props(
                    f"color=primary data-testid=btn-save-{self.entity_name.lower()}"
                )
            else:
                # Top-level form - Create button
                ui.button("Create", on_click=self._on_create, icon="add").props(
                    f"color=primary data-testid=btn-create-{self.entity_name.lower()}"
                )
                ui.button("Clear", on_click=self._on_clear, icon="clear").props(
                    f"flat data-testid=btn-clear-{self.entity_name.lower()}"
                )

                # Result container (only for top-level forms)
                self.result_container = ui.column().classes("w-full mt-4")

    def _render_field(self, field_name: str, required: bool) -> None:
        """Render a single form field."""
        info = self.helper.field_info(field_name)
        field_type = info["type"]
        description = info.get("description", "")
        items = info.get("items")

        label = f"{field_name} *" if required else field_name

        # Create test ID for this field
        testid = f"input-{field_name.replace('_', '-')}"

        with ui.column().classes("w-full mb-2"):
            if field_type == "string":
                self.inputs[field_name] = (
                    ui.input(
                        label=label,
                        placeholder=description[:50] if description else None,
                    )
                    .classes("w-full")
                    .props(f"data-testid={testid}")
                    .mark(field_name)
                )

            elif field_type == "integer":
                self.inputs[field_name] = (
                    ui.number(
                        label=label,
                        format="%.0f",
                    )
                    .classes("w-full")
                    .props(f"data-testid={testid}")
                    .mark(field_name)
                )

            elif field_type == "float":
                self.inputs[field_name] = (
                    ui.number(
                        label=label,
                    )
                    .classes("w-full")
                    .props(f"data-testid={testid}")
                    .mark(field_name)
                )

            elif field_type == "boolean":
                self.inputs[field_name] = (
                    ui.checkbox(label).props(f"data-testid={testid}").mark(field_name)
                )

            elif field_type == "date":
                # Simple date input without complex bindings
                self.inputs[field_name] = (
                    ui.input(
                        label=label,
                        placeholder="YYYY-MM-DD",
                    )
                    .classes("w-full")
                    .props(f"data-testid={testid}")
                    .mark(field_name)
                )

            elif field_type == "uri":
                self.inputs[field_name] = (
                    ui.input(
                        label=label,
                        placeholder="https://...",
                    )
                    .classes("w-full")
                    .props(f"data-testid={testid}")
                    .mark(field_name)
                )

            elif field_type == "list":
                if items and items not in ("string", "int", "float", "bool"):
                    # List of entities - show add button and list
                    self._render_nested_list_field(field_name, items, label)
                else:
                    # List of primitives - use textarea
                    self.inputs[field_name] = (
                        ui.textarea(
                            label=label,
                            placeholder=f"One {items or 'item'} per line",
                        )
                        .classes("w-full")
                        .props(f"data-testid={testid}")
                        .mark(field_name)
                    )

            elif field_type == "entity":
                # Single entity reference - show add button
                self._render_nested_entity_field(field_name, items, label)

            else:
                # Fallback to text input
                self.inputs[field_name] = (
                    ui.input(label=label)
                    .classes("w-full")
                    .props(f"data-testid={testid}")
                    .mark(field_name)
                )

            if description:
                ui.label(description).classes("text-xs text-gray-500 mt-1")

    def _render_nested_list_field(self, field_name: str, entity_type: str, label: str) -> None:
        """Render a field that contains a list of nested entities."""
        self.nested_items[field_name] = []

        with ui.card().classes("w-full p-2 bg-gray-50"):
            ui.label(label).classes("font-semibold text-sm")

            # Container for added items
            items_container = ui.column().classes("w-full gap-1 mt-2")
            count_label = ui.label(f"0 {entity_type}(s)").classes("text-xs text-gray-500")

            def refresh_list():
                items_container.clear()
                items = self.nested_items[field_name]
                count_label.set_text(f"{len(items)} {entity_type}(s)")
                with items_container:
                    for i, item in enumerate(items):
                        with ui.row().classes("w-full items-center gap-2 p-1 bg-white rounded"):
                            summary = self._get_entity_summary(item)
                            ui.label(summary).classes("flex-grow text-sm")

                            def make_delete_handler(idx: int):
                                def handler():
                                    del self.nested_items[field_name][idx]
                                    refresh_list()

                                return handler

                            ui.button(
                                icon="delete",
                                on_click=make_delete_handler(i),
                            ).props("flat dense color=negative size=sm")

            with ui.row().classes("gap-2 mt-2"):
                ui.button(
                    f"Add {entity_type}",
                    on_click=lambda: self._open_nested_dialog(
                        entity_type, field_name, refresh_list
                    ),
                    icon="add",
                ).props(f"flat dense color=primary data-testid=btn-add-{entity_type.lower()}")

                # Navigation link to explore the entity type
                if self.app is not None:
                    ui.button(
                        f"Explore {entity_type}",
                        on_click=lambda et=entity_type: self.app.navigate_to_entity(et),
                        icon="arrow_forward",
                    ).props(f"flat dense data-testid=btn-explore-{entity_type.lower()}")

    def _render_nested_entity_field(self, field_name: str, entity_type: str, label: str) -> None:
        """Render a field that contains a single nested entity."""
        self.nested_items[field_name] = None

        with ui.card().classes("w-full p-2 bg-gray-50"):
            ui.label(label).classes("font-semibold text-sm")

            # Container for the item
            item_container = ui.column().classes("w-full mt-2")

            def refresh_item():
                item_container.clear()
                with item_container:
                    item = self.nested_items[field_name]
                    if item:
                        with ui.row().classes("w-full items-center gap-2 p-1 bg-white rounded"):
                            summary = self._get_entity_summary(item)
                            ui.label(summary).classes("flex-grow text-sm")
                            ui.button(
                                icon="delete",
                                on_click=lambda: self._clear_nested_item(field_name, refresh_item),
                            ).props("flat dense color=negative size=sm")
                    else:
                        ui.label("Not set").classes("text-gray-400 text-sm italic")

            def on_add_item():
                self._open_nested_dialog(entity_type, field_name, refresh_item, is_single=True)

            refresh_item()

            with ui.row().classes("gap-2 mt-2"):
                ui.button(
                    f"Set {entity_type}",
                    on_click=on_add_item,
                    icon="edit",
                ).props(f"flat dense color=primary data-testid=btn-set-{entity_type.lower()}")

                # Navigation link to explore the entity type
                if self.app is not None:
                    ui.button(
                        f"Explore {entity_type}",
                        on_click=lambda et=entity_type: self.app.navigate_to_entity(et),
                        icon="arrow_forward",
                    ).props(f"flat dense data-testid=btn-explore-{entity_type.lower()}")

    def _get_entity_summary(self, entity: Any) -> str:
        """Get a short summary string for an entity."""
        if hasattr(entity, "model_dump"):
            data = entity.model_dump()
        elif isinstance(entity, dict):
            data = entity
        else:
            return str(entity)

        # Try common identifier fields
        for key in ["name", "title", "unique_id", "identifier", "filename", "term"]:
            if key in data and data[key]:
                return f"{data[key]}"
        # Fallback to first non-empty value
        for _, val in data.items():
            if val and isinstance(val, str):
                return f"{val[:30]}..."
        return "(unnamed)"

    def _open_nested_dialog(
        self,
        entity_type: str,
        field_name: str,
        refresh_callback: Any,
        is_single: bool = False,
    ) -> None:
        """Open a dialog to create a nested entity."""
        with ui.dialog() as dialog, ui.card().classes("w-[700px] max-w-[90vw] max-h-[85vh] p-6"):
            ui.label(f"Add {entity_type}").classes("text-lg font-bold mb-4")

            # Scrollable form content
            with ui.scroll_area().classes("w-full").style("max-height: calc(85vh - 120px)"):

                def on_save(instance: Any):
                    if is_single:
                        self.nested_items[field_name] = instance
                    else:
                        self.nested_items[field_name].append(instance)
                    dialog.close()
                    refresh_callback()

                # Create nested form
                nested_form = EntityForm(self.facade, entity_type, on_save=on_save, is_nested=True)
                nested_form.render()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props(
                    f"flat data-testid=btn-cancel-{entity_type.lower()}"
                )

        dialog.open()

    def _clear_nested_item(self, field_name: str, refresh_callback: Any) -> None:
        """Clear a single nested item field."""
        self.nested_items[field_name] = None
        refresh_callback()

    async def _on_save_nested(self) -> None:
        """Handle save button click for nested forms."""
        values = self._collect_values()

        try:
            instance = self.helper.create(**values)
            if self.on_save:
                self.on_save(instance)
        except ValidationError as e:
            # Show validation errors in a notification
            errors = "; ".join(
                f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in e.errors()
            )
            ui.notify(f"Validation error: {errors}", type="negative")

    def _collect_values(self) -> dict[str, Any]:
        """Collect form values into a dictionary."""
        values = {}

        # Collect regular input values
        for field_name, input_elem in self.inputs.items():
            value = input_elem.value
            if value is None or value == "":
                continue

            info = self.helper.field_info(field_name)
            field_type = info["type"]

            # Handle type conversions
            if field_type == "list" and info.get("items") == "string":
                # Split textarea by lines
                value = [line.strip() for line in str(value).split("\n") if line.strip()]
            elif field_type in ("list", "entity") and isinstance(value, str):
                # Try parsing as JSON/YAML
                try:
                    import json

                    value = json.loads(value)
                except (json.JSONDecodeError, ValueError):
                    pass  # Keep as string, will fail validation

            values[field_name] = value

        # Collect nested entity values
        for field_name, items in self.nested_items.items():
            if items is None:
                continue
            if isinstance(items, list):
                if items:  # Only include non-empty lists
                    values[field_name] = items
            else:
                values[field_name] = items

        return values

    async def _on_create(self) -> None:
        """Handle create button click."""
        if self.result_container:
            self.result_container.clear()

        values = self._collect_values()

        try:
            instance = self.helper.create(**values)

            # Call on_save callback if set (for tree integration)
            if self.on_save:
                self.on_save(instance)
                return  # Tree view handles the display

            # Show success (fallback for forms without tree integration)
            if self.result_container:
                with self.result_container:
                    ui.label("Created successfully!").classes("text-green-600 font-bold")

                    # Show YAML output
                    with ui.expansion("YAML Output", icon="code").classes("w-full"):
                        yaml_str = yaml.dump(
                            instance.model_dump(exclude_none=True),
                            default_flow_style=False,
                            allow_unicode=True,
                        )
                        ui.code(yaml_str, language="yaml").classes("w-full")

                    # Download buttons
                    with ui.row().classes("gap-2 mt-2"):
                        yaml_bytes = yaml_str.encode()
                        ui.download(
                            yaml_bytes,
                            f"{self.entity_name.lower()}.yaml",
                        ).classes("hidden").props("id=download-yaml")
                        ui.button(
                            "Download YAML",
                            on_click=lambda: ui.run_javascript(
                                "document.getElementById('download-yaml').click()"
                            ),
                            icon="download",
                        ).props("flat")

        except ValidationError as e:
            error_msg = "; ".join(
                f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in e.errors()
            )
            ui.notify(f"Validation error: {error_msg}", type="negative")

        except Exception as e:
            ui.notify(f"Error: {e}", type="negative")

    def _on_clear(self) -> None:
        """Clear all form inputs."""
        for input_elem in self.inputs.values():
            if hasattr(input_elem, "set_value"):
                input_elem.set_value(None)
            elif hasattr(input_elem, "value"):
                input_elem.value = None
        if self.result_container:
            self.result_container.clear()


class MIAPPEApp:
    """Main application class."""

    def __init__(self) -> None:
        """Initialize the application."""
        self.profiles = ["miappe", "isa"]
        self.current_profile: str = "miappe"
        self.current_version: str | None = None
        self.current_entity: str | None = None
        self.facade: ProfileFacade | None = None
        self.main_content: ui.element | None = None
        self.breadcrumb_container: ui.element | None = None
        self.sidebar_container: ui.element | None = None
        self.nav_stack: list[str] = []  # Stack of entity names for breadcrumbs
        # Tree of created entities
        self.entity_tree: list[TreeNode] = []
        self.nodes_by_id: dict[str, TreeNode] = {}
        self.editing_node: TreeNode | None = None

    def _build_entity_hierarchy(self) -> list[tuple[str, int]]:
        """Build entity hierarchy from spec relationships.

        Returns:
            List of (entity_name, depth) tuples in hierarchical order.
        """
        if self.facade is None:
            return []

        # Build parent -> children map from entity references
        children: dict[str, list[str]] = {name: [] for name in self.facade.entities}
        referenced_by: dict[str, set[str]] = {name: set() for name in self.facade.entities}

        for entity_name in self.facade.entities:
            helper = getattr(self.facade, entity_name)
            nested = helper.nested_fields  # {field_name: entity_type}

            for ref_entity in nested.values():
                if ref_entity in children:
                    children[entity_name].append(ref_entity)
                    referenced_by[ref_entity].add(entity_name)

        # Find root entities (not referenced by others, or self-referential only)
        roots = []
        for name in self.facade.entities:
            refs = referenced_by[name] - {name}  # Exclude self-references
            if not refs:
                roots.append(name)

        # If no clear roots, use Investigation or first entity
        if not roots:
            if "Investigation" in self.facade.entities:
                roots = ["Investigation"]
            else:
                roots = [self.facade.entities[0]]

        # BFS to build hierarchy with depths
        result: list[tuple[str, int]] = []
        visited: set[str] = set()

        def visit(name: str, depth: int) -> None:
            if name in visited:
                return
            visited.add(name)
            result.append((name, depth))

            # Sort children for consistent ordering
            for child in sorted(children.get(name, [])):
                visit(child, depth + 1)

        # Start from roots
        for root in sorted(roots):
            visit(root, 0)

        # Add any unvisited entities at depth 0
        for name in sorted(self.facade.entities):
            if name not in visited:
                result.append((name, 0))

        return result

    def run(self, host: str = "127.0.0.1", port: int = 8080) -> None:
        """Run the application.

        Args:
            host: Host to bind to.
            port: Port to bind to.
        """
        self._setup_ui()
        ui.run(host=host, port=port, title="MIAPPE-API", reload=False)

    def _setup_ui(self) -> None:
        """Set up the main UI layout."""

        @ui.page("/")
        def index():
            with ui.header().classes("bg-blue-800 text-white"):
                ui.label("MIAPPE-API").classes("text-xl font-bold")
                ui.space()
                with ui.row().classes("gap-4"):
                    ui.select(
                        self.profiles,
                        value=self.current_profile,
                        on_change=lambda e: self._on_profile_change(e.value),
                    ).props("dense dark data-testid=select-profile").classes("w-32")

            with ui.left_drawer().classes("bg-gray-100") as drawer:
                drawer.props("width=300")
                with ui.column().classes("w-full") as sidebar:
                    self.sidebar_container = sidebar
                    self._render_sidebar()

            with ui.column().classes("w-full p-4"):
                # Breadcrumb container at top
                self.breadcrumb_container = ui.row().classes("w-full mb-4 gap-2 items-center")
                # Main content below
                with ui.column().classes("w-full") as main:
                    self.main_content = main
                    self._render_welcome()

    def _render_sidebar(self) -> None:
        """Render the entity tree sidebar."""
        if self.facade is None:
            self._load_profile(self.current_profile)

        ui.label("Project").classes("text-lg font-bold mb-2")

        # New entity buttons for root types
        root_types = self._get_root_entity_types()
        with ui.row().classes("gap-1 mb-4 flex-wrap"):
            for entity_type in root_types[:3]:  # Show top 3 root types
                ui.button(
                    f"+ {entity_type}",
                    on_click=lambda _, et=entity_type: self._create_new_root_entity(et),
                ).props(f"dense size=sm data-testid=btn-new-{entity_type.lower()}").classes(
                    "text-xs"
                )

        # Entity tree
        if not self.entity_tree:
            ui.label("No entities created yet").classes("text-gray-400 text-sm italic")
            ui.label("Click a button above to start").classes("text-gray-400 text-xs")
        else:
            self._render_tree_nodes(self.entity_tree, depth=0)

    def _render_tree_nodes(self, nodes: list[TreeNode], depth: int) -> None:
        """Render tree nodes recursively."""
        for node in nodes:
            indent_px = depth * 16
            is_selected = self.editing_node and self.editing_node.id == node.id

            with (
                ui.row()
                .classes(
                    f"w-full items-center gap-1 p-1 rounded cursor-pointer "
                    f"{'bg-blue-100' if is_selected else 'hover:bg-gray-200'}"
                )
                .style(f"margin-left: {indent_px}px")
                .props(f"data-testid=tree-node-{node.id}")
                .mark(f"tree-{node.id}", node.label)
                .on("click", lambda _, n=node: self._on_tree_node_click(n))
            ):
                # Icon based on entity type
                icon = "folder" if node.children else "description"
                ui.icon(icon, size="xs").classes("text-gray-500")
                with ui.column().classes("gap-0"):
                    ui.label(node.label).classes("text-sm font-medium")
                    ui.label(node.entity_type).classes("text-xs text-gray-400")

            # Render children
            if node.children:
                self._render_tree_nodes(node.children, depth + 1)

    def _get_root_entity_types(self) -> list[str]:
        """Get entity types that can be created at root level."""
        if self.facade is None:
            return []

        # Find entities not referenced by others
        referenced_by: dict[str, set[str]] = {name: set() for name in self.facade.entities}

        for entity_name in self.facade.entities:
            helper = getattr(self.facade, entity_name)
            for ref_entity in helper.nested_fields.values():
                if ref_entity in referenced_by:
                    referenced_by[ref_entity].add(entity_name)

        roots = []
        for name in self.facade.entities:
            refs = referenced_by[name] - {name}
            if not refs:
                roots.append(name)

        # Prioritize Investigation
        if "Investigation" in roots:
            roots.remove("Investigation")
            roots.insert(0, "Investigation")

        return roots

    def _create_new_root_entity(self, entity_type: str) -> None:
        """Create a new root-level entity."""
        self.nav_stack = [entity_type]
        self.editing_node = None
        self._render_breadcrumbs()
        self.main_content.clear()

        with self.main_content:
            form = EntityForm(
                self.facade,
                entity_type,
                app=self,
                on_save=lambda inst: self._add_to_tree(entity_type, inst),
            )
            form.render()

    def _add_to_tree(self, entity_type: str, instance: Any, parent_id: str | None = None) -> None:
        """Add a created entity to the tree."""
        node = TreeNode.create(entity_type, instance, parent_id)
        self.nodes_by_id[node.id] = node

        if parent_id and parent_id in self.nodes_by_id:
            self.nodes_by_id[parent_id].children.append(node)
        else:
            self.entity_tree.append(node)

        # Refresh sidebar
        self._refresh_sidebar()
        ui.notify(f"Created {entity_type}: {node.label}", type="positive")

    def _refresh_sidebar(self) -> None:
        """Refresh the sidebar tree view."""
        if self.sidebar_container:
            self.sidebar_container.clear()
            with self.sidebar_container:
                self._render_sidebar()

    def _on_tree_node_click(self, node: TreeNode) -> None:
        """Handle click on a tree node to edit it."""
        self.editing_node = node
        self.nav_stack = [node.entity_type]
        self._render_breadcrumbs()
        self._refresh_sidebar()
        self.main_content.clear()

        with self.main_content:
            # Show entity details with edit capability
            ui.label(f"Editing: {node.label}").classes("text-2xl font-bold mb-2")
            ui.label(node.entity_type).classes("text-gray-600 mb-4")

            # Show current data
            with ui.expansion("Current Data", icon="data_object").classes("w-full mb-4"):
                yaml_str = yaml.dump(
                    node.instance.model_dump(exclude_none=True),
                    default_flow_style=False,
                    allow_unicode=True,
                )
                ui.code(yaml_str, language="yaml").classes("w-full")

            # Show nested entity options
            helper = getattr(self.facade, node.entity_type)
            nested = helper.nested_fields

            if nested:
                ui.label("Add Child Entities").classes("text-lg font-semibold mb-2")
                with ui.row().classes("gap-2 flex-wrap"):
                    for _field_name, child_type in nested.items():
                        ui.button(
                            f"+ {child_type}",
                            on_click=lambda _,
                            ct=child_type,
                            nid=node.id: self._create_child_entity(ct, nid),
                        ).props(f"outline data-testid=btn-add-child-{child_type.lower()}")

    def _create_child_entity(self, entity_type: str, parent_id: str) -> None:
        """Create a child entity under a parent."""
        self.nav_stack.append(entity_type)
        self._render_breadcrumbs()
        self.main_content.clear()

        with self.main_content:
            form = EntityForm(
                self.facade,
                entity_type,
                app=self,
                on_save=lambda inst: self._add_to_tree(entity_type, inst, parent_id),
            )
            form.render()

    def _render_welcome(self) -> None:
        """Render welcome message."""
        with ui.column().classes("items-center justify-center h-64"):
            ui.label("Welcome to MIAPPE-API").classes("text-2xl font-bold text-gray-600")
            ui.label("Select an entity from the sidebar to begin").classes("text-gray-500")

    def _load_profile(self, profile: str) -> None:
        """Load a profile."""
        self.current_profile = profile
        self.facade = ProfileFacade(profile)
        self.current_version = self.facade.version

    def _on_profile_change(self, profile: str) -> None:
        """Handle profile selection change."""
        self._load_profile(profile)
        ui.navigate.reload()

    def _on_entity_select(self, entity_name: str, reset_nav: bool = True) -> None:
        """Handle entity selection from sidebar or navigation.

        Args:
            entity_name: Name of entity to display.
            reset_nav: If True, reset nav stack (sidebar click). If False, push to stack.
        """
        if reset_nav:
            self.nav_stack = [entity_name]
        else:
            self.nav_stack.append(entity_name)

        self.current_entity = entity_name
        self._render_breadcrumbs()
        self.main_content.clear()

        with self.main_content:
            form = EntityForm(self.facade, entity_name, app=self)
            form.render()

    def _render_breadcrumbs(self) -> None:
        """Render breadcrumb navigation."""
        self.breadcrumb_container.clear()
        with self.breadcrumb_container:
            for i, entity_name in enumerate(self.nav_stack):
                if i > 0:
                    ui.label("/").classes("text-gray-400")

                is_current = i == len(self.nav_stack) - 1
                if is_current:
                    ui.label(entity_name).classes("font-bold text-blue-800")
                else:
                    # Clickable breadcrumb to navigate back
                    ui.button(
                        entity_name,
                        on_click=lambda _, idx=i: self._navigate_to_breadcrumb(idx),
                    ).props("flat dense").classes("text-blue-600")

    def _navigate_to_breadcrumb(self, index: int) -> None:
        """Navigate to a breadcrumb position."""
        # Truncate nav_stack to the clicked position
        self.nav_stack = self.nav_stack[: index + 1]
        entity_name = self.nav_stack[-1]
        self.current_entity = entity_name
        self._render_breadcrumbs()
        self.main_content.clear()

        with self.main_content:
            form = EntityForm(self.facade, entity_name, app=self)
            form.render()

    def navigate_to_entity(self, entity_name: str) -> None:
        """Navigate into a nested entity (drill-down)."""
        self._on_entity_select(entity_name, reset_nav=False)


def run_ui(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Run the MIAPPE-API web interface.

    Args:
        host: Host to bind to.
        port: Port to bind to.
    """
    app = MIAPPEApp()
    app.run(host=host, port=port)
