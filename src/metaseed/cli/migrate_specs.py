"""Repair profile specs whose ``version`` is not ``MAJOR.MINOR``.

Since 0.22 a ``ProfileSpec.version`` must match ``^\\d+\\.\\d+$`` (see
:mod:`metaseed.specs.versioning`). Spec files written by earlier releases can
violate that rule -- ``SpecBuilder.from_template`` used to mint versions such as
``1.2-dev-a1b2c3`` -- and such a file is still listed by ``metaseed profiles``
but raises on load. This module finds those files and rewrites the value.

Two properties are load-bearing:

* **Only the version is written.** The rest of the file keeps its key order,
  comments and quoting, because a hand-maintained spec must survive the
  migration otherwise unchanged.
* **Nothing is guessed and nothing is overwritten.** A value with no leading
  integer is reported, not invented; a repair that would put two specs at the
  same ``<name>/<version>`` path is refused, not resolved.

See `docs/api/cli.md#migrate-specs`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from metaseed.specs.versioning import PROFILE_VERSION_PATTERN

RULE_CONFORMING = "already MAJOR.MINOR"
RULE_QUOTED = "quoted the value (YAML parsed it as a number, not a string)"
RULE_STRIPPED_V = "stripped the leading 'v'"
RULE_ADDED_MINOR = "added the missing MINOR component '0'"
RULE_DROPPED_SUFFIX = "dropped the pre-release/build suffix"
RULE_TRUNCATED = "truncated to the first two components"
RULE_NOT_DERIVABLE = (
    "no leading integer, so no MAJOR.MINOR version can be derived from it"
)
RULE_UNLOCATABLE = (
    "the value is not on a top-level 'version:' line, so it cannot be rewritten "
    "without reformatting the file; edit it by hand"
)

_LEADING_V = re.compile(r"^[vV](?=\d)")
_NUMERIC_PREFIX = re.compile(r"^\d+(?:\.\d+)*")
_TOP_LEVEL_VERSION_LINE = re.compile(r"^version:[ \t]*", re.MULTILINE)


class Outcome(Enum):
    """What the migration concluded about one spec file."""

    REPAIRABLE = "repairable"
    """The version can be normalized; written when ``--apply`` is given."""

    MANUAL = "manual"
    """No version is derivable from the value; a human must choose one."""

    COLLISION = "collision"
    """Repairing would put two specs at the same name+version path."""

    ERROR = "error"
    """The file could not be read, parsed, or written."""


@dataclass(frozen=True)
class NormalizedVersion:
    """The result of applying the normalization rules to one value.

    Attributes:
        value: The normalized ``MAJOR.MINOR`` version, or None if the input has
            no leading integer and therefore yields nothing derivable.
        lossy: True when components beyond MAJOR.MINOR were discarded.
        rule: Human-readable description of the rules applied, for the report.
    """

    value: str | None
    lossy: bool
    rule: str


@dataclass
class SpecVersionMigration:
    """One reported spec: what it declares, and what was or would be done.

    Attributes:
        path: Path to the ``profile.yaml``.
        old_version: The version as the file declares it.
        new_version: The normalized version, or None if none was derivable.
        outcome: Why the file is in the report.
        lossy: True when normalizing discarded a patch (or later) component.
        reason: The rule applied, or the reason no repair was made.
        applied: True once the change has actually been written.
        renamed_to: The version directory the spec was moved to, if any.
        rename_target: The directory a repair would move the spec to, if any.
        notes: Extra report lines about consequences of the repair.
        rewritten: The exact file text ``--apply`` would write. Computed while
            planning so a dry run reports what an apply will do, rather than
            discovering only at write time that the value cannot be located.
    """

    path: Path
    old_version: str
    new_version: str | None
    outcome: Outcome
    lossy: bool
    reason: str
    applied: bool = False
    renamed_to: Path | None = None
    rename_target: Path | None = field(default=None, repr=False)
    notes: list[str] = field(default_factory=list)
    rewritten: str | None = field(default=None, repr=False)


def normalize_profile_version(value: str) -> NormalizedVersion:
    """Apply the normalization rules to a declared profile version.

    The rules, in order and combinable: strip a leading ``v``; take the leading
    run of dot-separated integers and drop any pre-release or build suffix after
    it; pad a single integer with MINOR ``0``; truncate three or more components
    to two (lossy, because the patch component is discarded).

    Args:
        value: The version as declared in the spec file.

    Returns:
        The normalized version, whether normalizing lost information, and the
        rules that were applied. ``value`` is None when the input has no leading
        integer -- ``draft`` and ``latest`` are reported, never guessed.
    """
    text = str(value).strip()
    if PROFILE_VERSION_PATTERN.match(text):
        return NormalizedVersion(text, False, RULE_CONFORMING)

    rules: list[str] = []
    remainder = text
    if _LEADING_V.match(remainder):
        remainder = remainder[1:]
        rules.append(RULE_STRIPPED_V)

    numeric = _NUMERIC_PREFIX.match(remainder)
    if numeric is None:
        return NormalizedVersion(None, False, RULE_NOT_DERIVABLE)
    if numeric.end() < len(remainder):
        rules.append(RULE_DROPPED_SUFFIX)

    components = numeric.group(0).split(".")
    lossy = False
    if len(components) == 1:
        components.append("0")
        rules.append(RULE_ADDED_MINOR)
    elif len(components) > 2:
        components = components[:2]
        lossy = True
        rules.append(RULE_TRUNCATED)

    return NormalizedVersion(".".join(components), lossy, "; ".join(rules))


def get_spec_dirs() -> list[Path]:
    """Return the spec trees to scan: built-in specs, then user specs.

    Returns:
        Existing spec root directories.
    """
    from metaseed.paths import get_builtin_specs_dir, get_user_specs_dir

    candidates = [get_builtin_specs_dir(), get_user_specs_dir()]
    return [d for d in candidates if d.exists()]


def find_spec_files(dirs: list[Path]) -> list[Path]:
    """Find every ``profile.yaml`` under the given spec trees.

    Args:
        dirs: Spec root directories.

    Returns:
        Sorted paths, deduplicated across overlapping roots.
    """
    files: set[Path] = set()
    for directory in dirs:
        files.update(directory.glob("**/profile.yaml"))
    return sorted(files)


def _declared_version(document: Any) -> Any:
    """Return the raw ``version`` value of a parsed spec document, or None."""
    if not isinstance(document, dict):
        return None
    return document.get("version")


def _value_token(remainder: str) -> str | None:
    """Split the scalar off the text following ``version:`` on its line.

    Args:
        remainder: Everything after ``version:`` up to the end of the line.

    Returns:
        The scalar as written (quotes included), or None if it is quoted but
        never closed. A trailing comment is not part of the token: in YAML a
        ``#`` starts a comment only after whitespace, so an unquoted value ends
        at the first ``space-#`` or at the end of the line.
    """
    if remainder[:1] in ("'", '"'):
        quote = remainder[0]
        closing = remainder.find(quote, 1)
        return None if closing == -1 else remainder[: closing + 1]
    comment = remainder.find(" #")
    return (remainder if comment == -1 else remainder[:comment]).rstrip()


def _rewrite_version_line(content: str, declared: Any, new_version: str) -> str | None:
    """Replace the value of the top-level ``version:`` key, and nothing else.

    The replaced span is the scalar token itself, verified by re-parsing it and
    checking that it yields the value the document declares. A prefix match is
    not enough: ``version: 1.20`` declares ``1.2``, and splicing that in over
    the first three characters would leave ``'1.2'0``.

    Args:
        content: The full file text.
        declared: The ``version`` value as YAML parsed it.
        new_version: The normalized version to write.

    Returns:
        The new file text, or None if the value could not be located on a
        top-level ``version:`` line -- a flow-style document, for instance -- in
        which case the file is left for a human rather than edited blind.
    """
    match = _TOP_LEVEL_VERSION_LINE.search(content)
    if match is None:
        return None

    line_end = content.find("\n", match.end())
    if line_end == -1:
        line_end = len(content)

    token = _value_token(content[match.end() : line_end])
    if token is None:
        return None
    try:
        if yaml.safe_load(token) != declared:
            return None
    except yaml.YAMLError:
        return None

    value_end = match.end() + len(token)
    return f"{content[: match.end()]}'{new_version}'{content[value_end:]}"


def _plan_file(path: Path, content: str, raw: Any) -> SpecVersionMigration | None:
    """Plan the repair of one spec file, or return None if nothing is needed.

    Args:
        path: Path to the ``profile.yaml``.
        content: The file text, already read.
        raw: The ``version`` value as YAML parsed it.

    Returns:
        The planned migration, or None if the spec's version is already a
        conforming string.
    """
    declared = str(raw)
    normalized = normalize_profile_version(declared)

    # A version YAML parsed as a number is a string in neither the file nor the
    # loaded document, so the spec fails to load even when the digits conform.
    already_correct = normalized.value == declared and isinstance(raw, str)
    if already_correct:
        return None

    if normalized.value is None:
        return SpecVersionMigration(
            path=path,
            old_version=declared,
            new_version=None,
            outcome=Outcome.MANUAL,
            lossy=False,
            reason=normalized.rule,
        )

    rewritten = _rewrite_version_line(content, raw, normalized.value)
    if rewritten is None:
        return SpecVersionMigration(
            path=path,
            old_version=declared,
            new_version=normalized.value,
            outcome=Outcome.MANUAL,
            lossy=normalized.lossy,
            reason=RULE_UNLOCATABLE,
        )

    reason = normalized.rule
    if not isinstance(raw, str):
        reason = (
            f"{RULE_QUOTED}; {reason}" if reason != RULE_CONFORMING else RULE_QUOTED
        )

    # A rename is planned only when the directory carries the same
    # non-conforming string, and only when it actually moves: a spec whose sole
    # fault is an unquoted value keeps its directory, which already names the
    # right version.
    rename_target = None
    if path.parent.name == declared and declared != normalized.value:
        rename_target = path.parent.parent / normalized.value

    return SpecVersionMigration(
        path=path,
        old_version=declared,
        new_version=normalized.value,
        outcome=Outcome.REPAIRABLE,
        lossy=normalized.lossy,
        reason=reason,
        rename_target=rename_target,
        rewritten=rewritten,
    )


def _refuse_collisions(migrations: list[SpecVersionMigration]) -> None:
    """Mark as COLLISION any repair that would share a name+version path.

    Two specs normalizing onto one directory, or one normalizing onto a
    directory that already exists, are both refused: a spec's name and version
    are its identity, and merging two identities silently is worse than leaving
    both unrepaired.

    Args:
        migrations: The planned migrations, updated in place.
    """
    targets: dict[Path, list[SpecVersionMigration]] = {}
    for migration in migrations:
        if migration.outcome is Outcome.REPAIRABLE and migration.rename_target:
            targets.setdefault(migration.rename_target, []).append(migration)

    for target, claimants in targets.items():
        if len(claimants) > 1:
            sources = sorted(m.path.parent.name for m in claimants)
            for migration in claimants:
                migration.outcome = Outcome.COLLISION
                migration.reason = (
                    f"{len(claimants)} specs normalize to {target}: "
                    f"{', '.join(sources)}"
                )
        elif target.exists():
            claimants[0].outcome = Outcome.COLLISION
            claimants[0].reason = f"{target} already exists"


def _note_duplicate_identities(
    migrations: list[SpecVersionMigration], declared: dict[Path, str]
) -> None:
    """Note repairs that leave two specs declaring one name and version.

    Distinct from a collision: the specs sit in different directories, so
    nothing is overwritten and each stays addressable. But a spec's name and
    version are how it is cited elsewhere, so a repair that duplicates a
    published identity must not pass unremarked. ``ProfileSpec.content_hash``
    is what tells the two apart afterwards.

    Args:
        migrations: The planned migrations, updated in place.
        declared: The version every scanned spec declares before migrating.
    """
    final = dict(declared)
    for migration in migrations:
        if migration.outcome is Outcome.REPAIRABLE and migration.new_version:
            final[migration.path] = migration.new_version

    for migration in migrations:
        if migration.outcome is not Outcome.REPAIRABLE or not migration.new_version:
            continue
        profile_dir = migration.path.parent.parent
        others = sorted(
            path.parent.name
            for path, version in final.items()
            if path != migration.path
            and path.parent.parent == profile_dir
            and version == migration.new_version
        )
        if others:
            migration.notes.append(
                f"another spec under '{profile_dir.name}' also declares version "
                f"'{migration.new_version}': {', '.join(others)}"
            )


def plan_spec_version_migration(files: list[Path]) -> list[SpecVersionMigration]:
    """Plan the repair of every non-conforming spec among ``files``.

    Args:
        files: Candidate ``profile.yaml`` paths.

    Returns:
        One entry per spec that is not already loadable, collisions resolved to
        refusals. Conforming specs are not reported.
    """
    migrations: list[SpecVersionMigration] = []
    declared: dict[Path, str] = {}

    for path in files:
        try:
            content = path.read_text(encoding="utf-8")
            document = yaml.safe_load(content)
        except (OSError, yaml.YAMLError) as exc:
            migrations.append(
                SpecVersionMigration(
                    path=path,
                    old_version="",
                    new_version=None,
                    outcome=Outcome.ERROR,
                    lossy=False,
                    reason=f"could not read the spec: {exc}",
                )
            )
            continue

        raw = _declared_version(document)
        if raw is None:
            continue
        declared[path] = str(raw)

        migration = _plan_file(path, content, raw)
        if migration is not None:
            migrations.append(migration)

    _refuse_collisions(migrations)
    _note_duplicate_identities(migrations, declared)
    return migrations


def _apply(migration: SpecVersionMigration) -> None:
    """Write one planned repair, updating the migration with what happened."""
    assert migration.rewritten is not None
    try:
        migration.path.write_text(migration.rewritten, encoding="utf-8")
        migration.applied = True

        if migration.rename_target is not None:
            migration.path.parent.rename(migration.rename_target)
            migration.renamed_to = migration.rename_target
            migration.path = migration.rename_target / migration.path.name
    except OSError as exc:
        migration.outcome = Outcome.ERROR
        migration.reason = f"could not write the spec: {exc}"


def migrate_spec_versions(
    dry_run: bool = True, dirs: list[Path] | None = None
) -> list[SpecVersionMigration]:
    """Find and (optionally) repair specs whose version is not MAJOR.MINOR.

    Args:
        dry_run: If True (the default), report without writing anything.
        dirs: Spec trees to scan. Defaults to the built-in and user spec dirs.

    Returns:
        One entry per spec that is not already loadable. An empty list means
        every spec conforms.
    """
    migrations = plan_spec_version_migration(
        find_spec_files(dirs if dirs is not None else get_spec_dirs())
    )
    if not dry_run:
        for migration in migrations:
            if migration.outcome is Outcome.REPAIRABLE:
                _apply(migration)
    return migrations


def has_failures(migrations: list[SpecVersionMigration]) -> bool:
    """Report whether a repair was attempted and did not complete.

    A refused collision and a filesystem error are failures. A spec needing a
    manual fix is a finding, not a failure: the command did everything it could
    do without guessing.

    Args:
        migrations: The reported migrations.

    Returns:
        True if the process should exit non-zero after ``--apply``.
    """
    return any(m.outcome in (Outcome.COLLISION, Outcome.ERROR) for m in migrations)


def _flags(migration: SpecVersionMigration) -> str:
    """Return the report label(s) for one migration."""
    if migration.outcome is Outcome.MANUAL:
        return "[NEEDS MANUAL FIX]"
    if migration.outcome is Outcome.COLLISION:
        return "[COLLISION]"
    if migration.outcome is Outcome.ERROR:
        return "[ERROR]"
    label = "[REPAIRED]" if migration.applied else "[WOULD REPAIR]"
    return f"{label} [LOSSY]" if migration.lossy else label


def _directory_note(migration: SpecVersionMigration) -> list[str]:
    """Return the report line(s) about the spec's version directory, if any.

    A spec is addressed by its directory name, so the report says whether that
    name followed the repaired version. Silence means the directory already
    names the version the file declares.

    Args:
        migration: The reported migration.

    Returns:
        Zero or one note line.
    """
    if migration.renamed_to is not None:
        return [f"directory renamed to {migration.renamed_to}"]
    if migration.outcome is not Outcome.REPAIRABLE:
        return []
    if migration.path.parent.name == migration.new_version:
        return []
    return [
        f"directory is named {migration.path.parent.name!r}, not the declared "
        "version; left in place"
    ]


def print_migration_report(
    migrations: list[SpecVersionMigration], dry_run: bool
) -> None:
    """Print one line per reported spec, then a summary.

    Args:
        migrations: The reported migrations.
        dry_run: Whether the run wrote anything, which changes the wording.
    """
    print()
    print(
        "=== DRY RUN (no changes written) ===" if dry_run else "=== SPECS MIGRATED ==="
    )
    print()

    for migration in migrations:
        target = migration.new_version or "-"
        print(f"{_flags(migration)} {migration.path}")
        print(f"         version: {migration.old_version!r} -> {target!r}")
        print(f"         {migration.reason}")
        for note in _directory_note(migration) + migration.notes:
            print(f"         {note}")

    counted = dict.fromkeys(Outcome, 0)
    lossy = 0
    for migration in migrations:
        counted[migration.outcome] += 1
        if migration.lossy and migration.outcome is Outcome.REPAIRABLE:
            lossy += 1

    verb = "repairable" if dry_run else "repaired"
    print()
    print(
        f"Summary: {len(migrations)} non-conforming spec(s); "
        f"{counted[Outcome.REPAIRABLE]} {verb} "
        f"({lossy} lossy), "
        f"{counted[Outcome.MANUAL]} needing a manual fix, "
        f"{counted[Outcome.COLLISION]} refused as a collision, "
        f"{counted[Outcome.ERROR]} error(s)"
    )
    if any(
        m.rename_target is not None and m.outcome is Outcome.REPAIRABLE
        for m in migrations
    ):
        renamed = "renamed" if not dry_run else "will be renamed"
        print(
            f"Note: version directories {renamed}. A saved dataset records the "
            "profile version it was created against, so update the 'version' "
            "field of any dataset that names an old one."
        )
    if dry_run and counted[Outcome.REPAIRABLE]:
        print("Run with --apply to write these changes")
