"""Diff visualization for profile comparisons.

This module generates vis.js compatible graph data for visualizing
differences between profile specifications.
"""

from typing import Any, Self

from .models import ComparisonResult, DiffType, EntityDiff


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
            entity_node = self._create_entity_node(entity_diff, comparison.profiles)
            nodes.append(entity_node)
            entity_node_ids[entity_diff.entity_name.lower()] = entity_node["id"]

        # Create edges between related entities (based on field references)
        entity_edges = self._create_entity_edges(
            comparison.entity_diffs, entity_node_ids, comparison.profiles
        )
        edges.extend(entity_edges)

        return {
            "nodes": nodes,
            "edges": edges,
            "legend": self._create_legend(),
            "statistics": self._create_statistics_summary(comparison),
        }

    def _create_entity_node(
        self: Self, entity_diff: EntityDiff, profiles: list[str]
    ) -> dict[str, Any]:
        """Create a vis.js node for an entity.

        Args:
            entity_diff: Entity difference data.
            profiles: List of profile identifiers.

        Returns:
            Node dictionary for vis.js.
        """
        node_id = self._next_id()
        colors = self.COLORS[entity_diff.diff_type]

        # Build presence info
        presence = []
        for profile_id in profiles:
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
            for spec in fd.profiles.values():
                if spec is not None:
                    field_type = spec.type.value
                    required = spec.required
                    items = spec.items
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
