"""MCP tools for authoring profile specifications.

These tools expose the shared :class:`~metaseed.specs.builder.SpecBuilder` over
MCP. They operate on a single active draft held per session (keyed to the
session :class:`AppState`). Entities, fields, and rules are addressed by name.

See `docs/api/spec-builder-mcp.md`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from metaseed.specs.builder import SpecBuilder
from metaseed.specs.schema import Constraints

if TYPE_CHECKING:
    from collections.abc import Callable

    from mcp.server.fastmcp import FastMCP

    from metaseed.ui.state import AppState


# The active draft is held on the session AppState (AppState.spec_draft), so
# standalone and context-injected modes each get their own draft and it resets
# with the session.


def _set_draft(state: AppState, builder: SpecBuilder) -> SpecBuilder:
    state.spec_draft = builder.spec
    return builder


def _require_draft(state: AppState) -> SpecBuilder:
    if state.spec_draft is None:
        raise ValueError(
            "No spec draft in progress. Start one with spec_create, "
            "spec_clone, or spec_import_yaml."
        )
    return SpecBuilder.from_spec(state.spec_draft)


def _status(builder: SpecBuilder) -> dict[str, Any]:
    spec = builder.spec
    return {
        "name": spec.name,
        "version": spec.version,
        "display_name": spec.display_name,
        "root_entity": spec.root_entity,
        "entities": {
            entity_name: [f.name for f in entity.fields]
            for entity_name, entity in spec.entities.items()
        },
        "validation_rules": [r.name for r in spec.validation_rules],
    }


def _clean(attrs: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is None so 'unset' arguments leave fields unchanged."""
    return {key: value for key, value in attrs.items() if value is not None}


def _constraints(
    pattern: str | None,
    min_length: int | None,
    max_length: int | None,
    minimum: float | None,
    maximum: float | None,
    min_items: int | None,
    max_items: int | None,
    enum: list[str] | None,
) -> Constraints | None:
    """Build a Constraints object, or None if no constraint is supplied."""
    values = _clean(
        {
            "pattern": pattern,
            "min_length": min_length,
            "max_length": max_length,
            "minimum": minimum,
            "maximum": maximum,
            "min_items": min_items,
            "max_items": max_items,
            "enum": enum,
        }
    )
    return Constraints(**values) if values else None


def register_spec_builder_tools(  # noqa: C901
    mcp: FastMCP, get_mcp_state: Callable[[], AppState]
) -> None:
    """Register the spec-builder tools with the MCP server.

    Args:
        mcp: FastMCP server instance.
        get_mcp_state: Callable returning the active session AppState.
    """

    # ------------------------------------------------------------------
    # Draft lifecycle
    # ------------------------------------------------------------------
    @mcp.tool()
    def spec_create(
        name: str,
        version: str,
        display_name: str | None = None,
        description: str = "",
        ontology: str | None = None,
    ) -> str:
        """Start a new empty profile draft, replacing any current draft."""
        builder = SpecBuilder.empty(
            name,
            version,
            display_name=display_name,
            description=description,
            ontology=ontology,
        )
        _set_draft(get_mcp_state(), builder)
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_clone(profile: str, version: str) -> str:
        """Start a draft from a built-in or user spec, replacing any current draft."""
        try:
            builder = SpecBuilder.from_template(profile, version)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        _set_draft(get_mcp_state(), builder)
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_import_yaml(yaml_text: str) -> str:
        """Start a draft from a YAML spec document, replacing any current draft."""
        try:
            builder = SpecBuilder.from_yaml(yaml_text)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        _set_draft(get_mcp_state(), builder)
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_status() -> str:
        """Summarize the current draft (name, version, root, entities, rules)."""
        try:
            builder = _require_draft(get_mcp_state())
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_preview_yaml() -> str:
        """Return the current draft serialized to YAML."""
        try:
            builder = _require_draft(get_mcp_state())
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return builder.to_yaml()

    @mcp.tool()
    def spec_validate() -> str:
        """Validate the draft via a full model build; returns the issue list."""
        try:
            builder = _require_draft(get_mcp_state())
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        issues = builder.validate()
        return json.dumps({"valid": not issues, "issues": issues}, indent=2)

    @mcp.tool()
    def spec_save(name: str | None = None) -> str:
        """Persist the draft to the user specs directory."""
        from metaseed.specs.persistence import save_spec

        try:
            builder = _require_draft(get_mcp_state())
            path = save_spec(builder.spec, name)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps({"status": "saved", "path": str(path)}, indent=2)

    # ------------------------------------------------------------------
    # Profile metadata
    # ------------------------------------------------------------------
    @mcp.tool()
    def spec_set_metadata(
        name: str | None = None,
        version: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        ontology: str | None = None,
    ) -> str:
        """Update profile-level fields. Unset arguments are left unchanged."""
        try:
            builder = _require_draft(get_mcp_state())
            builder.set_metadata(
                **_clean(
                    {
                        "name": name,
                        "version": version,
                        "display_name": display_name,
                        "description": description,
                        "ontology": ontology,
                    }
                )
            )
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_set_root_entity(entity: str) -> str:
        """Set the root entity (must already exist)."""
        try:
            builder = _require_draft(get_mcp_state())
            builder.set_root_entity(entity)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------
    @mcp.tool()
    def spec_add_entity(
        name: str, description: str = "", ontology_term: str | None = None
    ) -> str:
        """Add an entity to the draft."""
        try:
            builder = _require_draft(get_mcp_state())
            builder.add_entity(
                name, description=description, ontology_term=ontology_term
            )
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_update_entity(
        name: str,
        description: str | None = None,
        ontology_term: str | None = None,
    ) -> str:
        """Update an entity's description and/or ontology term."""
        try:
            builder = _require_draft(get_mcp_state())
            builder.update_entity(
                name, description=description, ontology_term=ontology_term
            )
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_rename_entity(old_name: str, new_name: str) -> str:
        """Rename an entity, cascading every reference to it."""
        try:
            builder = _require_draft(get_mcp_state())
            builder.rename_entity(old_name, new_name)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_delete_entity(name: str) -> str:
        """Delete an entity from the draft."""
        try:
            builder = _require_draft(get_mcp_state())
            builder.delete_entity(name)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------
    @mcp.tool()
    def spec_add_field(
        entity: str,
        name: str,
        field_type: str,
        required: bool = False,
        description: str = "",
        items: str | None = None,
        ontology_term: str | None = None,
        reference: str | None = None,
        parent_ref: str | None = None,
        pattern: str | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        minimum: float | None = None,
        maximum: float | None = None,
        min_items: int | None = None,
        max_items: int | None = None,
        enum: list[str] | None = None,
    ) -> str:
        """Add a field. Nested fields auto-create the parent id and back-reference."""
        try:
            builder = _require_draft(get_mcp_state())
            constraints = _constraints(
                pattern,
                min_length,
                max_length,
                minimum,
                maximum,
                min_items,
                max_items,
                enum,
            )
            builder.add_field(
                entity,
                name,
                field_type,
                required=required,
                description=description,
                **_clean(
                    {
                        "items": items,
                        "ontology_term": ontology_term,
                        "reference": reference,
                        "parent_ref": parent_ref,
                        "constraints": constraints,
                    }
                ),
            )
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_update_field(
        entity: str,
        field_name: str,
        field_type: str | None = None,
        required: bool | None = None,
        description: str | None = None,
        items: str | None = None,
        ontology_term: str | None = None,
        reference: str | None = None,
        parent_ref: str | None = None,
    ) -> str:
        """Update a field in place. Only supplied attributes change."""
        try:
            builder = _require_draft(get_mcp_state())
            builder.update_field(
                entity,
                field_name,
                **_clean(
                    {
                        "type": field_type,
                        "required": required,
                        "description": description,
                        "items": items,
                        "ontology_term": ontology_term,
                        "reference": reference,
                        "parent_ref": parent_ref,
                    }
                ),
            )
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_delete_field(entity: str, field_name: str) -> str:
        """Delete a field by name."""
        try:
            builder = _require_draft(get_mcp_state())
            builder.delete_field(entity, field_name)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_move_field(entity: str, field_name: str, direction: str) -> str:
        """Reorder a field one position 'up' or 'down'."""
        try:
            builder = _require_draft(get_mcp_state())
            builder.move_field(entity, field_name, direction)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)

    # ------------------------------------------------------------------
    # Validation rules
    # ------------------------------------------------------------------
    @mcp.tool()
    def spec_add_rule(
        name: str,
        type: str | None = None,
        message: str | None = None,
        applies_to: str | None = None,
        field: str | None = None,
        reference: str | None = None,
    ) -> str:
        """Add a validation rule to the draft."""
        try:
            builder = _require_draft(get_mcp_state())
            builder.add_rule(
                name,
                **_clean(
                    {
                        "type": type,
                        "message": message,
                        "applies_to": applies_to,
                        "field": field,
                        "reference": reference,
                    }
                ),
            )
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_update_rule(
        rule_name: str,
        message: str | None = None,
        applies_to: str | None = None,
        field: str | None = None,
        reference: str | None = None,
    ) -> str:
        """Update a validation rule in place. Only supplied attributes change."""
        try:
            builder = _require_draft(get_mcp_state())
            builder.update_rule(
                rule_name,
                **_clean(
                    {
                        "message": message,
                        "applies_to": applies_to,
                        "field": field,
                        "reference": reference,
                    }
                ),
            )
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_delete_rule(rule_name: str) -> str:
        """Delete a validation rule by name."""
        try:
            builder = _require_draft(get_mcp_state())
            builder.delete_rule(rule_name)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)
