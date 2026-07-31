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
    from mcp.server.fastmcp import FastMCP

    from metaseed.agent.mcp.context import ResolveContext
    from metaseed.specs.schema import ProfileSpec
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


_BUMP_RANK = {"downgrade": -1, "none": 0, "minor": 1, "major": 2}
"""Orders bump levels so a declared bump can be checked against a required one."""


def _load_released(profile: str, version: str) -> ProfileSpec:
    """Load a released profile as the 'old' side of a comparison.

    Raises:
        ValueError: If the profile or version cannot be loaded.
    """
    from metaseed.specs.loader import SpecLoader, SpecLoadError

    try:
        return SpecLoader(profile=profile).load_profile(
            version=version, profile=profile
        )
    except SpecLoadError as exc:
        raise ValueError(f"Cannot load profile {profile} v{version}: {exc}") from exc


def _comparison_payload(
    profile: str, released: ProfileSpec, draft: ProfileSpec
) -> dict[str, Any]:
    """Render a draft-versus-release comparison as the tool's JSON result.

    Raises:
        ValueError: If either version is not ``MAJOR.MINOR``.
    """
    from metaseed.specs.compare import compare_specs
    from metaseed.specs.versioning import declared_bump

    comparison = compare_specs(released, draft)
    declared = declared_bump(released.version, draft.version)
    return {
        "old": {
            "profile": profile,
            "version": released.version,
            "content_hash": released.short_hash,
        },
        "new": {"version": draft.version, "content_hash": draft.short_hash},
        "required_bump": comparison.required_bump,
        "declared_bump": declared,
        "bump_satisfied": _BUMP_RANK[declared] >= _BUMP_RANK[comparison.required_bump],
        "breaking": [change.to_dict() for change in comparison.breaking],
        "compatible": [change.to_dict() for change in comparison.compatible],
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
    mcp: FastMCP, resolve_context: ResolveContext
) -> None:
    """Register the spec-builder tools with the MCP server.

    Args:
        mcp: FastMCP server instance.
        resolve_context: Returns the context for the call being served.
    """

    def current_state() -> AppState:
        """The state of the session this call is serving.

        Named to avoid colliding with the ``state`` locals several tools use.
        """
        return resolve_context().state

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
        _set_draft(current_state(), builder)
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_clone(profile: str, version: str) -> str:
        """Start a draft from a built-in or user spec, replacing any current draft."""
        try:
            builder = SpecBuilder.from_template(profile, version)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        _set_draft(current_state(), builder)
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_import_yaml(yaml_text: str) -> str:
        """Start a draft from a YAML spec document, replacing any current draft."""
        try:
            builder = SpecBuilder.from_yaml(yaml_text)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        _set_draft(current_state(), builder)
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_status() -> str:
        """Summarize the current draft (name, version, root, entities, rules)."""
        try:
            builder = _require_draft(current_state())
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_preview_yaml() -> str:
        """Return the current draft serialized to YAML."""
        try:
            builder = _require_draft(current_state())
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return builder.to_yaml()

    @mcp.tool()
    def spec_validate() -> str:
        """Validate the draft via a full model build; returns the issue list."""
        try:
            builder = _require_draft(current_state())
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        issues = builder.validate()
        return json.dumps({"valid": not issues, "issues": issues}, indent=2)

    @mcp.tool()
    def spec_compare(profile: str, version: str) -> str:
        """Compare the draft against a released version; report the required bump."""
        try:
            builder = _require_draft(current_state())
            released = _load_released(profile, version)
            payload = _comparison_payload(profile, released, builder.spec)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(payload, indent=2)

    @mcp.tool()
    def spec_save(name: str | None = None) -> str:
        """Persist the draft to the user specs directory."""
        from metaseed.specs.persistence import save_spec

        try:
            builder = _require_draft(current_state())
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
            builder = _require_draft(current_state())
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
            builder = _require_draft(current_state())
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
            builder = _require_draft(current_state())
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
            builder = _require_draft(current_state())
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
            builder = _require_draft(current_state())
            builder.rename_entity(old_name, new_name)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_delete_entity(name: str) -> str:
        """Delete an entity from the draft."""
        try:
            builder = _require_draft(current_state())
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
            builder = _require_draft(current_state())
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
            builder = _require_draft(current_state())
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
            builder = _require_draft(current_state())
            builder.delete_field(entity, field_name)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)

    @mcp.tool()
    def spec_move_field(entity: str, field_name: str, direction: str) -> str:
        """Reorder a field one position 'up' or 'down'."""
        try:
            builder = _require_draft(current_state())
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
            builder = _require_draft(current_state())
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
            builder = _require_draft(current_state())
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
            builder = _require_draft(current_state())
            builder.delete_rule(rule_name)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps(_status(builder), indent=2)
