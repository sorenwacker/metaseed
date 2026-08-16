"""Spec loader for profile YAML specifications.

This module provides functionality to load and parse YAML specification files
that define entities and their fields for various profiles (MIAPPE, ISA, etc.).

Directory structure:
    specs/
        <profile-name>/
            <version>/
                profile.yaml

User-defined specs are stored in:
    - Linux/macOS: ~/.local/share/metaseed/specs/
    - Windows: %LOCALAPPDATA%/metaseed/specs/
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Self

import yaml
from pydantic import ValidationError

from metaseed.paths import get_builtin_specs_dir, get_user_specs_dir
from metaseed.specs.predicates import profile_predicate_issues
from metaseed.specs.schema import Constraints, EntitySpec, FieldType, ProfileSpec
from metaseed.specs.versioning import SUPPORTED_SPEC_VERSION

if TYPE_CHECKING:
    from metaseed.specs.schema import EntityDefSpec, FieldSpec, ValidationRuleSpec

# Field types a regex ``pattern`` or ``enum`` constraint can be applied to
# (Pydantic rejects e.g. a pattern on a ``datetime`` field). ``minimum``/``maximum``
# apply only to numeric fields.
_STRING_TYPES = frozenset({FieldType.STRING})
_NUMERIC_TYPES = frozenset({FieldType.INTEGER, FieldType.FLOAT})

logger = logging.getLogger(__name__)


class SpecLoadError(Exception):
    """Raised when a specification file cannot be loaded or parsed."""


def _rule_target_fields(
    profile: ProfileSpec, rule: ValidationRuleSpec
) -> list[FieldSpec]:
    """Return the FieldSpecs a rule applies to (by ``applies_to`` + ``field``)."""
    if not rule.field:
        return []
    applies = rule.applies_to
    if applies == "all":
        targets: list[EntityDefSpec] = list(profile.entities.values())
    else:
        names = applies if isinstance(applies, list) else [applies]
        by_norm = {
            key.lower().replace("_", ""): entity_def
            for key, entity_def in profile.entities.items()
        }
        targets = [
            entity_def
            for name in names
            if (entity_def := by_norm.get(str(name).lower().replace("_", "")))
        ]
    fields: list[FieldSpec] = []
    for entity_def in targets:
        fields.extend(f for f in entity_def.fields if f.name == rule.field)
    return fields


def _merge_rule_constraints_into_fields(profile: ProfileSpec) -> None:
    """Mirror rule-level pattern/enum/range constraints onto their fields.

    A constraint (``pattern``/``enum``/``minimum``/``maximum``) declared only on a
    ``validation_rule`` — the common case, since rule and field are separate YAML
    objects — is otherwise never enforced: ``engine._infer_rule_type`` delegates
    such constraints to Pydantic, but Pydantic (via ``models.factory``) only reads
    constraints from the field's own ``constraints`` block. Copying them onto the
    matching field here makes that delegation correct, so the generated model
    enforces them on every validation path. Field-level constraints win on
    conflict (a constraint the field already declares is left untouched).
    """
    for rule in profile.validation_rules:
        if (
            rule.pattern is None
            and rule.enum is None
            and rule.minimum is None
            and rule.maximum is None
        ):
            continue
        for field in _rule_target_fields(profile, rule):
            is_string = field.type in _STRING_TYPES
            is_numeric = field.type in _NUMERIC_TYPES
            if not (is_string or is_numeric):
                # A constraint on e.g. a datetime/uri field can't be applied as a
                # Pydantic pattern/range; the field type already validates it.
                continue
            invented = field.constraints is None
            if field.constraints is None:
                field.constraints = Constraints()
            constraints = field.constraints
            if is_string and rule.pattern is not None and constraints.pattern is None:
                constraints.pattern = rule.pattern
            if is_string and rule.enum is not None and constraints.enum is None:
                constraints.enum = rule.enum
            if is_numeric and rule.minimum is not None and constraints.minimum is None:
                constraints.minimum = rule.minimum
            if is_numeric and rule.maximum is not None and constraints.maximum is None:
                constraints.maximum = rule.maximum
            if invented and constraints == Constraints():
                # Every assignment above was skipped -- a numeric rule aimed at a
                # string field, say. Leaving the empty object behind would make
                # the loaded spec serialize `constraints: {}` where the source
                # had nothing, so identical content would hash two ways.
                field.constraints = None


class SpecLoader:
    """Loader for profile YAML specifications.

    Supports multiple profiles organized in directories:
        specs/<profile>/<version>/profile.yaml

    Searches in order:
        1. User specs directory (~/.local/share/metaseed/specs/)
        2. Built-in specs directory (package specs/)

    Example:
        specs/miappe/1.1/profile.yaml
        specs/darwin-core/1.0/profile.yaml
    """

    def __init__(self: Self, profile: str = "miappe") -> None:
        """Initialize the spec loader.

        Args:
            profile: Profile name (e.g., "miappe", "isa"). Defaults to "miappe".
        """
        self._builtin_specs_dir = get_builtin_specs_dir()
        self._user_specs_dir = get_user_specs_dir()
        self._profile_cache: dict[str, ProfileSpec] = {}
        self._default_profile = profile.lower()

    def find_profile_file(
        self: Self, version: str, profile: str | None = None
    ) -> Path | None:
        """Resolve the path to a profile's ``profile.yaml`` for a version.

        Public path-resolution API for callers that need the spec directory
        (e.g. to read sibling files such as ``notes.md``). Searches user specs
        first, then built-in specs.

        Args:
            version: Version string (e.g., "1.1").
            profile: Profile name (e.g., "miappe", "isa"). Uses default if None.

        Returns:
            Path to profile file or None if not found.
        """
        return self._find_profile_file(version, profile)

    def _find_profile_file(
        self: Self, version: str, profile: str | None = None
    ) -> Path | None:
        """Find profile file for a version.

        Searches user specs first, then built-in specs.

        Args:
            version: Version string (e.g., "1.1").
            profile: Profile name (e.g., "miappe", "isa"). Uses default if None.

        Returns:
            Path to profile file or None if not found.
        """
        profile = (profile or self._default_profile).lower()

        # Search user specs first, then built-in
        for specs_dir in [self._user_specs_dir, self._builtin_specs_dir]:
            profile_path = specs_dir / profile / version / "profile.yaml"
            if profile_path.exists():
                return profile_path

        return None

    def _cache_key(self: Self, version: str, profile: str | None = None) -> str:
        """Generate cache key for profile+version combination."""
        profile = (profile or self._default_profile).lower()
        return f"{profile}:{version}"

    def _load_profile(
        self: Self, version: str, profile: str | None = None
    ) -> ProfileSpec | None:
        """Load unified profile spec for a version.

        Args:
            version: Version string.
            profile: Profile name. Uses default if None.

        Returns:
            ProfileSpec or None if no profile file exists for this version.

        Raises:
            SpecLoadError: If the profile file exists but is malformed
                (invalid YAML or fails schema validation).
        """
        cache_key = self._cache_key(version, profile)
        if cache_key in self._profile_cache:
            return self._profile_cache[cache_key]

        profile_path = self._find_profile_file(version, profile)
        if profile_path is None:
            return None

        logger.debug("Loading profile from %s", profile_path)
        content = profile_path.read_text(encoding="utf-8")
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise SpecLoadError(f"Failed to parse profile {profile_path}: {e}") from e

        if data is None:
            logger.warning("Empty profile file: %s", profile_path)
            return None

        if not isinstance(data, dict):
            # A YAML file whose top level is a list or a scalar. Reported as a
            # spec problem, which every caller handles, rather than as the
            # TypeError the next line would raise from inside the loader.
            raise SpecLoadError(
                f"Profile file must contain a mapping, got "
                f"{type(data).__name__}: {profile_path}"
            )

        # Set default spec_version for backward compatibility with old specs
        if "spec_version" not in data:
            data["spec_version"] = "0.1"

        try:
            loaded_profile = ProfileSpec.model_validate(data)
        except ValidationError as e:
            errors = e.errors()
            if errors:
                first_error = errors[0]
                loc = ".".join(str(part) for part in first_error["loc"])
                msg = first_error["msg"]
                raise SpecLoadError(
                    f"Invalid profile {profile_path} at {loc}: {msg}"
                    f"{_version_hint(data, first_error)}"
                ) from e
            raise SpecLoadError(f"Invalid profile {profile_path}: {e}") from e

        _merge_rule_constraints_into_fields(loaded_profile)

        predicate_problems = profile_predicate_issues(loaded_profile)
        if predicate_problems:
            # Loudly, once, at load: a predicate naming a field that does not
            # exist is a rule that never fires, and finding that out from the
            # record it failed to catch is the defect class it guards against.
            raise SpecLoadError(
                f"Invalid profile {profile_path}: " + "; ".join(predicate_problems)
            )

        self._profile_cache[cache_key] = loaded_profile
        logger.debug(
            "Loaded profile %s with %d entities",
            cache_key,
            len(loaded_profile.entities),
        )
        return loaded_profile

    def load(self: Self, path: Path) -> EntitySpec:
        """Load an entity spec from a YAML file.

        Args:
            path: Path to the YAML specification file.

        Returns:
            Parsed EntitySpec object.

        Raises:
            SpecLoadError: If the file cannot be read or parsed.
        """
        if not path.exists():
            raise SpecLoadError(f"Specification file not found: {path}")

        try:
            content = path.read_text(encoding="utf-8")
            return self.load_from_string(content)
        except yaml.YAMLError as e:
            raise SpecLoadError(f"Failed to parse YAML: {e}") from e

    def load_from_string(self: Self, yaml_str: str) -> EntitySpec:
        """Load an entity spec from a YAML string.

        Args:
            yaml_str: YAML content as a string.

        Returns:
            Parsed EntitySpec object.

        Raises:
            SpecLoadError: If the YAML is invalid or doesn't match schema.
        """
        try:
            data = yaml.safe_load(yaml_str)
            if data is None:
                raise SpecLoadError("Empty YAML content")
            return EntitySpec.model_validate(data)
        except yaml.YAMLError as e:
            raise SpecLoadError(f"Failed to parse YAML: {e}") from e
        except ValidationError as e:
            errors = e.errors()
            if errors:
                first_error = errors[0]
                loc = ".".join(str(part) for part in first_error["loc"])
                msg = first_error["msg"]
                raise SpecLoadError(f"Invalid specification at {loc}: {msg}") from e
            raise SpecLoadError(f"Invalid specification: {e}") from e

    #: Profile names that have been renamed, mapped to what they are called now.
    #: A dataset records the profile it was built against, so dropping the old
    #: name would stop it opening -- it would resolve nothing and the dataset
    #: would refuse to load. Keeping the mapping costs a lookup and means a
    #: rename is a rename rather than a data migration everyone has to perform.
    RENAMED_PROFILES: ClassVar[dict[str, str]] = {"jerm": "seek"}

    def _resolve_renamed(self: Self, profile: str | None) -> str | None:
        """Return the current name of ``profile``, following a rename."""
        if profile is None:
            return None
        return self.RENAMED_PROFILES.get(profile.lower(), profile)

    def _load_profile_following_renames(
        self: Self, version: str, profile: str | None
    ) -> ProfileSpec | None:
        """Load, retrying under the profile's current name after a rename.

        The old name arrives on every path — an explicit argument OR the
        constructor default a dataset was recorded against — so the fallback
        must sit under all of them, not only inside ``load_profile``.
        """
        loaded = self._load_profile(version, profile)
        if loaded is None:
            effective = profile or self._default_profile
            renamed = self._resolve_renamed(effective)
            if renamed is not None and renamed != effective:
                loaded = self._load_profile(version, renamed)
        return loaded

    def load_profile(
        self: Self,
        version: str = "1.2",
        profile: str | None = None,
    ) -> ProfileSpec:
        """Load a unified profile spec.

        Args:
            version: Profile version (e.g., "1.1").
            profile: Profile name (e.g., "miappe", "isa"). Uses default if None.
        Returns:
            ProfileSpec object.

        Raises:
            SpecLoadError: If profile not found.
        """
        profile_name = profile or self._default_profile
        loaded = self._load_profile_following_renames(version, profile)
        if loaded is None:
            raise SpecLoadError(f"Profile not found: {profile_name} version {version}")
        return loaded

    def load_entity(
        self: Self,
        entity: str,
        version: str = "1.2",
        profile: str | None = None,
    ) -> EntitySpec:
        """Load an entity spec by name and version.

        Args:
            entity: Entity name (e.g., "investigation" or "Investigation").
            version: Version string (e.g., "1.1").
            profile: Profile name (e.g., "miappe", "isa"). Uses default if None.

        Returns:
            Parsed EntitySpec object.

        Raises:
            SpecLoadError: If the entity or version is not found.
        """
        profile_name = profile or self._default_profile

        loaded_profile = self._load_profile_following_renames(version, profile)
        if loaded_profile is not None:
            try:
                return loaded_profile.get_entity(entity)
            except KeyError:
                raise SpecLoadError(
                    f"Entity not found: {entity} ({profile_name} v{version})"
                ) from None

        raise SpecLoadError(f"Profile not found: {profile_name} v{version}")

    def list_entities(
        self: Self,
        version: str = "1.2",
        profile: str | None = None,
    ) -> list[str]:
        """List available entities for a version.

        Returns entities in the order defined in the profile YAML, which is
        typically hierarchical (Investigation -> Study -> nested entities).

        Args:
            version: Version string (e.g., "1.1").
            profile: Profile name (e.g., "miappe", "isa"). Uses default if None.

        Returns:
            List of entity names in definition order.

        Raises:
            SpecLoadError: If the version is not found.
        """
        profile_name = profile or self._default_profile

        loaded_profile = self._load_profile_following_renames(version, profile)
        if loaded_profile is not None:
            return loaded_profile.list_entities()

        raise SpecLoadError(f"Version not found: {profile_name} v{version}")

    def list_versions(self: Self, profile: str | None = None) -> list[str]:
        """List available versions for a profile.

        Searches both user and built-in specs directories.

        Args:
            profile: Profile name (e.g., "miappe", "isa"). Uses default if None.

        Returns:
            List of version strings (e.g., ["1.1"]).
        """
        profile_name = (profile or self._default_profile).lower()
        versions: set[str] = set()

        # The renamed directory answers for the old name here too: a dataset
        # recorded against the old name lists versions before loading.
        candidates = [profile_name]
        renamed = self._resolve_renamed(profile_name)
        if renamed and renamed.lower() != profile_name:
            candidates.append(renamed.lower())

        for candidate in candidates:
            if versions:
                break
            for specs_dir in [self._user_specs_dir, self._builtin_specs_dir]:
                profile_dir = specs_dir / candidate
                if profile_dir.exists() and profile_dir.is_dir():
                    for version_dir in profile_dir.iterdir():
                        if (
                            version_dir.is_dir()
                            and (version_dir / "profile.yaml").exists()
                        ):
                            versions.add(version_dir.name)

        # Numeric order, not text: "1.10" outranks "1.9". versions[-1] is what
        # every caller means by latest.
        from metaseed.specs.versioning import version_sort_key

        return sorted(versions, key=version_sort_key)

    def list_profiles(self: Self) -> list[str]:
        """List available profiles.

        Searches both user and built-in specs directories.

        Returns:
            List of profile names (e.g., ["miappe", "isa", "darwin-core"]).
        """
        profiles = set()

        # Search both user and built-in specs
        for specs_dir in [self._user_specs_dir, self._builtin_specs_dir]:
            if not specs_dir.exists():
                continue
            for item in specs_dir.iterdir():
                if item.is_dir() and not item.name.startswith("_"):
                    # Check if any subdirectory has a profile.yaml
                    for version_dir in item.iterdir():
                        if (
                            version_dir.is_dir()
                            and (version_dir / "profile.yaml").exists()
                        ):
                            # Lowercased, because that is the name every other
                            # method resolves by: a user directory "JERM" beside
                            # a built-in "jerm" is one profile whose versions are
                            # merged, not two profiles that happen to look alike.
                            profiles.add(item.name.lower())
                            break

        return sorted(profiles)

    def is_user_defined(self: Self, profile: str, version: str | None = None) -> bool:
        """Check if a profile (or specific version) is user-defined.

        Args:
            profile: Profile name.
            version: Optional version to check. If None, checks if any version is user-defined.

        Returns:
            True if the profile/version exists in user specs directory.
        """
        profile = profile.lower()
        profile_dir = self._user_specs_dir / profile

        if not profile_dir.exists():
            return False

        if version:
            return (profile_dir / version / "profile.yaml").exists()

        # Check if any version exists in user specs
        for version_dir in profile_dir.iterdir():
            if version_dir.is_dir() and (version_dir / "profile.yaml").exists():
                return True

        return False


def _version_hint(data: dict[str, Any], error: Mapping[str, Any]) -> str:
    """A second sentence naming a format-version mismatch, when that is the cause.

    "Extra inputs are not permitted" names the key it rejected but not why, and
    the why is usually that the profile was written for a newer metaseed. Only
    added for that error kind: on a genuine typo the version is not the reason.
    """
    if error.get("type") != "extra_forbidden":
        return ""
    declared = str(data.get("spec_version", "0.1"))
    if _as_version(declared) <= _as_version(SUPPORTED_SPEC_VERSION):
        return ""
    return (
        f" (the profile declares spec_version {declared}; "
        f"this metaseed supports up to {SUPPORTED_SPEC_VERSION})"
    )


def _as_version(value: str) -> tuple[int, ...]:
    """A dotted version as comparable integers, unparseable parts as zero."""
    parts = []
    for part in value.split("."):
        parts.append(int(part) if part.isdigit() else 0)
    return tuple(parts)
