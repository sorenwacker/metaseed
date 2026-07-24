"""Validation tools for MCP server."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from metaseed.agent.core import ExtractionContext
from metaseed.specs.loader import SpecLoadError
from metaseed.utils.json import DateAwareEncoder

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from metaseed.facade import ProfileFacade
    from metaseed.ui.state import AppState, TreeNode


def register_validation_tools(  # noqa: C901
    mcp: FastMCP, get_mcp_state: Callable[[], AppState]
) -> None:
    """Register validation tools with the MCP server.

    Args:
        mcp: FastMCP server instance.
        get_mcp_state: Function to get MCP state.
    """

    @mcp.tool()
    def validate_extracted(data: str, profile: str, version: str, entity: str) -> str:
        """Validate extracted data against the entity specification.

        Checks required fields, type constraints, and field-level validations.

        Args:
            data: JSON string of extracted instances.
            profile: Profile name.
            version: Profile version.
            entity: Entity name.

        Returns:
            JSON object with validation results for each instance.
        """
        try:
            instances = json.loads(data)
            if not isinstance(instances, list):
                instances = [instances]

            ctx = ExtractionContext.from_profile(profile, version)
            results = []

            for i, instance in enumerate(instances):
                errors = ctx.validate_instance(instance, entity)
                results.append(
                    {
                        "index": i,
                        "valid": len(errors) == 0,
                        "errors": [
                            {"field": e.field, "message": e.message, "value": e.value}
                            for e in errors
                        ],
                    }
                )

            return json.dumps(
                {
                    "total": len(instances),
                    "valid": sum(1 for r in results if r["valid"]),
                    "invalid": sum(1 for r in results if not r["valid"]),
                    "results": results,
                },
                indent=2,
            )

        except (json.JSONDecodeError, SpecLoadError) as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def validate_entity(node_id: str) -> str:
        """Validate a single entity against its specification.

        Checks the entity data against all field validations
        and cross-entity rules.

        Args:
            node_id: The entity's node ID.

        Returns:
            JSON with validation results.
        """
        from metaseed.validators import validate_entity_with_report

        state = get_mcp_state()

        try:
            node = state.nodes_by_id.get(node_id)
            if not node:
                return json.dumps({"error": f"Entity not found: {node_id}"})

            if not node.instance:
                return json.dumps({"error": "Entity has no instance data"})

            facade = state.get_or_create_facade()

            # Validate via Pydantic
            helper = getattr(facade, node.entity_type, None)
            if not helper:
                return json.dumps({"error": f"Unknown entity type: {node.entity_type}"})

            data = node.instance.model_dump(exclude_none=True)

            # Use comprehensive validation with check reporting
            validation_checks = validate_entity_with_report(
                data=data,
                entity_type=node.entity_type,
                profile=facade.profile,
                version=facade.version,
            )

            # Build checks and errors lists
            checks = []
            errors = []
            for check in validation_checks:
                check_dict = {
                    "field": check.field,
                    "check": check.check,
                    "passed": check.passed,
                }
                if check.message:
                    check_dict["message"] = check.message
                checks.append(check_dict)
                if not check.passed:
                    errors.append(
                        {
                            "field": check.field,
                            "message": check.message or f"{check.check} check failed",
                            "rule": check.check,
                        }
                    )

            return json.dumps(
                {
                    "id": node.id,
                    "entity_type": node.entity_type,
                    "valid": len(errors) == 0,
                    "checks": checks,
                    "errors": errors,
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def validate_dataset() -> str:
        """Validate all entities in the current dataset.

        Runs validation on all entities and reports any issues found.

        Returns:
            JSON with validation summary and detailed results.
        """
        state = get_mcp_state()

        try:
            facade = state.get_or_create_facade()
            results: list[dict[str, Any]] = []

            for node in state.entity_tree:
                _validate_node_recursive(node, facade, results)

            return json.dumps(
                {
                    "total": len(results),
                    "valid": sum(1 for r in results if r["valid"]),
                    "invalid": sum(1 for r in results if not r["valid"]),
                    "results": results,
                },
                indent=2,
                cls=DateAwareEncoder,
            )

        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def validate_relationships() -> str:  # noqa: C901
        """Report relationship-completeness gaps the schema implies.

        Unlike validate_dataset (per-entity field rules), this flags links that
        the spec makes possible but that are unset - so datasets come out
        connected rather than flat. All checks are derived from the active
        profile's nested_fields, reference_fields, and field types; nothing is
        profile-specific.

        Warnings:
        - empty list-reference fields (e.g. a list of ids left empty)
        - entities of a referenced type that nothing points at
        - container entities with no child of a type they can hold

        Returns:
            JSON with total_warnings and a warnings list of {entity, type, issue}.
        """
        state = get_mcp_state()

        try:
            facade = state.get_or_create_facade()
            nodes = list(state.nodes_by_id.values())

            # Which (consumer_type, field) reference each target type.
            consumers_of: dict[str, list[str]] = {}
            for etype in facade.entities:
                helper = getattr(facade, etype, None)
                if not helper:
                    continue
                for field, (target_type, _tf) in helper.reference_fields.items():
                    consumers_of.setdefault(target_type, []).append(f"{etype}.{field}")

            # Identifier values referenced by any entity, per target type.
            referenced: dict[str, set[str]] = {}
            for node in nodes:
                helper = getattr(facade, node.entity_type, None)
                if not helper or not node.instance:
                    continue
                data = node.instance.model_dump(exclude_none=True)
                for field, (target_type, _tf) in helper.reference_fields.items():
                    value = data.get(field)
                    if value is None:
                        continue
                    values = value if isinstance(value, list) else [value]
                    referenced.setdefault(target_type, set()).update(
                        str(v) for v in values
                    )

            warnings = []
            for node in nodes:
                etype = node.entity_type
                helper = getattr(facade, etype, None)
                if not helper:
                    continue
                data = (
                    node.instance.model_dump(exclude_none=True) if node.instance else {}
                )
                label = node.label or node.id

                # Empty list-reference fields.
                for field, (target_type, _tf) in helper.reference_fields.items():
                    if helper.field_info(field).get("type") != "list":
                        continue
                    if not data.get(field):
                        warnings.append(
                            {
                                "entity": label,
                                "type": etype,
                                "issue": f"empty {field} - consider linking "
                                f"{target_type} entities",
                            }
                        )

                # Container with no child of a type it can hold.
                child_types_present = {c.entity_type for c in node.children}
                for child_type in helper.nested_fields.values():
                    if child_type not in child_types_present:
                        warnings.append(
                            {
                                "entity": label,
                                "type": etype,
                                "issue": f"no {child_type} linked",
                            }
                        )

                # Referenced type, but this instance is referenced by nothing.
                if etype in consumers_of:
                    identifier = data.get(helper.identifier_field)
                    if identifier is not None and str(identifier) not in (
                        referenced.get(etype, set())
                    ):
                        consumers = ", ".join(sorted(set(consumers_of[etype])))
                        warnings.append(
                            {
                                "entity": label,
                                "type": etype,
                                "issue": f"not referenced by any {consumers}",
                            }
                        )

            return json.dumps(
                {"total_warnings": len(warnings), "warnings": warnings},
                indent=2,
                cls=DateAwareEncoder,
            )

        except Exception as e:
            return json.dumps({"error": str(e)})


def _validate_node_recursive(
    node: TreeNode, facade: ProfileFacade, results: list[dict[str, Any]]
) -> None:
    """Recursively validate a node and its children.

    Uses comprehensive validation from the validators module, including:
    - Pydantic type checking and constraints (patterns, min/max length, ranges)
    - Custom validation rules from the profile spec

    Args:
        node: TreeNode to validate.
        facade: ProfileFacade instance.
        results: List to append results to.
    """
    from metaseed.validators import validate_entity_with_report

    checks = []
    errors = []

    if node.instance:
        data = node.instance.model_dump(exclude_none=True)

        # Use comprehensive validation with check reporting
        validation_checks = validate_entity_with_report(
            data=data,
            entity_type=node.entity_type,
            profile=facade.profile,
            version=facade.version,
        )

        for check in validation_checks:
            check_dict = {
                "field": check.field,
                "check": check.check,
                "passed": check.passed,
            }
            if check.message:
                check_dict["message"] = check.message
            checks.append(check_dict)
            if not check.passed:
                errors.append(
                    {
                        "field": check.field,
                        "message": check.message or f"{check.check} check failed",
                        "rule": check.check,
                    }
                )

    results.append(
        {
            "id": node.id,
            "entity_type": node.entity_type,
            "label": node.label,
            "valid": len(errors) == 0,
            "checks": checks,
            "errors": errors,
        }
    )

    for child in node.children:
        _validate_node_recursive(child, facade, results)
