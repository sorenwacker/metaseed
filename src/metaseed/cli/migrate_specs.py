"""Migrate specs from parent_ref to reference.

This migration standardizes entity references to use only `reference` field,
deprecating `parent_ref`. The parent-child hierarchy is defined by nested_fields
in the parent entity - the reference field provides the back-link.

Usage:
    uv run python -m metaseed.cli.migrate_specs --dry-run
    uv run python -m metaseed.cli.migrate_specs --apply
"""

from __future__ import annotations

import re
from pathlib import Path


def get_spec_dirs() -> list[Path]:
    """Get all spec directories (built-in and user)."""
    from metaseed.paths import get_builtin_specs_dir, get_user_specs_dir

    dirs = []

    # Built-in specs
    builtin = get_builtin_specs_dir()
    if builtin.exists():
        dirs.append(builtin)

    # User specs
    user_dir = get_user_specs_dir()
    if user_dir.exists():
        dirs.append(user_dir)

    return dirs


def find_spec_files(dirs: list[Path]) -> list[Path]:
    """Find all profile.yaml files in spec directories."""
    files = []
    for d in dirs:
        files.extend(d.glob("**/profile.yaml"))
    return sorted(files)


def migrate_file(path: Path, dry_run: bool = True) -> dict:
    """Migrate a single spec file from parent_ref to reference.

    Args:
        path: Path to the spec file.
        dry_run: If True, don't write changes.

    Returns:
        Migration report with changes made.
    """
    content = path.read_text()
    original = content

    # Count occurrences
    parent_ref_count = len(re.findall(r"^\s*parent_ref:", content, re.MULTILINE))

    if parent_ref_count == 0:
        return {
            "file": str(path),
            "migrated": False,
            "changes": 0,
            "message": "No parent_ref found",
        }

    # Replace parent_ref: with reference:
    # Preserve indentation and value
    new_content = re.sub(
        r"^(\s*)parent_ref:(\s*.+)$",
        r"\1reference:\2",
        content,
        flags=re.MULTILINE,
    )

    changes = parent_ref_count

    if not dry_run and new_content != original:
        path.write_text(new_content)

    return {
        "file": str(path),
        "migrated": True,
        "changes": changes,
        "saved": not dry_run,
        "message": f"Converted {changes} parent_ref to reference",
    }


def migrate_all_specs(dry_run: bool = True) -> list[dict]:
    """Migrate all spec files.

    Args:
        dry_run: If True, report changes without applying.

    Returns:
        List of migration reports.
    """
    dirs = get_spec_dirs()
    files = find_spec_files(dirs)

    reports = []
    for f in files:
        try:
            report = migrate_file(f, dry_run=dry_run)
            reports.append(report)
        except Exception as e:
            reports.append(
                {
                    "file": str(f),
                    "error": str(e),
                }
            )

    return reports


def print_migration_report(reports: list[dict], dry_run: bool) -> None:
    """Print migration report to console."""
    print()
    if dry_run:
        print("=== DRY RUN (no changes written) ===")
    else:
        print("=== MIGRATION APPLIED ===")
    print()

    total_changes = 0
    files_changed = 0

    for report in reports:
        if "error" in report:
            print(f"[ERROR] {report['file']}: {report['error']}")
            continue

        if report.get("migrated"):
            files_changed += 1
            total_changes += report.get("changes", 0)
            status = "[SAVED]" if report.get("saved") else "[WOULD CHANGE]"
            print(f"{status} {report['file']}")
            print(f"         {report['message']}")
        else:
            print(f"[OK] {report['file']} - no changes needed")

    print()
    print(f"Summary: {files_changed} files with {total_changes} total changes")
    if dry_run:
        print("Run with --apply to apply changes")


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate specs from parent_ref to reference"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show what would change without applying (default)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the migration",
    )

    args = parser.parse_args()

    dry_run = not args.apply

    reports = migrate_all_specs(dry_run=dry_run)
    print_migration_report(reports, dry_run=dry_run)


if __name__ == "__main__":
    main()
