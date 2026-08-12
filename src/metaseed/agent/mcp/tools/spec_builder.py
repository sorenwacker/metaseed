"""MCP tools for authoring profile specifications.

These tools expose the shared :class:`~metaseed.specs.builder.SpecBuilder` over
MCP. They operate on a single active draft held per session (keyed to the
session :class:`AppState`). Entities, fields, and rules are addressed by name.

See `docs/api/spec-builder-mcp.md`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from metaseed.specs.builder import (
    SpecBuilder,
    normalize_markers,
    validate_constraint_names,
    validate_marker_values,
)
from metaseed.specs.schema import Constraints

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from metaseed.agent.mcp.context import ResolveContext
    from metaseed.agent.mcp.ui_session import AppState
    from metaseed.specs.schema import ProfileSpec


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


def _markers(
    *,
    codename: str | None,
    ontologies: list[str] | None,
    within: str | None,
    unique_within: str | None,
    dcat: str | None,
    owns: bool | None,
    is_identifier: bool | None,
    is_label: bool | None,
    example: str | None,
    options: list[str] | None,
    unit: str | None,
    label: str | None,
    tier: str | None,
    isa_tag: str | None,
) -> dict[str, Any]:
    """Collect the field markers both field tools accept.

    The parameter list is the tools' marker signature written once. It is checked
    against :data:`~metaseed.specs.builder.FIELD_MARKER_NAMES` by a test, so a
    marker added to ``FieldSpec`` cannot quietly stay unreachable here.

    Returns:
        The markers to assign: omitted ones dropped, explicitly emptied ones
        mapped to None. See
        :func:`~metaseed.specs.builder.normalize_markers`.
    """
    return normalize_markers(
        {
            "codename": codename,
            "ontologies": ontologies,
            "within": within,
            "unique_within": unique_within,
            "dcat": dcat,
            "owns": owns,
            "is_identifier": is_identifier,
            "is_label": is_label,
            "example": example,
            "options": options,
            "unit": unit,
            "label": label,
            "tier": tier,
            "isa_tag": isa_tag,
        }
    )


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
        """Validate the draft via a full model build; returns issues and warnings.

        `issues` are defects that make the spec invalid; `warnings` are advisory
        (e.g. an entity whose identifier is inferred onto an optional free-text
        field) and never affect `valid`.
        """
        try:
            builder = _require_draft(current_state())
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        issues = builder.validate()
        return json.dumps(
            {"valid": not issues, "issues": issues, "warnings": builder.warnings()},
            indent=2,
        )

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
        codename: str | None = None,
        ontologies: list[str] | None = None,
        unique_within: str | None = None,
        dcat: str | None = None,
        owns: bool | None = None,
        is_identifier: bool | None = None,
        is_label: bool | None = None,
        within: str | None = None,
        example: str | None = None,
        options: list[str] | None = None,
        unit: str | None = None,
        label: str | None = None,
        tier: str | None = None,
        isa_tag: str | None = None,
    ) -> str:
        """Add a field. Nested fields auto-create the parent id and back-reference.

        Beyond the constraints, the declarative markers can be set here:
        `is_identifier` / `is_label` declare which field identifies and which
        labels the entity (overriding the positional convention), `owns` marks a
        containment relationship, and `codename`, `ontologies`, `unique_within`,
        `dcat`, `example`, `options`, `unit`, `label` and `tier` carry field
        metadata. `tier` is one of required/recommended/optional. `isa_tag`
        names the ISA tag the field carries into a SEEK Sample Type attribute.
        """
        markers = _markers(
            codename=codename,
            ontologies=ontologies,
            unique_within=unique_within,
            dcat=dcat,
            owns=owns,
            is_identifier=is_identifier,
            is_label=is_label,
            within=within,
            example=example,
            options=options,
            unit=unit,
            label=label,
            tier=tier,
            isa_tag=isa_tag,
        )
        marker_error = validate_marker_values(markers)
        if marker_error:
            return json.dumps({"error": marker_error})
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
                # On a new field an emptied marker and an omitted one are the
                # same request, so the Nones are dropped rather than assigned.
                **_clean(markers),
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
        pattern: str | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        minimum: float | None = None,
        maximum: float | None = None,
        min_items: int | None = None,
        max_items: int | None = None,
        enum: list[str] | None = None,
        codename: str | None = None,
        ontologies: list[str] | None = None,
        unique_within: str | None = None,
        dcat: str | None = None,
        owns: bool | None = None,
        is_identifier: bool | None = None,
        is_label: bool | None = None,
        within: str | None = None,
        example: str | None = None,
        options: list[str] | None = None,
        unit: str | None = None,
        label: str | None = None,
        tier: str | None = None,
        isa_tag: str | None = None,
        clear: list[str] | None = None,
    ) -> str:
        """Update a field in place. Unset arguments keep their current value.

        Constraints merge: a supplied constraint overwrites that one value and
        leaves the field's other constraints intact (and creates the constraints
        block if the field had none). Because an omitted argument means
        "unchanged", removal needs `clear` -- a list of constraint names
        (pattern, min_length, max_length, minimum, maximum, min_items, max_items,
        enum) to unset. Naming a constraint in both `clear` and an argument is an
        error. Clearing the last constraint drops the block entirely.

        The markers (`is_identifier`, `is_label`, `owns`, `codename`,
        `ontologies`, `unique_within`, `dcat`, `example`, `options`, `unit`,
        `label`, `tier`) are assigned whole and need no `clear`: pass `false`,
        `""` or `[]` to unset one. A list marker is replaced, not merged.
        """
        constraint_values = _clean(
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
        markers = _markers(
            codename=codename,
            ontologies=ontologies,
            unique_within=unique_within,
            dcat=dcat,
            owns=owns,
            is_identifier=is_identifier,
            is_label=is_label,
            within=within,
            example=example,
            options=options,
            unit=unit,
            label=label,
            tier=tier,
            isa_tag=isa_tag,
        )
        # Checked before the first mutation: the attribute update and the
        # constraint merge are two calls, so a bad `clear` name caught by the
        # second would otherwise leave the first already applied.
        name_error = validate_constraint_names(clear or ()) or validate_marker_values(
            markers
        )
        if name_error:
            return json.dumps({"error": name_error})
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
                # Not _clean'd: a normalized None here is an explicit "unset".
                **markers,
            )
            if constraint_values or clear:
                builder.update_field_constraints(
                    entity, field_name, clear=clear or (), **constraint_values
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
