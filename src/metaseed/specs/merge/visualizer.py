"""Diff visualization for profile comparisons.

This module generates vis.js compatible graph data for visualizing
differences between profile specifications.
"""

from typing import Any, Self

from metaseed.specs.schema import FieldSpec, ValidationRuleSpec

from .models import ComparisonResult, DiffType, EntityDiff

RULE_EDGE_COLOR = "#b26a00"


class DiffVisualizer:
    """Generates visualization data for profile diffs.

    Produces vis.js compatible node and edge data with diff-appropriate
    colors and styling.
    """

    # Color scheme for diff types
    COLORS = {
        DiffType.UNCHANGED: {"background": "#e0e0e0", "border": "#9e9e9e"},
        DiffType.ADDED: {"background": "#c8e6c9", "border": "#4caf50"},
        DiffType.REMOVED: {"background": "#ffcdd2", "border": "#f44336"},
        DiffType.MODIFIED: {"background": "#fff3e0", "border": "#ff9800"},
        DiffType.CONFLICT: {"background": "#ffebee", "border": "#d32f2f"},
    }

    # Shape for entities
    ENTITY_SHAPE = "box"

    def __init__(self: Self) -> None:
        """Initialize the visualizer."""
        self._node_id_counter = 0

    def build_diff_graph(
        self: Self,
        comparison: ComparisonResult,
        show_unchanged: bool = True,
    ) -> dict[str, Any]:
        """Build vis.js compatible graph data from comparison.

        Args:
            comparison: ComparisonResult to visualize.
            show_unchanged: Whether to include unchanged entities.

        Returns:
            Dictionary with nodes, edges, and legend data.
        """
        self._node_id_counter = 0
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        # Track entity node IDs for edge creation
        entity_node_ids: dict[str, int] = {}

        for entity_diff in comparison.entity_diffs:
            # Skip unchanged if not showing
            if not show_unchanged and entity_diff.diff_type == DiffType.UNCHANGED:
                continue

            # Create entity node (fields are included in the node data, not as separate nodes)
            entity_node = self._create_entity_node(entity_diff, comparison)
            nodes.append(entity_node)
            entity_node_ids[entity_diff.entity_name.lower()] = entity_node["id"]

        # Create edges between related entities (based on field references)
        entity_edges = self._create_entity_edges(
            comparison.entity_diffs, entity_node_ids, comparison.profiles
        )
        edges.extend(entity_edges)
        edges.extend(_rule_edges(comparison, entity_node_ids))

        return {
            "nodes": nodes,
            "edges": edges,
            "legend": self._create_legend(),
            "statistics": self._create_statistics_summary(comparison),
            # Every rule of every profile, so the page can list the ones that
            # span entities; each entity node also carries its own.
            "rules": {
                pid: [_rule_details(rule) for rule in spec.validation_rules]
                for pid, spec in comparison.profile_specs.items()
            },
            # What the profile says about itself -- the builder's profile form.
            "profiles_meta": {
                pid: {
                    "name": spec.name,
                    "version": spec.version,
                    "display_name": spec.display_name,
                    "description": spec.description,
                    "ontology": spec.ontology,
                    "root_entity": spec.root_entity,
                }
                for pid, spec in comparison.profile_specs.items()
            },
        }

    def _create_entity_node(
        self: Self, entity_diff: EntityDiff, comparison: ComparisonResult
    ) -> dict[str, Any]:
        """Create a vis.js node for an entity.

        Args:
            entity_diff: Entity difference data.
            comparison: The comparison, for the profiles and their rules.

        Returns:
            Node dictionary for vis.js.
        """
        node_id = self._next_id()
        colors = self.COLORS[entity_diff.diff_type]

        # Build presence info
        presence = []
        for profile_id in comparison.profiles:
            present = entity_diff.profiles.get(profile_id, False)
            presence.append(f"{'Y' if present else 'N'}")

        # Build title (tooltip)
        title_lines = [
            f"<b>{entity_diff.entity_name}</b>",
            f"Status: {entity_diff.diff_type.value}",
            f"Profiles: {' | '.join(presence)}",
        ]

        if entity_diff.has_conflicts:
            conflicts = [fd.field_name for fd in entity_diff.conflicting_fields]
            title_lines.append(f"Conflicts: {', '.join(conflicts)}")

        # Build field info for ERD display
        fields_data = []
        for fd in entity_diff.field_diffs:
            # Get field type from first available profile
            field_type = "?"
            required = False
            items = None
            # The closed vocabulary a field takes its values from, so the
            # explorer can show it: the terms are what a user needs to see.
            vocabulary: list[str] = []
            details: dict[str, Any] = {}
            for spec in fd.profiles.values():
                if spec is not None:
                    field_type = spec.type.value
                    required = spec.required
                    items = spec.items
                    if spec.constraints and spec.constraints.enum:
                        vocabulary = list(spec.constraints.enum)
                    details = _field_details(spec)
                    break

            # Determine which profiles have this field
            field_profiles = [
                pid for pid, spec in fd.profiles.items() if spec is not None
            ]

            fields_data.append(
                {
                    "name": fd.field_name,
                    "type": field_type,
                    "required": required,
                    "items": items,
                    "vocabulary": vocabulary,
                    "details": details,
                    "diff_type": fd.diff_type.value,
                    "profiles": field_profiles,
                    "attributes_changed": fd.attributes_changed,
                }
            )

        return {
            "id": node_id,
            "label": entity_diff.entity_name,
            "shape": self.ENTITY_SHAPE,
            "color": colors,
            "font": {"bold": True},
            "title": "<br>".join(title_lines),
            "borderWidth": 3 if entity_diff.has_conflicts else 2,
            "data": {
                "type": "entity",
                "name": entity_diff.entity_name,
                "diff_type": entity_diff.diff_type.value,
                "profiles": entity_diff.profiles,
                "field_count": len(entity_diff.field_diffs),
                "conflict_count": len(entity_diff.conflicting_fields),
                "fields": fields_data,
                **_entity_details(comparison, entity_diff.entity_name),
                "seek": _seek_for(comparison, entity_diff.entity_name),
                "rules": _rules_for(comparison, entity_diff.entity_name),
            },
        }

    def _create_entity_edges(  # noqa: C901
        self: Self,
        entity_diffs: list[EntityDiff],
        entity_node_ids: dict[str, int],
        all_profile_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Create edges between related entities.

        Args:
            entity_diffs: List of entity differences.
            entity_node_ids: Mapping of entity name to node ID.
            all_profile_ids: List of all profile IDs being compared.

        Returns:
            List of edge dictionaries.
        """
        edges: list[dict[str, Any]] = []
        # Track (from, to, label, is_reference) -> set of profile_ids with this edge
        edge_profiles: dict[tuple[int, int, str, bool], set[str]] = {}

        for entity_diff in entity_diffs:
            entity_lower = entity_diff.entity_name.lower()
            if entity_lower not in entity_node_ids:
                continue

            from_id = entity_node_ids[entity_lower]

            # Find relationships from field types - check ALL profiles
            for field_diff in entity_diff.field_diffs:
                for profile_id, spec in field_diff.profiles.items():
                    if spec is None:
                        continue

                    # Check for nested entity relationships (entity/list types)
                    target = None
                    is_reference = False
                    if spec.type.value == "entity" or (
                        spec.type.value == "list" and spec.items
                    ):
                        target = spec.items

                    # Check for reference relationships (reference property)
                    if spec.reference:
                        # Reference format is "Entity.field" (e.g., "Study.alias")
                        ref_target = spec.reference.split(".")[0]
                        if ref_target.lower() in entity_node_ids:
                            to_id = entity_node_ids[ref_target.lower()]
                            edge_key = (from_id, to_id, field_diff.field_name, True)
                            if edge_key not in edge_profiles:
                                edge_profiles[edge_key] = set()
                            edge_profiles[edge_key].add(profile_id)

                    # Create edge for nested relationships
                    if target and target.lower() in entity_node_ids:
                        to_id = entity_node_ids[target.lower()]
                        # Include is_reference in the key to track edge type
                        edge_key = (from_id, to_id, field_diff.field_name, is_reference)

                        if edge_key not in edge_profiles:
                            edge_profiles[edge_key] = set()
                        edge_profiles[edge_key].add(profile_id)

        # Create edges with colors based on profile presence (base-relative)
        # First profile is the base/reference
        base_profile = all_profile_ids[0] if all_profile_ids else None
        is_explore_mode = len(all_profile_ids) == 1

        for (from_id, to_id, label, is_reference), profiles in edge_profiles.items():
            if is_explore_mode:
                # Explore mode: use spec-builder colors
                # Green for nested, different color for reference
                color = "#7c4a6b" if is_reference else "#4a7c59"
            else:
                in_base = base_profile in profiles if base_profile else False
                in_others = any(p in profiles for p in all_profile_ids[1:])

                # Determine color based on base-relative presence
                if in_base and in_others:
                    # Edge in both base and compare - unchanged (gray)
                    color = "#666666"
                elif in_base and not in_others:
                    # Edge only in base - removed (red)
                    color = "#f44336"
                elif not in_base and in_others:
                    # Edge only in compare - added (green)
                    color = "#4caf50"
                else:
                    # Shouldn't happen, but default to gray
                    color = "#666666"

            edges.append(
                {
                    "from": from_id,
                    "to": to_id,
                    "arrows": "to",
                    "color": {"color": color},
                    "width": 2,
                    "label": label,
                    "font": {"size": 8},
                    "title": f"In: {', '.join(sorted(profiles))}",
                    "dashes": is_reference,
                }
            )

        return edges

    def _create_legend(self: Self) -> list[dict[str, Any]]:
        """Create legend data for the visualization.

        Returns:
            List of legend items.
        """
        return [
            {
                "label": "Unchanged",
                "color": self.COLORS[DiffType.UNCHANGED],
                "description": "Same in all profiles",
            },
            {
                "label": "Added",
                "color": self.COLORS[DiffType.ADDED],
                "description": "Present in some profiles only",
            },
            {
                "label": "Removed",
                "color": self.COLORS[DiffType.REMOVED],
                "description": "Missing from some profiles",
            },
            {
                "label": "Modified",
                "color": self.COLORS[DiffType.MODIFIED],
                "description": "Different values across profiles",
            },
            {
                "label": "Conflict",
                "color": self.COLORS[DiffType.CONFLICT],
                "description": "Incompatible differences requiring resolution",
            },
        ]

    def _create_statistics_summary(
        self: Self, comparison: ComparisonResult
    ) -> dict[str, Any]:
        """Create statistics summary for the visualization.

        Args:
            comparison: Comparison result.

        Returns:
            Statistics dictionary.
        """
        stats = comparison.statistics
        return {
            "profiles_compared": len(comparison.profiles),
            "profile_names": comparison.profiles,
            "total_entities": stats.total_entities,
            "common_entities": stats.common_entities,
            "unique_entities": stats.unique_entities,
            "modified_entities": stats.modified_entities,
            "total_fields": stats.total_fields,
            "common_fields": stats.common_fields,
            "modified_fields": stats.modified_fields,
            "conflicting_fields": stats.conflicting_fields,
        }

    def _next_id(self: Self) -> int:
        """Get next unique node ID.

        Returns:
            Unique integer ID.
        """
        self._node_id_counter += 1
        return self._node_id_counter


# The headline attributes the graph shows on the node itself; everything else a
# field has set is a detail the panel lists.
_HEADLINE_FIELD_ATTRIBUTES = frozenset({"name", "type", "required", "items"})


def _field_details(spec: FieldSpec) -> dict[str, Any]:
    """Every attribute a field has set, beyond the headline ones.

    An attribute left at its default is absent, so a plain string field shows
    nothing and a vocabulary-bound identifier shows what makes it one. The
    enumerated vocabulary is carried separately (``vocabulary``) and is not
    repeated here.
    """
    dumped = spec.model_dump(exclude_none=True, exclude=set(_HEADLINE_FIELD_ATTRIBUTES))
    details: dict[str, Any] = {}
    for key, value in dumped.items():
        if value in (False, "", [], {}):
            continue
        if key == "constraints":
            constraints = {
                k: v for k, v in value.items() if v is not None and k != "enum"
            }
            if constraints:
                details["constraints"] = constraints
            continue
        details[key] = value
    return details


def _rule_details(rule: ValidationRuleSpec) -> dict[str, Any]:
    """A validation rule with only the parameters it sets."""
    return {
        k: v for k, v in rule.model_dump(exclude_none=True).items() if v not in ("", [])
    }


def _rule_edges(
    comparison: ComparisonResult, entity_node_ids: dict[str, int]
) -> list[dict[str, Any]]:
    """One dashed edge per rule that references another entity.

    A rule such as ``reference: Study.identifier`` on ``Sample`` is a relation
    between two entities, so the graph draws it, from each entity the rule
    applies to toward the entity it references. Rules without a reference, or
    whose entities are not on the graph, draw nothing.
    """
    edges: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()
    for spec in comparison.profile_specs.values():
        for rule in spec.validation_rules:
            if not rule.reference or "." not in rule.reference:
                continue
            target, _, target_field = rule.reference.partition(".")
            to_id = entity_node_ids.get(target.lower())
            applies = rule.applies_to
            sources = [applies] if isinstance(applies, str) else list(applies or [])
            for source in sources:
                from_id = entity_node_ids.get(source.lower())
                if (
                    from_id is None
                    or to_id is None
                    or (from_id, to_id, rule.name) in seen
                ):
                    continue
                seen.add((from_id, to_id, rule.name))
                edges.append(
                    {
                        "from": from_id,
                        "to": to_id,
                        "arrows": "to",
                        "color": {"color": RULE_EDGE_COLOR},
                        "width": 1,
                        "label": rule.name,
                        "font": {"size": 8, "color": RULE_EDGE_COLOR},
                        "title": (
                            f"Rule {rule.name} ({rule.type}): {source}.{rule.field or '?'}"
                            f" must match {target}.{target_field}"
                        ),
                        "dashes": True,
                        "rule": rule.name,
                    }
                )
    return edges


def _entity_details(comparison: ComparisonResult, entity_name: str) -> dict[str, Any]:
    """The entity's own description and term, from the first profile that has it."""
    for spec in comparison.profile_specs.values():
        entity = spec.entities.get(entity_name)
        if entity is not None:
            return {
                "description": entity.description,
                "ontology_term": entity.ontology_term,
            }
    return {"description": None, "ontology_term": None}


def _rules_for(comparison: ComparisonResult, entity_name: str) -> list[dict[str, Any]]:
    """The rules that apply to ``entity_name``: named in ``applies_to``, or ``all``."""
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for spec in comparison.profile_specs.values():
        for rule in spec.validation_rules:
            applies = rule.applies_to
            targets = [applies] if isinstance(applies, str) else list(applies or [])
            if ("all" in targets or entity_name in targets) and rule.name not in seen:
                seen.add(rule.name)
                found.append(_rule_details(rule))
    return found


def _seek_for(comparison: ComparisonResult, entity_name: str) -> dict[str, Any]:
    """The entity's SEEK mapping, with only what it sets; empty when none."""
    for spec in comparison.profile_specs.values():
        entity = spec.entities.get(entity_name)
        if entity is not None and entity.seek is not None:
            return {
                k: v for k, v in entity.seek.model_dump(exclude_none=True).items() if v
            }
    return {}
