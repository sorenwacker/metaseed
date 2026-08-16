"""Dataset validation with reference integrity checking.

This module provides validation for entire datasets, checking that
references between entities are valid.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple, Self, cast

import yaml

from metaseed.profiles import ProfileFactory
from metaseed.services.term_check import Outcome, check_entity_terms
from metaseed.specs.loader import SpecLoader, SpecLoadError
from metaseed.utils import to_snake_case
from metaseed.validators.api import _pydantic_constraint_errors
from metaseed.validators.base import ValidationError
from metaseed.validators.engine import create_engine_for_entity
from metaseed.validators.uniqueness import UniquenessChecker, rules_from_profile


class _ReferenceFieldDef(NamedTuple):
    """A declared reference, resolved for dataset-level checking.

    Attributes:
        name: The field holding the value.
        target: The ``Entity.field`` it names.
        external: Whether the target may live outside this dataset. An external
            value that happens to name a record here is still checked; one that
            does not is reported as *not checked* rather than as broken.
    """

    name: str
    target: str
    external: bool = False


@dataclass
class DatasetValidationResult:
    """Result of dataset validation.

    Attributes:
        errors: List of validation errors.
        warnings: List of validation warnings.
        entity_counts: Count of entities by type.
        files_checked: List of files that were validated.
    """

    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    entity_counts: dict[str, int] = field(default_factory=dict)
    files_checked: list[Path] = field(default_factory=list)

    @property
    def is_valid(self: Self) -> bool:
        """Return True if no errors were found.

        Counts both kinds. Deliberately unchanged: making it ignore
        completeness errors would turn every dataset with an unfilled required
        field from invalid into valid, which is a policy decision for whoever
        owns the data, not a side effect of classifying rules.
        """
        return len(self.errors) == 0

    @property
    def wrong_values(self: Self) -> list[ValidationError]:
        """The errors saying something supplied is wrong.

        True now and still true tomorrow: a term from the wrong ontology, an
        inverted range, an identifier that does not match its profile's
        pattern. A consumer enforcing a specification on every write blocks on
        these.
        """
        return [e for e in self.errors if e.blocks]

    @property
    def unfinished(self: Self) -> list[ValidationError]:
        """The errors saying something is absent or insufficient.

        A required field not filled in, a list short of its minimum. True of
        every dataset at the moment it is created, so a consumer that blocks on
        these cannot create anything (#246); report them, and let the person
        keep working.
        """
        return [e for e in self.errors if not e.blocks]

    def merge(self: Self, other: DatasetValidationResult) -> None:
        """Merge another result into this one.

        Args:
            other: The result to merge.
        """
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.files_checked.extend(other.files_checked)
        for entity_type, count in other.entity_counts.items():
            self.entity_counts[entity_type] = (
                self.entity_counts.get(entity_type, 0) + count
            )


class IdRegistry:
    """Tracks entity IDs for reference validation.

    Used to collect all IDs in a first pass, then validate references
    in a second pass.

    Example:
        >>> registry = IdRegistry()
        >>> registry.register("study", "STU001")
        >>> registry.exists("study", "STU001")
        True
        >>> registry.exists("study", "STU999")
        False
    """

    def __init__(self: Self) -> None:
        """Initialize an empty ID registry."""
        self._ids: dict[str, set[str]] = {}

    def register(self: Self, entity_type: str, entity_id: str) -> None:
        """Register an entity ID.

        Args:
            entity_type: The type of entity (e.g., "study", "observation_unit").
            entity_id: The unique ID of the entity.
        """
        if entity_type not in self._ids:
            self._ids[entity_type] = set()
        self._ids[entity_type].add(entity_id)

    def exists(self: Self, entity_type: str, entity_id: str) -> bool:
        """Check if an entity ID exists.

        Args:
            entity_type: The type of entity.
            entity_id: The ID to check.

        Returns:
            True if the ID exists for the given entity type.
        """
        return entity_id in self._ids.get(entity_type, set())


def _referenced_ids(value: Any) -> list[str]:
    """The identifiers a reference field names, if any.

    A reference field does not always hold one string. It can hold several — a
    study naming its contacts — and it can hold the child itself, embedded,
    which is how every nested document is written. Both were passed straight to
    a set lookup, so validating the shipped ISA and MIAPPE examples raised
    ``TypeError: unhashable type`` and no dataset shaped like them could be
    validated at all.

    An embedded object is not a dangling reference: the entity is right there.
    It is checked in its own right when the walk reaches it, so nothing is lost
    by skipping it here.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


class DatasetValidator:
    """Validates datasets with reference integrity checking.

    Performs two-pass validation:
    1. First pass: Collect all entity IDs into registry
    2. Second pass: Validate each entity and check references

    Example:
        >>> validator = DatasetValidator("miappe", "1.1")
        >>> result = validator.validate_directory(Path("./my_project"))
        >>> if not result.is_valid:
        ...     for error in result.errors:
        ...         print(error)
    """

    def __init__(
        self: Self,
        profile: str | None = None,
        version: str | None = None,
        term_source: Any = None,
    ) -> None:
        """Initialize the dataset validator.

        Args:
            profile: Profile name. If None, uses default profile.
            version: Profile version. If None, uses latest version.
            term_source: Where to check ontology terms. ``None`` asks the
                application's configured sources, which for OLS means a network
                request per term — so a caller that must not do I/O, or that
                wants a particular vocabulary, supplies its own.
        """
        self._term_source = term_source
        factory = ProfileFactory()

        if profile is None:
            profile = factory.get_default_profile()

        if version is None:
            version = factory.get_latest_version(profile)
            if version is None:
                raise ValueError(f"No versions found for profile: {profile}")

        self.profile = profile
        self.version = version
        self._loader = SpecLoader(profile=profile)
        self._registry = IdRegistry()
        self._reference_fields: dict[str, list[_ReferenceFieldDef]] = {}
        # (entity, field, target) -> how many externally-scoped values named
        # nothing here. Accumulated across the whole run and reported once per
        # field: a checklist of 10,000 rows would otherwise say the same thing
        # 10,000 times, and a directory would repeat it per file.
        self._unchecked: dict[tuple[str, str, str], int] = {}
        #: Ontology values a source could not answer for, reported as warnings
        #: so "how much went unverified" is visible rather than silent.
        self._unchecked_terms: list[ValidationError] = []
        # (entity_type, field_name) -> {record identifier: referenced identifier},
        # for the fields that reference their own entity type. Accumulated during
        # reference validation and walked afterwards: a cycle can span files, so
        # it cannot be judged record by record (#250).
        self._self_referencing: dict[tuple[str, str], dict[str, str]] = {}
        self._identifier_fields: dict[str, str] = {}
        self._load_reference_fields()
        self._uniqueness = UniquenessChecker(
            rules_from_profile(self._load_profile_spec())
        )

    def _load_profile_spec(self: Self) -> Any:
        """The profile this validator enforces, or ``None`` if it will not load.

        A profile that cannot be loaded leaves the declared checks with nothing
        to enforce, which the callers already treat as "no rules" rather than
        as an error about the data.
        """
        try:
            return self._loader.load_profile(version=self.version, profile=self.profile)
        except SpecLoadError:
            return None

    def _validate_uniqueness(
        self: Self,
        data: dict[str, Any],
        entity_type: str,
        seen: set[tuple[str, str, str]],
        path: str = "",
        scope_prefix: str = "",
    ) -> list[ValidationError]:
        """Cross-record uniqueness, delegated to the checker that owns it.

        The tree walk stays here — it is this class's — and is handed over, so
        the checker does not reimplement it.
        """
        return self._uniqueness.check(
            data,
            entity_type,
            seen,
            self._traverse_entity_tree,
            path,
            scope_prefix,
        )

    def _load_reference_fields(self: Self) -> None:
        """Load reference field definitions from specs."""
        try:
            entities = self._loader.list_entities(self.version)
        except SpecLoadError:
            return

        for entity_name in entities:
            try:
                spec = self._loader.load_entity(entity_name, self.version)
                refs = []
                for f in spec.fields:
                    if f.reference:
                        refs.append(
                            _ReferenceFieldDef(
                                name=f.name,
                                target=f.reference,
                                external=f.reference_scope == "external",
                            )
                        )
                if refs:
                    # Key by snake_case so lookups during traversal, which use
                    # the snake_case entity type, actually match.
                    self._reference_fields[to_snake_case(entity_name)] = refs
                identifier = next(
                    (f.name for f in spec.fields if f.is_identifier), None
                )
                if identifier:
                    self._identifier_fields[to_snake_case(entity_name)] = identifier
            except SpecLoadError:
                continue

    def _detect_entity_type(self: Self, data: dict[str, Any]) -> str | None:
        """Read the entity type from the data's ``_type`` marker.

        Args:
            data: The data dictionary.

        Returns:
            The lowercased ``_type`` value, or None if absent. The type is read
            from the data, never guessed from profile-specific field names.
        """
        entity_type = data.get("_type")
        return str(entity_type).lower() if entity_type else None

    def _is_known_entity(self: Self, entity_type: str) -> bool:
        """Whether ``entity_type`` resolves to an entity in the active profile.

        Args:
            entity_type: The entity type name to check.

        Returns:
            True if the profile defines the entity, False otherwise.
        """
        try:
            self._loader.load_entity(entity_type, self.version)
        except SpecLoadError:
            return False
        return True

    def _default_entity_type(self: Self) -> str | None:
        """The profile's root entity type, for data lacking a ``_type`` marker.

        Returns:
            The root entity type from the active profile (lowercased), or None
            if the profile cannot be loaded. Profile-agnostic - no entity name
            is hardcoded.
        """
        try:
            spec = self._loader.load_profile(version=self.version, profile=self.profile)
        except SpecLoadError:
            return None
        return spec.root_entity.lower() if spec and spec.root_entity else None

    def _traverse_entity_tree(
        self: Self,
        data: dict[str, Any],
        entity_type: str,
        visitor: Callable[[dict[str, Any], str, str], None],
        path: str = "",
    ) -> None:
        """Traverse entity tree recursively, calling visitor at each node.

        Args:
            data: Entity data dictionary.
            entity_type: Type of the current entity.
            visitor: Callback function(data, entity_type, path) called for each entity.
            path: Current path for error reporting.
        """
        visitor(data, entity_type, path)

        try:
            spec = self._loader.load_entity(entity_type, self.version)
        except SpecLoadError:
            return

        for f in spec.fields:
            if not f.items:
                continue

            child_entity = to_snake_case(f.items)

            if f.type.value == "list":
                items = data.get(f.name, [])
                if not isinstance(items, list):
                    continue

                for i, item in enumerate(items):
                    if isinstance(item, dict):
                        item_path = (
                            f"{path}.{f.name}[{i}]" if path else f"{f.name}[{i}]"
                        )
                        self._traverse_entity_tree(
                            item, child_entity, visitor, item_path
                        )

            elif f.type.value == "entity":
                # A child held singly rather than in a list. Only lists were
                # descended, so an entity nested this way was never visited: its
                # own fields were checked against its *parent's* spec — every one
                # reported as "Extra inputs are not permitted" — and its
                # references were never checked at all. Darwin Core nests both
                # its Event and its Organism this way.
                child = data.get(f.name)
                if isinstance(child, dict):
                    child_path = f"{path}.{f.name}" if path else f.name
                    self._traverse_entity_tree(child, child_entity, visitor, child_path)

    def _collect_ids(
        self: Self,
        data: dict[str, Any],
        entity_type: str,
    ) -> None:
        """Recursively collect entity IDs into the registry.

        Args:
            data: Entity data dictionary.
            entity_type: Type of the entity.
        """

        def register_id(d: dict[str, Any], etype: str, _path: str) -> None:
            for field_name in self._identifier_fields_for(etype):
                value = d.get(field_name)
                if value is not None and isinstance(value, str | int):
                    self._registry.register(etype, str(value))

        self._traverse_entity_tree(data, entity_type, register_id)

    def _identifier_fields_for(self: Self, entity_type: str) -> set[str]:
        """The fields whose values other entities may name.

        Read from the reference declarations themselves: a field declaring
        ``reference: "Occurrence.occurrenceID"`` says, of the Occurrence, that
        its ``occurrenceID`` is what gets referenced. Deriving it this way is
        what makes reference integrity work for a profile that does not use
        MIAPPE's ``unique_id`` convention — only entities carrying a literal
        ``unique_id`` were ever registered, so Darwin Core (``occurrenceID``),
        DiSSCo (``identifier``) and ENA (``alias``) had an empty registry and a
        reference that could never resolve.

        ``unique_id`` is kept unconditionally, so profiles that do use it are
        unaffected whether or not anything references them.
        """
        fields = {"unique_id"}
        for targets in self._reference_fields.values():
            for declared in targets:
                target_entity, _, target_field = declared.target.partition(".")
                if to_snake_case(target_entity) == entity_type and target_field:
                    fields.add(target_field)
        return fields

    def _validate_references(
        self: Self,
        data: dict[str, Any],
        entity_type: str,
        path: str = "",
    ) -> list[ValidationError]:
        """Validate references in entity data.

        Args:
            data: Entity data dictionary.
            entity_type: Type of the entity.
            path: Current path for error reporting.

        Returns:
            List of reference validation errors.
        """
        errors: list[ValidationError] = []

        def check_refs(d: dict[str, Any], etype: str, p: str) -> None:
            for declared in self._reference_fields.get(etype, []):
                # ``target`` is an "Entity.field" string (e.g.
                # "Study.unique_id"); the registered entity type is the
                # snake_case form of the entity part only.
                ref_entity = to_snake_case(declared.target.split(".")[0])
                own_id = None
                if ref_entity == etype:
                    id_field = self._identifier_fields.get(etype)
                    raw = d.get(id_field) if id_field else None
                    own_id = str(raw) if raw not in (None, "") else None
                for ref_value in _referenced_ids(d.get(declared.name)):
                    if own_id is not None:
                        if ref_value == own_id:
                            # Its own ancestor: the target exists, so the
                            # existence check below would pass it (#250).
                            field_path = f"{p}.{declared.name}" if p else declared.name
                            errors.append(
                                ValidationError(
                                    field=field_path,
                                    message=(
                                        f"'{own_id}' names itself in "
                                        f"{declared.name}; a record cannot be "
                                        "its own ancestor"
                                    ),
                                    rule="reference_self",
                                )
                            )
                            continue
                        self._self_referencing.setdefault((etype, declared.name), {})[
                            own_id
                        ] = ref_value
                    if self._registry.exists(ref_entity, ref_value):
                        continue
                    if declared.external:
                        # The target may be a GBIF taxon or a museum record.
                        # Not resolvable from here is not the same as wrong.
                        key = (etype, declared.name, declared.target)
                        self._unchecked[key] = self._unchecked.get(key, 0) + 1
                        continue
                    field_path = f"{p}.{declared.name}" if p else declared.name
                    errors.append(
                        ValidationError(
                            field=field_path,
                            message=(
                                f"Reference not found: {declared.target} '{ref_value}'"
                            ),
                            rule="reference_integrity",
                        )
                    )

        self._traverse_entity_tree(data, entity_type, check_refs, path)
        return errors

    def _reference_cycles(self: Self) -> list[ValidationError]:
        """One error per record inside a closed loop of self-references.

        Every step of a cycle resolves and every record exists, so nothing
        else reports it — while an ancestry query, a tree render or an export
        recursing parents never terminates on it. Reported against the
        cycle's members only: a clean record that merely hangs off a
        pre-existing loop is not to blame for it (#250).
        """
        errors: list[ValidationError] = []
        for (etype, field_name), parent_of in self._self_referencing.items():
            resolved: set[str] = set()
            for start in parent_of:
                if start in resolved:
                    continue
                path: list[str] = []
                seen_at: dict[str, int] = {}
                current: str | None = start
                while current is not None and current in parent_of:
                    if current in resolved:
                        break
                    if current in seen_at:
                        cycle = path[seen_at[current] :]
                        joined = " -> ".join([*cycle, cycle[0]])
                        for member in cycle:
                            errors.append(
                                ValidationError(
                                    field=f"{etype}.{field_name}",
                                    message=(
                                        f"'{member}' is part of a "
                                        f"{field_name} cycle: {joined}"
                                    ),
                                    rule="reference_cycle",
                                )
                            )
                        break
                    seen_at[current] = len(path)
                    path.append(current)
                    current = parent_of.get(current)
                resolved.update(path)
        return errors

    def _unchecked_references(self: Self) -> list[ValidationError]:
        """One report per field whose external values named nothing here.

        Not an error -- an identifier nobody can resolve from here is not
        thereby wrong -- and not silence either, which would hide how much of a
        dataset went unverified.
        """
        return [
            ValidationError(
                field=f"{entity}.{field_name}",
                message=(
                    f"{count} value(s) name {target} outside this dataset and "
                    f"were not checked; the field is declared "
                    f"reference_scope: external"
                ),
                rule="reference_not_checked",
            )
            for (entity, field_name, target), count in self._unchecked.items()
        ]

    def _validate_entity(
        self: Self,
        data: dict[str, Any],
        entity_type: str,
        path: str = "",
    ) -> list[ValidationError]:
        """Validate entity data against spec.

        Args:
            data: Entity data dictionary.
            entity_type: Type of the entity.
            path: Current path for error reporting.

        Returns:
            List of validation errors.
        """
        errors: list[ValidationError] = []

        def validate_node(d: dict[str, Any], etype: str, p: str) -> None:
            try:
                engine = create_engine_for_entity(etype, self.version, self.profile)
                for error in engine.validate(d):
                    field_path = f"{p}.{error.field}" if p else error.field
                    errors.append(
                        ValidationError(
                            field=field_path,
                            message=error.message,
                            rule=error.rule,
                            # Carried, not re-derived: rebuilding the error to
                            # prefix its path silently dropped what the rule
                            # claimed, so every missing field arrived here as a
                            # wrong value.
                            kind=error.kind,
                        )
                    )
            except SpecLoadError:
                pass

            # Pydantic constraint validation (types/patterns/ranges/enums), so the
            # dataset path enforces the same constraints as the single-entity path.
            try:
                spec = SpecLoader(profile=self.profile).load_entity(etype, self.version)
            except (FileNotFoundError, KeyError, ValueError, SpecLoadError):
                return
            for error in _pydantic_constraint_errors(d, spec):
                field_path = f"{p}.{error.field}" if p else error.field
                errors.append(
                    ValidationError(
                        field=field_path,
                        message=error.message,
                        rule=error.rule,
                        kind=error.kind,
                    )
                )

            # A value in an ontology-term field, checked against the ontologies
            # its field names (#215). Reported here because this is the path the
            # application validates through: a check reachable only from the
            # library is one no researcher ever sees.
            for field_name, verdict in check_entity_terms(
                spec.fields, d, self._term_source
            ).items():
                if not verdict.is_problem:
                    # NOT_CHECKED is not a fault in the data. An outage, or an
                    # ontology no configured source carries, must not fill a
                    # dataset with errors it cannot justify — but silence would
                    # hide how much of it went unverified, so it is reported
                    # the way an unchecked reference already is.
                    if verdict.message and verdict.outcome is Outcome.NOT_CHECKED:
                        field_path = f"{p}.{field_name}" if p else field_name
                        self._unchecked_terms.append(
                            ValidationError(
                                field=field_path,
                                message=verdict.message,
                                rule="ontology_term_not_checked",
                            )
                        )
                    continue
                if not verdict.message:
                    continue
                field_path = f"{p}.{field_name}" if p else field_name
                errors.append(
                    ValidationError(
                        field=field_path,
                        message=verdict.message,
                        rule="ontology_term",
                    )
                )

        self._traverse_entity_tree(data, entity_type, validate_node, path)
        return errors

    def _count_entities(
        self: Self,
        data: dict[str, Any],
        entity_type: str,
        counts: dict[str, int],
    ) -> None:
        """Count entities by type.

        Args:
            data: Entity data dictionary.
            entity_type: Type of the entity.
            counts: Dictionary to update with counts.
        """

        def count_node(_d: dict[str, Any], etype: str, _p: str) -> None:
            counts[etype] = counts.get(etype, 0) + 1

        self._traverse_entity_tree(data, entity_type, count_node)

    def validate_file(self: Self, path: Path) -> DatasetValidationResult:
        """Validate a single file.

        Args:
            path: Path to the YAML/JSON file.

        Returns:
            Validation result for the file.
        """
        result = DatasetValidationResult()
        result.files_checked.append(path)

        # Load the file
        try:
            content = path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if data is None:
                data = {}
        except yaml.YAMLError as e:
            result.errors.append(
                ValidationError(
                    field=str(path),
                    message=f"Invalid YAML: {e}",
                    rule="yaml_syntax",
                )
            )
            return result
        except OSError as e:
            result.errors.append(
                ValidationError(
                    field=str(path),
                    message=f"Cannot read file: {e}",
                    rule="file_access",
                )
            )
            return result

        # Detect entity type, falling back to the profile's root entity. The
        # fallback yields ``None`` only when the profile cannot be loaded, a
        # degenerate case the downstream traversal handles as a no-op; cast to
        # ``str`` to satisfy the helper signatures without altering behavior.
        detected_type = self._detect_entity_type(data)
        entity_type = cast("str", detected_type or self._default_entity_type())

        # A file that declares a _type naming no known entity would otherwise be
        # reported valid: the traversal and engine both swallow the resulting
        # SpecLoadError, so no rule ever runs. Flag it instead of failing open.
        if detected_type is not None and not self._is_known_entity(detected_type):
            result.errors.append(
                ValidationError(
                    field="_type",
                    message=f"Unknown entity type: '{data.get('_type')}'",
                    rule="unknown_entity_type",
                )
            )
            return result

        # Reset registry for single file validation
        self._registry = IdRegistry()
        self._unchecked = {}
        self._self_referencing = {}

        # Pass 1: Collect IDs
        self._collect_ids(data, entity_type)

        # Pass 2: Validate entity structure
        result.errors.extend(self._validate_entity(data, entity_type))

        # Pass 3: Validate references
        result.errors.extend(self._validate_references(data, entity_type))

        # Pass 4: Validate declared uniqueness rules across records
        result.errors.extend(self._validate_uniqueness(data, entity_type, set()))

        result.errors.extend(self._reference_cycles())

        # Count entities
        self._count_entities(data, entity_type, result.entity_counts)

        result.warnings.extend(self._unchecked_references())
        result.warnings.extend(self._unchecked_terms)

        return result

    def validate_directory(self: Self, path: Path) -> DatasetValidationResult:
        """Validate all YAML/JSON files in a directory.

        Args:
            path: Path to the directory.

        Returns:
            Combined validation result for all files.
        """
        result = DatasetValidationResult()

        # Reset registry for directory validation
        self._registry = IdRegistry()
        self._unchecked = {}
        self._self_referencing = {}

        # Find all YAML and JSON files
        files = list(path.glob("**/*.yaml")) + list(path.glob("**/*.yml"))
        files.extend(path.glob("**/*.json"))

        if not files:
            result.warnings.append(
                ValidationError(
                    field=str(path),
                    message="No YAML or JSON files found",
                    rule="file_discovery",
                )
            )
            return result

        # Pass 1: Collect all IDs from all files
        file_data: list[tuple[Path, dict[str, Any], str]] = []
        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8")
                data = yaml.safe_load(content)
                if data is None:
                    continue

                # See validate_file: the fallback is None only for an unloadable
                # profile; cast to str leaves runtime behavior unchanged.
                detected_type = self._detect_entity_type(data)
                entity_type = cast("str", detected_type or self._default_entity_type())

                result.files_checked.append(file_path)

                # Flag a declared-but-unknown _type rather than fail open (see
                # validate_file); skip collecting/validating this file further.
                if detected_type is not None and not self._is_known_entity(
                    detected_type
                ):
                    result.errors.append(
                        ValidationError(
                            field=f"{file_path}:_type",
                            message=f"Unknown entity type: '{data.get('_type')}'",
                            rule="unknown_entity_type",
                        )
                    )
                    continue

                self._collect_ids(data, entity_type)
                file_data.append((file_path, data, entity_type))
            except yaml.YAMLError as e:
                result.errors.append(
                    ValidationError(
                        field=str(file_path),
                        message=f"Invalid YAML: {e}",
                        rule="yaml_syntax",
                    )
                )
            except OSError as e:
                result.errors.append(
                    ValidationError(
                        field=str(file_path),
                        message=f"Cannot read file: {e}",
                        rule="file_access",
                    )
                )

        # Pass 2: Validate all files. Uniqueness is shared across files so that
        # global-scope rules catch cross-file duplicates.
        uniqueness_seen: set[tuple[str, str, str]] = set()
        for file_path, data, entity_type in file_data:
            # Validate entity structure
            errors = self._validate_entity(data, entity_type)
            for error in errors:
                result.errors.append(
                    ValidationError(
                        field=f"{file_path}:{error.field}",
                        message=error.message,
                        rule=error.rule,
                        # Carried, not re-derived: dropping it upgraded every
                        # per-file completeness report to a blocking error.
                        kind=error.kind,
                    )
                )

            # Validate references
            ref_errors = self._validate_references(data, entity_type)
            for error in ref_errors:
                result.errors.append(
                    ValidationError(
                        field=f"{file_path}:{error.field}",
                        message=error.message,
                        rule=error.rule,
                        kind=error.kind,
                    )
                )

            # Validate declared uniqueness rules across records
            uniq_errors = self._validate_uniqueness(
                data, entity_type, uniqueness_seen, scope_prefix=f"{file_path}:"
            )
            for error in uniq_errors:
                result.errors.append(
                    ValidationError(
                        field=f"{file_path}:{error.field}",
                        message=error.message,
                        rule=error.rule,
                        kind=error.kind,
                    )
                )

            # Count entities
            self._count_entities(data, entity_type, result.entity_counts)

        # After every file: a cycle can span files, so it is only judgeable
        # over the whole accumulated map.
        result.errors.extend(self._reference_cycles())

        # Once per field for the whole directory, not once per file: the counts
        # accumulated across every file above.
        result.warnings.extend(self._unchecked_references())
        result.warnings.extend(self._unchecked_terms)

        return result
