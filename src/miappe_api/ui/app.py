"""Main NiceGUI application for MIAPPE-API.

Provides a web interface for creating and validating MIAPPE/ISA entities.
"""

from __future__ import annotations

from typing import Any

import yaml
from nicegui import ui
from pydantic import ValidationError

from miappe_api.facade import ProfileFacade


class EntityForm:
    """Dynamic form for creating entities."""

    def __init__(self, facade: ProfileFacade, entity_name: str) -> None:
        """Initialize form for an entity.

        Args:
            facade: Profile facade instance.
            entity_name: Name of entity to create form for.
        """
        self.facade = facade
        self.entity_name = entity_name
        self.helper = getattr(facade, entity_name)
        self.inputs: dict[str, Any] = {}
        self.result_container: ui.element | None = None

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
            ui.button("Create", on_click=self._on_create, icon="add").props("color=primary")
            ui.button("Clear", on_click=self._on_clear, icon="clear").props("flat")

        # Result container
        self.result_container = ui.column().classes("w-full mt-4")

    def _render_field(self, field_name: str, required: bool) -> None:
        """Render a single form field."""
        info = self.helper.field_info(field_name)
        field_type = info["type"]
        description = info.get("description", "")
        items = info.get("items")

        label = f"{field_name} *" if required else field_name

        with ui.column().classes("w-full mb-2"):
            if field_type == "string":
                self.inputs[field_name] = ui.input(
                    label=label,
                    placeholder=description[:50] if description else None,
                ).classes("w-full")

            elif field_type == "integer":
                self.inputs[field_name] = ui.number(
                    label=label,
                    format="%.0f",
                ).classes("w-full")

            elif field_type == "float":
                self.inputs[field_name] = ui.number(
                    label=label,
                ).classes("w-full")

            elif field_type == "boolean":
                self.inputs[field_name] = ui.checkbox(label)

            elif field_type == "date":
                with ui.input(label=label).classes("w-full") as date_input:
                    with ui.menu().props("no-parent-event") as menu:
                        with ui.date().bind_value(date_input):
                            with ui.row().classes("justify-end"):
                                ui.button("Close", on_click=menu.close).props("flat")
                    with date_input.add_slot("append"):
                        ui.icon("edit_calendar").on("click", menu.open).classes("cursor-pointer")
                self.inputs[field_name] = date_input

            elif field_type == "uri":
                self.inputs[field_name] = ui.input(
                    label=label,
                    placeholder="https://...",
                ).classes("w-full")

            elif field_type == "list":
                # For list fields, use textarea with one item per line
                hint = (
                    f"One {items or 'item'} per line"
                    if items == "string"
                    else f"JSON array of {items}"
                )
                self.inputs[field_name] = ui.textarea(
                    label=label,
                    placeholder=hint,
                ).classes("w-full")

            elif field_type == "entity":
                # For entity references, use JSON input
                self.inputs[field_name] = (
                    ui.textarea(
                        label=f"{label} ({items})",
                        placeholder=f"JSON object for {items}",
                    )
                    .classes("w-full")
                    .props("rows=3")
                )

            else:
                # Fallback to text input
                self.inputs[field_name] = ui.input(label=label).classes("w-full")

            if description:
                ui.label(description).classes("text-xs text-gray-500 mt-1")

    def _collect_values(self) -> dict[str, Any]:
        """Collect form values into a dictionary."""
        values = {}
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

        return values

    async def _on_create(self) -> None:
        """Handle create button click."""
        self.result_container.clear()

        values = self._collect_values()

        try:
            instance = self.helper.create(**values)

            # Show success
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
            with self.result_container:
                ui.label("Validation Error").classes("text-red-600 font-bold")
                for error in e.errors():
                    field = ".".join(str(loc) for loc in error["loc"])
                    msg = error["msg"]
                    ui.label(f"  {field}: {msg}").classes("text-red-500 text-sm")

        except Exception as e:
            with self.result_container:
                ui.label(f"Error: {e}").classes("text-red-600")

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
                    ).props("dense dark").classes("w-32")

            with ui.left_drawer().classes("bg-gray-100") as drawer:
                drawer.props("width=280")
                self._render_sidebar()

            with ui.column().classes("w-full p-4") as main:
                self.main_content = main
                self._render_welcome()

    def _render_sidebar(self) -> None:
        """Render the entity list sidebar in hierarchical order."""
        if self.facade is None:
            self._load_profile(self.current_profile)

        ui.label("Entities").classes("text-lg font-bold mb-2")

        hierarchy = self._build_entity_hierarchy()

        for entity_name, depth in hierarchy:
            helper = getattr(self.facade, entity_name)
            req_count = len(helper.required_fields)

            # Indent using inline style for precise control
            indent_px = depth * 12
            border_style = "border-left: 3px solid #93c5fd;" if depth > 0 else ""

            with (
                ui.card()
                .classes("w-full mb-1 cursor-pointer hover:bg-blue-50")
                .style(f"margin-left: {indent_px}px; {border_style}")
                .on("click", lambda _, name=entity_name: self._on_entity_select(name))
            ):
                ui.label(entity_name).classes("font-semibold text-sm")
                ui.label(f"{req_count} required").classes("text-xs text-gray-500")

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

    def _on_entity_select(self, entity_name: str) -> None:
        """Handle entity selection."""
        self.current_entity = entity_name
        self.main_content.clear()

        with self.main_content:
            form = EntityForm(self.facade, entity_name)
            form.render()


def run_ui(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Run the MIAPPE-API web interface.

    Args:
        host: Host to bind to.
        port: Port to bind to.
    """
    app = MIAPPEApp()
    app.run(host=host, port=port)
