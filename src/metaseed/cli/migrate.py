"""Migration utilities for metaseed datasets.

Provides commands to migrate datasets to new formats.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from metaseed.paths import get_datasets_dir


def is_node_id(value: str) -> bool:
    """Check if a value looks like an old node ID (8 hex chars)."""
    if not isinstance(value, str):
        return False
    return bool(re.match(r"^[a-f0-9]{8}$", value))


def migrate_dataset(path: Path, dry_run: bool = True) -> dict[str, Any]:
    """Migrate a single dataset to use unique_id for references.

    Args:
        path: Path to dataset JSON file.
        dry_run: If True, don't write changes.

    Returns:
        Migration report with changes made.
    """
    with open(path) as f:
        data = json.load(f)

    entities = data.get("entities", [])

    # Build map of old node IDs to unique IDs
    node_id_to_unique_id: dict[str, str] = {}

    for entity in entities:
        old_node_id = entity.get("_node_id")
        unique_id = entity.get("unique_id")

        if old_node_id and unique_id:
            node_id_to_unique_id[old_node_id] = unique_id

    changes = []

    # Migrate _parent_id to _parent_unique_id
    for entity in entities:
        old_parent_id = entity.get("_parent_id")

        if old_parent_id and old_parent_id in node_id_to_unique_id:
            parent_unique_id = node_id_to_unique_id[old_parent_id]

            if "_parent_unique_id" not in entity:
                entity["_parent_unique_id"] = parent_unique_id
                changes.append(
                    {
                        "entity": entity.get("unique_id") or entity.get("_type"),
                        "field": "_parent_id",
                        "old": old_parent_id,
                        "new": f"_parent_unique_id: {parent_unique_id}",
                    }
                )

            # Remove old field
            del entity["_parent_id"]

        # Remove _node_id (no longer needed)
        if "_node_id" in entity:
            del entity["_node_id"]

    # Migrate entity reference fields (like material_source)
    # These are fields with values that look like node IDs
    for entity in entities:
        entity_type = entity.get("_type", "Unknown")

        for field_name, value in list(entity.items()):
            if field_name.startswith("_"):
                continue

            if is_node_id(value) and value in node_id_to_unique_id:
                new_value = node_id_to_unique_id[value]
                entity[field_name] = new_value
                changes.append(
                    {
                        "entity": entity.get("unique_id") or entity_type,
                        "field": field_name,
                        "old": value,
                        "new": new_value,
                    }
                )

    report = {
        "file": str(path),
        "dataset": data.get("name", path.stem),
        "entity_count": len(entities),
        "changes": changes,
        "migrated": len(changes) > 0,
    }

    if not dry_run and changes:
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        report["saved"] = True
    else:
        report["saved"] = False

    return report


def migrate_all_datasets(dry_run: bool = True) -> list[dict[str, Any]]:
    """Migrate all datasets in the datasets directory.

    Args:
        dry_run: If True, don't write changes.

    Returns:
        List of migration reports.
    """
    datasets_dir = get_datasets_dir()
    reports = []

    for path in sorted(datasets_dir.glob("*.json")):
        try:
            report = migrate_dataset(path, dry_run=dry_run)
            reports.append(report)
        except (OSError, json.JSONDecodeError) as e:
            reports.append(
                {
                    "file": str(path),
                    "error": str(e),
                }
            )

    return reports


def print_migration_report(reports: list[dict[str, Any]]) -> None:
    """Print migration reports in a readable format."""
    total_changes = 0
    migrated_count = 0

    for report in reports:
        if "error" in report:
            print(f"\n[ERROR] {report['file']}: {report['error']}")
            continue

        changes = report.get("changes", [])
        if changes:
            migrated_count += 1
            total_changes += len(changes)

            print(f"\n{report['dataset']} ({report['entity_count']} entities)")
            print("-" * 40)

            for change in changes:
                print(f"  {change['entity']}.{change['field']}")
                print(f"    {change['old']} -> {change['new']}")

            if report.get("saved"):
                print("  [SAVED]")
            else:
                print("  [DRY RUN - not saved]")

    print(f"\n{'=' * 40}")
    print(
        f"Total: {len(reports)} datasets, {migrated_count} need migration, {total_changes} changes"
    )


if __name__ == "__main__":
    import sys

    dry_run = "--apply" not in sys.argv

    if dry_run:
        print("DRY RUN - use --apply to save changes\n")
    else:
        print("APPLYING CHANGES\n")

    reports = migrate_all_datasets(dry_run=dry_run)
    print_migration_report(reports)
