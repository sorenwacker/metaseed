"""Schema specification module.

This module provides the spec loader, the schema models for parsing profile YAML
specifications, and the versioning tools built on them: the ``MAJOR.MINOR``
profile version rule, the canonical content hash, and the breaking-change
comparator that decides which version bump a set of edits requires.

See `docs/api/schema-specs.md`.
"""

from metaseed.specs.compare import (
    ChangeKind,
    Compatibility,
    SpecChange,
    SpecComparison,
    compare_specs,
    required_bump,
)
from metaseed.specs.loader import SpecLoader, SpecLoadError
from metaseed.specs.schema import (
    Constraints,
    EntitySpec,
    FieldSpec,
    FieldType,
    ProfileSpec,
)
from metaseed.specs.versioning import (
    PROFILE_VERSION_PATTERN,
    check_profile_version,
    content_hash,
    declared_bump,
    short_hash,
)

__all__ = [
    "PROFILE_VERSION_PATTERN",
    "ChangeKind",
    "Compatibility",
    "Constraints",
    "EntitySpec",
    "FieldSpec",
    "FieldType",
    "ProfileSpec",
    "SpecChange",
    "SpecComparison",
    "SpecLoadError",
    "SpecLoader",
    "check_profile_version",
    "compare_specs",
    "content_hash",
    "declared_bump",
    "required_bump",
    "short_hash",
]
