"""Profile tools for MCP server."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from metaseed.specs.loader import SpecLoader, SpecLoadError
from metaseed.specs.schema import EntityDefSpec, FieldSpec

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from metaseed.agent.mcp.context import ResolveContext
    from metaseed.agent.mcp.ui_session import AppState


def _load_entity_def(
    entity_type: str, profile: str, version: str
) -> tuple[EntityDefSpec | None, str | None]:
    """Load entity definition from a profile.

    Args:
        entity_type: Entity type name.
        profile: Profile name.
        version: Profile version.

    Returns:
        Tuple of (entity_def, error_message). One will be None.
    """
    loader = SpecLoader(profile=profile)
    try:
        spec = loader.load_profile(version=version, profile=profile)
        entity_def = spec.entities.get(entity_type)
        if not entity_def:
            return None, f"Entity '{entity_type}' not found in {profile} v{version}"
        return entity_def, None
    except SpecLoadError as e:
        return None, str(e)


def _field_to_dict(field: FieldSpec) -> dict[str, Any]:
    """Convert a FieldSpec to a dictionary for JSON serialization.

    Args:
        field: FieldSpec object.

    Returns:
        Dictionary with field properties.
    """
    field_info: dict[str, Any] = {
        "name": field.name,
        "type": field.type.value,
        "required": field.required,
        "description": field.description,
    }
    if field.codename:
        field_info["codename"] = field.codename
    if field.items:
        field_info["items"] = field.items
    # Richer per-field metadata (#98), present only when declared.
    if field.example is not None:
        field_info["example"] = field.example
    options = field.options
    if options is None and field.constraints and field.constraints.enum:
        options = field.constraints.enum
    if options:
        field_info["options"] = options
    if field.unit:
        field_info["unit"] = field.unit
    if field.label:
        field_info["label"] = field.label
    if field.tier:
        field_info["tier"] = field.tier
    return field_info


def _placeholder_value(field: FieldSpec) -> Any:
    """Return a valid placeholder value for a field by its type.

    Used to build example datasets; values are syntactically valid (e.g. a real
    ISO date) so the example imports cleanly while clearly being placeholders.

    Args:
        field: FieldSpec to produce a placeholder for.

    Returns:
        A placeholder value appropriate to the field's type.
    """
    from metaseed.specs.schema import FieldType

    by_type = {
        FieldType.INTEGER: 0,
        FieldType.FLOAT: 0.0,
        FieldType.BOOLEAN: False,
        FieldType.DATE: "2024-01-01",
        FieldType.DATETIME: "2024-01-01T00:00:00",
        FieldType.URI: "https://example.com",
        FieldType.LIST: [],
    }
    return by_type.get(field.type, f"<{field.name}>")


def _identifier_info(entity_def: Any) -> tuple[str | None, str | None]:
    """Return an entity's identifier field and a note if it deviates.

    The identifier is the first non-reference field (matching the runtime
    EntityHelper convention). A note is returned for entities that break the
    common ``unique_id`` pattern - e.g. Person keys on ``name`` and has no
    ``unique_id`` field - so agents stop assuming ``unique_id`` everywhere.

    Args:
        entity_def: Entity definition spec with a ``fields`` list.

    Returns:
        Tuple of (identifier_field, note). note is None when the entity follows
        the usual ``unique_id`` convention.
    """
    field_names = {f.name for f in entity_def.fields}
    identifier = next(
        (f.name for f in entity_def.fields if f.is_identifier),
        next((f.name for f in entity_def.fields if not f.reference), None),
    )
    note = None
    if identifier and identifier != "unique_id" and "unique_id" not in field_names:
        note = (
            f"Unlike most entities, this type has no 'unique_id' field; "
            f"its identifier is '{identifier}'."
        )
    return identifier, note


def register_profile_tools(  # noqa: C901
    mcp: FastMCP, resolve_context: ResolveContext
) -> None:
    """Register profile tools with the MCP server.

    Most of these read only the spec files, but ``get_field_spec`` reports
    against the active dataset's profile, so this registrar is not stateless
    despite looking it.

    Args:
        mcp: FastMCP server instance.
        resolve_context: Returns the context for the call being served.
    """

    def current_state() -> AppState:
        """The state of the session this call is serving.

        Named to avoid colliding with the ``state`` locals several tools use.
        """
        return resolve_context().state

    @mcp.tool()
    def list_profiles() -> str:
        """List all available profiles with their versions.

        Returns a JSON array of profiles, each with name and available versions.
        Use this to discover what metadata standards are available.
        """
        loader = SpecLoader()
        profiles = loader.list_profiles()
        result = []

        for profile in profiles:
            versions = loader.list_versions(profile)
            result.append(
                {
                    "name": profile,
                    "versions": versions,
                    "latest": versions[-1] if versions else None,
                }
            )

        return json.dumps(result, indent=2)

    @mcp.tool()
    def get_profile_schema(profile: str, version: str) -> str:
        """Get the full schema for a profile including all entities.

        Args:
            profile: Profile name (e.g., "miappe", "isa", "darwin-core").
            version: Profile version (e.g., "1.1", "1.0").

        Returns:
            JSON object with profile metadata and list of entities with their fields.
        """
        loader = SpecLoader(profile=profile)
        try:
            spec = loader.load_profile(version=version, profile=profile)
            entities = {}

            for entity_name in spec.list_entities():
                entity_def = spec.entities[entity_name]
                fields = [_field_to_dict(f) for f in entity_def.fields]

                entities[entity_name] = {
                    "description": entity_def.description,
                    "ontology_term": entity_def.ontology_term,
                    "fields": fields,
                }

            return json.dumps(
                {
                    "name": spec.name,
                    "version": spec.version,
                    "display_name": spec.display_name,
                    "description": spec.description,
                    "root_entity": spec.root_entity,
                    "entities": entities,
                },
                indent=2,
            )
        except SpecLoadError as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def get_profile_relationships(profile: str, version: str) -> str:
        """Get the entity relationship map for a profile.

        Shows, for every entity type, its identifier field, the child entity
        types it can contain, and its cross-reference fields (which entity and
        field each reference points at). Use this before creating entities so
        the dataset is built relationally instead of flat.

        Args:
            profile: Profile name (e.g., "miappe", "isa").
            version: Profile version (e.g., "1.2", "1.0").

        Returns:
            JSON with profile, version, root_entity, and a hierarchy map of
            {entity_type: {identifier, children, cross_references, note?}}.
        """
        from metaseed.facade import ProfileFacade

        loader = SpecLoader(profile=profile)
        try:
            spec = loader.load_profile(version=version, profile=profile)
            facade = ProfileFacade(profile, version)
        except SpecLoadError as e:
            return json.dumps({"error": str(e)})

        hierarchy: dict[str, Any] = {}
        for entity_name in spec.list_entities():
            entity_def = spec.entities[entity_name]
            helper = getattr(facade, entity_name, None)

            # The hierarchy this tool is the authority on is the one
            # create_entity enforces: child_fields honours `owns:`.
            children = sorted(set(helper.child_fields.values())) if helper else []
            cross_references = (
                {
                    field: f"{target_type}.{target_field}"
                    for field, (
                        target_type,
                        target_field,
                    ) in helper.reference_fields.items()
                }
                if helper
                else {}
            )
            identifier, note = _identifier_info(entity_def)

            info: dict[str, Any] = {
                "identifier": identifier,
                "children": children,
                "cross_references": cross_references,
            }
            if note:
                info["note"] = note
            hierarchy[entity_name] = info

        return json.dumps(
            {
                "profile": spec.name,
                "version": spec.version,
                "root_entity": spec.root_entity,
                "hierarchy": hierarchy,
            },
            indent=2,
        )

    @mcp.tool()
    def get_example_dataset(profile: str, version: str) -> str:
        """Get a small, fully cross-referenced example dataset for a profile.

        Returns one instance of every entity type with required fields filled
        with placeholders and every reference field wired to the matching
        example entity, so an agent has a correct relational pattern to copy.
        Values are placeholders; the structure and links are valid. Built from
        the profile's own schema, so it works for any spec.

        Args:
            profile: Profile name (e.g., "miappe", "isa").
            version: Profile version (e.g., "1.2", "1.0").

        Returns:
            JSON with profile, version, a note, and an entities list (each with
            a ``_type`` and example field values).
        """
        from metaseed.facade import ProfileFacade
        from metaseed.specs.schema import FieldType

        loader = SpecLoader(profile=profile)
        try:
            spec = loader.load_profile(version=version, profile=profile)
            facade = ProfileFacade(profile, version)
        except SpecLoadError as e:
            return json.dumps({"error": str(e)})

        # One example identifier per entity type, used to wire references.
        example_ids = {et: f"{et}-example-1" for et in spec.list_entities()}

        entities = []
        for entity_name in spec.list_entities():
            helper = getattr(facade, entity_name, None)
            if not helper:
                continue
            identifier = helper.identifier_field
            references = helper.reference_fields

            row: dict[str, Any] = {"_type": entity_name}
            for field in spec.entities[entity_name].fields:
                name = field.name
                if name == identifier:
                    row[name] = example_ids[entity_name]
                elif name in references:
                    target_type = references[name][0]
                    if target_type in example_ids:
                        target_id = example_ids[target_type]
                        row[name] = (
                            [target_id] if field.type == FieldType.LIST else target_id
                        )
                elif field.required:
                    row[name] = _placeholder_value(field)
            entities.append(row)

        return json.dumps(
            {
                "profile": spec.name,
                "version": spec.version,
                "note": (
                    "Placeholder values; structure and cross-references are "
                    "valid. Replace values with real data before saving."
                ),
                "entities": entities,
            },
            indent=2,
        )

    @mcp.tool()
    def get_field_spec(entity_type: str, field_name: str | None = None) -> str:
        """Get detailed specification for entity fields.

        Returns field definitions including type, constraints, description,
        and ontology terms.

        Args:
            entity_type: Entity type (e.g., "Investigation").
            field_name: Optional specific field name. If not provided, returns all fields.

        Returns:
            JSON with field specifications.
        """
        session = current_state()

        try:
            facade = session.get_or_create_facade()

            helper = getattr(facade, entity_type, None)
            if not helper:
                return json.dumps({"error": f"Unknown entity type: {entity_type}"})

            fields = []
            for field in helper._spec.fields:
                if field_name and field.name != field_name:
                    continue

                # _field_to_dict carries name/type/required/description/codename/
                # items plus the #98 metadata (example/options/unit/label/tier);
                # this tool additionally surfaces ontology_term and constraints.
                field_info = _field_to_dict(field)
                if field.ontology_term:
                    field_info["ontology_term"] = field.ontology_term
                if field.constraints:
                    field_info["constraints"] = field.constraints.model_dump(
                        exclude_none=True
                    )

                fields.append(field_info)

            if field_name:
                if fields:
                    return json.dumps(fields[0], indent=2)
                return json.dumps({"error": f"Field not found: {field_name}"})

            return json.dumps(
                {
                    "entity_type": entity_type,
                    "field_count": len(fields),
                    "required_count": sum(1 for f in fields if f["required"]),
                    "fields": fields,
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def get_entity_fields(entity_type: str, profile: str, version: str) -> str:
        """Get all fields for a specific entity type.

        Returns field definitions including name, type, required status,
        description, and other metadata. Useful for understanding what
        data is needed to create an entity.

        Args:
            entity_type: Entity type name (e.g., "Investigation", "Study").
            profile: Profile name (e.g., "miappe", "isa").
            version: Profile version (e.g., "1.2", "1.0").

        Returns:
            JSON with entity_type, profile, version, field_count,
            required_count, and list of field definitions.
        """
        entity_def, error = _load_entity_def(entity_type, profile, version)
        if entity_def is None:
            return json.dumps({"error": error})

        fields = [_field_to_dict(f) for f in entity_def.fields]
        identifier, note = _identifier_info(entity_def)

        payload: dict[str, Any] = {
            "entity_type": entity_type,
            "profile": profile,
            "version": version,
            "identifier_field": identifier,
            "field_count": len(fields),
            "required_count": sum(1 for f in fields if f["required"]),
            "fields": fields,
        }
        if note:
            payload["note"] = note
        return json.dumps(payload, indent=2)

    @mcp.tool()
    def get_required_fields(entity_type: str, profile: str, version: str) -> str:
        """Get the field names a profile marks required for an entity type.

        Required drives validation reporting, not creation: an entity saves
        with any of these missing, and validate_dataset then reports each gap.
        Record what the source actually states and leave the rest empty rather
        than inventing a value to satisfy this list.

        Args:
            entity_type: Entity type name (e.g., "Investigation", "Study").
            profile: Profile name (e.g., "miappe", "isa").
            version: Profile version (e.g., "1.2", "1.0").

        Returns:
            JSON with entity_type, profile, version, and required_fields list.
        """
        entity_def, error = _load_entity_def(entity_type, profile, version)
        if entity_def is None:
            return json.dumps({"error": error})

        required_fields = [f.name for f in entity_def.fields if f.required]
        identifier, note = _identifier_info(entity_def)

        payload: dict[str, Any] = {
            "entity_type": entity_type,
            "profile": profile,
            "version": version,
            "identifier_field": identifier,
            "required_fields": required_fields,
        }
        if note:
            payload["note"] = note
        return json.dumps(payload, indent=2)

    @mcp.tool()
    def get_entity_template(entity_type: str, profile: str, version: str) -> str:
        """Get a template for creating an entity with placeholder values.

        Returns a template object with placeholder values by field type:
        - string (required): "<required>"
        - integer: 0
        - float: 0.0
        - date: "YYYY-MM-DD"
        - datetime: "YYYY-MM-DDTHH:MM:SS"
        - uri: "https://example.com"
        - list: []
        - boolean: false
        - optional fields: null

        Args:
            entity_type: Entity type name (e.g., "Investigation", "Study").
            profile: Profile name (e.g., "miappe", "isa").
            version: Profile version (e.g., "1.2", "1.0").

        Returns:
            JSON with entity_type, template object, and _required list.
        """
        from metaseed.specs.schema import FieldType

        entity_def, error = _load_entity_def(entity_type, profile, version)
        if entity_def is None:
            return json.dumps({"error": error})

        template: dict[str, Any] = {}
        required_fields = []

        for field in entity_def.fields:
            if field.required:
                required_fields.append(field.name)
                # Required field placeholders by type
                if field.type == FieldType.STRING:
                    template[field.name] = "<required>"
                elif field.type == FieldType.INTEGER:
                    template[field.name] = 0
                elif field.type == FieldType.FLOAT:
                    template[field.name] = 0.0
                elif field.type == FieldType.DATE:
                    template[field.name] = "YYYY-MM-DD"
                elif field.type == FieldType.DATETIME:
                    template[field.name] = "YYYY-MM-DDTHH:MM:SS"
                elif field.type == FieldType.URI:
                    template[field.name] = "https://example.com"
                elif field.type == FieldType.BOOLEAN:
                    template[field.name] = False
                elif field.type == FieldType.LIST:
                    template[field.name] = []
                elif field.type == FieldType.ENTITY:
                    template[field.name] = None
                else:
                    template[field.name] = "<required>"
            else:
                # Optional fields are null
                template[field.name] = None

        identifier, note = _identifier_info(entity_def)
        payload: dict[str, Any] = {
            "entity_type": entity_type,
            "identifier_field": identifier,
            "template": template,
            "_required": required_fields,
        }
        if note:
            payload["note"] = note
        return json.dumps(payload, indent=2)
