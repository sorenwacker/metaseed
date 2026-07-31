"""Classify what changed between two versions of a profile spec.

Answers the question a version number claims to answer but cannot enforce: is
this change breaking? A change is **breaking** when a dataset that validated
under the old spec may fail under the new one, and **compatible** otherwise.
:func:`required_bump` turns that into the ``MAJOR``/``MINOR`` decision described
in :mod:`metaseed.specs.versioning`.

Three rules resolve what inspection cannot decide, all erring toward breaking:

* A changed ``pattern`` counts as tightened -- whether one regex accepts a
  superset of another is not decidable here.
* An introduced bound or enum counts as tightened -- going from unconstrained to
  constrained can only reject values that previously passed.
* A field attribute outside the recognized cosmetic set counts as breaking, so
  an attribute added to the spec format in a future ``spec_version`` is flagged
  until it is classified deliberately, rather than passing silently.

This is not :mod:`metaseed.specs.merge.comparator`, which diffs *different*
profiles to find overlap for merging. This module diffs two versions of the
*same* profile to decide compatibility.

See `docs/api/schema-specs.md#profile-versioning`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from metaseed.specs.schema import FieldSpec

if TYPE_CHECKING:
    from collections.abc import Iterator

    from metaseed.specs.schema import (
        Constraints,
        EntityDefSpec,
        ProfileSpec,
        ValidationRuleSpec,
    )

BumpLevel = Literal["major", "minor", "none"]
"""The version bump a set of changes requires."""


class Compatibility(StrEnum):
    """Whether a change can invalidate data that was valid before."""

    BREAKING = "breaking"
    COMPATIBLE = "compatible"


class ChangeKind(StrEnum):
    """The classified kinds of difference between two specs."""

    ROOT_ENTITY_CHANGED = "root_entity_changed"
    PROFILE_METADATA_CHANGED = "profile_metadata_changed"

    ENTITY_REMOVED = "entity_removed"
    ENTITY_ADDED = "entity_added"
    ENTITY_METADATA_CHANGED = "entity_metadata_changed"

    FIELD_REMOVED = "field_removed"
    REQUIRED_FIELD_ADDED = "required_field_added"
    OPTIONAL_FIELD_ADDED = "optional_field_added"
    FIELDS_REORDERED = "fields_reordered"

    FIELD_BECAME_REQUIRED = "field_became_required"
    FIELD_BECAME_OPTIONAL = "field_became_optional"
    FIELD_TYPE_CHANGED = "field_type_changed"
    NESTING_RETARGETED = "nesting_retargeted"
    NESTING_REMOVED = "nesting_removed"
    FIELD_METADATA_CHANGED = "field_metadata_changed"
    FIELD_CHANGED = "field_changed"

    ENUM_NARROWED = "enum_narrowed"
    ENUM_WIDENED = "enum_widened"
    CONSTRAINT_TIGHTENED = "constraint_tightened"
    CONSTRAINT_LOOSENED = "constraint_loosened"
    PATTERN_TIGHTENED = "pattern_tightened"
    PATTERN_RELAXED = "pattern_relaxed"

    VALIDATION_RULE_ADDED = "validation_rule_added"
    VALIDATION_RULE_REMOVED = "validation_rule_removed"
    VALIDATION_RULE_CHANGED = "validation_rule_changed"


COMPATIBILITY_BY_KIND: dict[ChangeKind, Compatibility] = {
    ChangeKind.ROOT_ENTITY_CHANGED: Compatibility.BREAKING,
    ChangeKind.PROFILE_METADATA_CHANGED: Compatibility.COMPATIBLE,
    ChangeKind.ENTITY_REMOVED: Compatibility.BREAKING,
    ChangeKind.ENTITY_ADDED: Compatibility.COMPATIBLE,
    ChangeKind.ENTITY_METADATA_CHANGED: Compatibility.COMPATIBLE,
    ChangeKind.FIELD_REMOVED: Compatibility.BREAKING,
    ChangeKind.REQUIRED_FIELD_ADDED: Compatibility.BREAKING,
    ChangeKind.OPTIONAL_FIELD_ADDED: Compatibility.COMPATIBLE,
    ChangeKind.FIELDS_REORDERED: Compatibility.COMPATIBLE,
    ChangeKind.FIELD_BECAME_REQUIRED: Compatibility.BREAKING,
    ChangeKind.FIELD_BECAME_OPTIONAL: Compatibility.COMPATIBLE,
    ChangeKind.FIELD_TYPE_CHANGED: Compatibility.BREAKING,
    ChangeKind.NESTING_RETARGETED: Compatibility.BREAKING,
    ChangeKind.NESTING_REMOVED: Compatibility.BREAKING,
    ChangeKind.FIELD_METADATA_CHANGED: Compatibility.COMPATIBLE,
    ChangeKind.FIELD_CHANGED: Compatibility.BREAKING,
    ChangeKind.ENUM_NARROWED: Compatibility.BREAKING,
    ChangeKind.ENUM_WIDENED: Compatibility.COMPATIBLE,
    ChangeKind.CONSTRAINT_TIGHTENED: Compatibility.BREAKING,
    ChangeKind.CONSTRAINT_LOOSENED: Compatibility.COMPATIBLE,
    ChangeKind.PATTERN_TIGHTENED: Compatibility.BREAKING,
    ChangeKind.PATTERN_RELAXED: Compatibility.COMPATIBLE,
    ChangeKind.VALIDATION_RULE_ADDED: Compatibility.BREAKING,
    ChangeKind.VALIDATION_RULE_REMOVED: Compatibility.COMPATIBLE,
    ChangeKind.VALIDATION_RULE_CHANGED: Compatibility.BREAKING,
}
"""The classification table. Every :class:`ChangeKind` appears exactly once."""


_HANDLED_FIELD_ATTRIBUTES = frozenset(
    {"name", "type", "required", "items", "constraints"}
)
"""Field attributes compared by dedicated rules below."""

COSMETIC_FIELD_ATTRIBUTES = frozenset(
    {
        "codename",
        "description",
        "ontology_term",
        "ontologies",
        "dcat",
        "example",
        "is_label",
        "label",
        "tier",
        "unit",
    }
)
"""Field attributes that cannot invalidate a dataset: documentation and display."""

SEMANTIC_FIELD_ATTRIBUTES = (
    frozenset(FieldSpec.model_fields) - _HANDLED_FIELD_ATTRIBUTES
) - COSMETIC_FIELD_ATTRIBUTES
"""Field attributes with no dedicated rule, reported as breaking by default."""

_ENTITY_METADATA_ATTRIBUTES = ("description", "ontology_term", "example", "seek")
_PROFILE_METADATA_ATTRIBUTES = ("display_name", "description", "ontology", "ontologies")
_LOWER_BOUNDS = ("minimum", "min_length", "min_items")
_UPPER_BOUNDS = ("maximum", "max_length", "max_items")


def _jsonable(value: Any) -> Any:
    """Reduce a value to JSON-safe primitives for :meth:`SpecChange.to_dict`."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class SpecChange:
    """One classified difference between two specs.

    Attributes:
        kind: What kind of difference this is.
        compatibility: Whether it can invalidate previously valid data.
        target: What it applies to -- ``"Entity"``, ``"Entity.field"``, the rule
            name, or the profile name.
        message: A one-line rendering, e.g. ``"Credit.person became required"``.
        old: The previous value, where one exists.
        new: The new value, where one exists.
    """

    kind: ChangeKind
    compatibility: Compatibility
    target: str
    message: str
    old: Any = None
    new: Any = None

    def __str__(self) -> str:
        """Render the change as its human-readable line."""
        return self.message

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict of this change."""
        return {
            "kind": self.kind.value,
            "compatibility": self.compatibility.value,
            "target": self.target,
            "message": self.message,
            "old": _jsonable(self.old),
            "new": _jsonable(self.new),
        }


@dataclass(frozen=True)
class SpecComparison:
    """The full result of comparing two specs.

    Iterating the comparison yields its changes, so
    ``for change in compare_specs(old, new)`` reads naturally.

    Attributes:
        old_version: ``version`` declared by the older spec.
        new_version: ``version`` declared by the newer spec.
        changes: Every classified change, in a stable order.
    """

    old_version: str
    new_version: str
    changes: tuple[SpecChange, ...]

    def __iter__(self) -> Iterator[SpecChange]:
        """Iterate the changes."""
        return iter(self.changes)

    def __len__(self) -> int:
        """The number of changes."""
        return len(self.changes)

    @property
    def breaking(self) -> tuple[SpecChange, ...]:
        """The changes that can invalidate previously valid data."""
        return tuple(
            c for c in self.changes if c.compatibility is Compatibility.BREAKING
        )

    @property
    def compatible(self) -> tuple[SpecChange, ...]:
        """The changes that cannot invalidate previously valid data."""
        return tuple(
            c for c in self.changes if c.compatibility is Compatibility.COMPATIBLE
        )

    @property
    def required_bump(self) -> BumpLevel:
        """The smallest honest version bump for these changes."""
        if self.breaking:
            return "major"
        return "minor" if self.changes else "none"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict of the whole comparison."""
        return {
            "old_version": self.old_version,
            "new_version": self.new_version,
            "required_bump": self.required_bump,
            "changes": [c.to_dict() for c in self.changes],
            "breaking": [c.to_dict() for c in self.breaking],
            "compatible": [c.to_dict() for c in self.compatible],
        }


def _change(
    kind: ChangeKind,
    target: str,
    message: str,
    old: Any = None,
    new: Any = None,
) -> SpecChange:
    """Build a change, taking its classification from :data:`COMPATIBILITY_BY_KIND`."""
    return SpecChange(
        kind=kind,
        compatibility=COMPATIBILITY_BY_KIND[kind],
        target=target,
        message=message,
        old=old,
        new=new,
    )


# ----------------------------------------------------------------------
# Constraints
# ----------------------------------------------------------------------
def _enum_change(
    target: str, old: list[str] | None, new: list[str] | None
) -> SpecChange | None:
    """Classify a change to a field's allowed-value set."""
    if (old or None) == (new or None) or set(old or ()) == set(new or ()):
        return None
    if not new:
        return _change(
            ChangeKind.ENUM_WIDENED,
            target,
            f"{target} enum constraint removed",
            old,
            new,
        )
    if not old:
        listed = ", ".join(sorted(new))
        return _change(
            ChangeKind.ENUM_NARROWED,
            target,
            f"{target} restricted to an enum of {len(new)} value(s): {listed}",
            old,
            new,
        )
    removed = sorted(set(old) - set(new))
    if removed:
        return _change(
            ChangeKind.ENUM_NARROWED,
            target,
            f"{target} enum no longer accepts: {', '.join(removed)}",
            old,
            new,
        )
    added = ", ".join(sorted(set(new) - set(old)))
    return _change(
        ChangeKind.ENUM_WIDENED,
        target,
        f"{target} enum now also accepts: {added}",
        old,
        new,
    )


def _pattern_change(target: str, old: str | None, new: str | None) -> SpecChange | None:
    """Classify a change to a field's regex pattern.

    Any pattern that changes but stays set is reported as tightened: regex
    containment is not decidable here, so the conservative reading applies.
    """
    if old == new:
        return None
    if new is None:
        return _change(
            ChangeKind.PATTERN_RELAXED, target, f"{target} pattern removed", old, new
        )
    detail = f"added: {new}" if old is None else f"changed from {old} to {new}"
    return _change(
        ChangeKind.PATTERN_TIGHTENED, target, f"{target} pattern {detail}", old, new
    )


def _bound_change(target: str, name: str, old: Any, new: Any) -> SpecChange | None:
    """Classify a change to one numeric/length/cardinality bound."""
    if old == new:
        return None
    if new is None:
        tightened = False
    elif old is None:
        tightened = True
    elif name in _LOWER_BOUNDS:
        tightened = new > old
    else:
        tightened = new < old

    kind = (
        ChangeKind.CONSTRAINT_TIGHTENED if tightened else ChangeKind.CONSTRAINT_LOOSENED
    )
    verb = "tightened" if tightened else "loosened"
    shown_old = "unset" if old is None else old
    shown_new = "unset" if new is None else new
    return _change(
        kind,
        target,
        f"{target} {name} {verb} from {shown_old} to {shown_new}",
        old,
        new,
    )


def _constraint_changes(
    target: str, old: Constraints | None, new: Constraints | None
) -> list[SpecChange]:
    """Classify every difference between two constraint blocks."""
    found: list[SpecChange] = []
    enum = _enum_change(target, old.enum if old else None, new.enum if new else None)
    if enum is not None:
        found.append(enum)
    pattern = _pattern_change(
        target, old.pattern if old else None, new.pattern if new else None
    )
    if pattern is not None:
        found.append(pattern)
    for name in (*_LOWER_BOUNDS, *_UPPER_BOUNDS):
        bound = _bound_change(
            target,
            name,
            getattr(old, name) if old else None,
            getattr(new, name) if new else None,
        )
        if bound is not None:
            found.append(bound)
    return found


# ----------------------------------------------------------------------
# Fields
# ----------------------------------------------------------------------
def _requirement_change(
    target: str, old: FieldSpec, new: FieldSpec
) -> SpecChange | None:
    """Classify a change to whether the field must be present."""
    if old.required == new.required:
        return None
    kind = (
        ChangeKind.FIELD_BECAME_REQUIRED
        if new.required
        else ChangeKind.FIELD_BECAME_OPTIONAL
    )
    state = "required" if new.required else "optional"
    return _change(kind, target, f"{target} became {state}", old.required, new.required)


def _type_change(target: str, old: FieldSpec, new: FieldSpec) -> SpecChange | None:
    """Classify a change to the field's data type."""
    if old.type == new.type:
        return None
    return _change(
        ChangeKind.FIELD_TYPE_CHANGED,
        target,
        f"{target} type changed from {old.type.value} to {new.type.value}",
        old.type,
        new.type,
    )


def _items_change(target: str, old: FieldSpec, new: FieldSpec) -> SpecChange | None:
    """Classify a change to the nesting link a list/entity field declares."""
    if old.items == new.items:
        return None
    if new.items is None:
        return _change(
            ChangeKind.NESTING_REMOVED,
            target,
            f"{target} no longer nests {old.items}",
            old.items,
            new.items,
        )
    source = old.items if old.items is not None else "nothing"
    return _change(
        ChangeKind.NESTING_RETARGETED,
        target,
        f"{target} items retargeted from {source} to {new.items}",
        old.items,
        new.items,
    )


def _attribute_changes(target: str, old: FieldSpec, new: FieldSpec) -> list[SpecChange]:
    """Classify differences in attributes without a dedicated rule."""
    found: list[SpecChange] = []
    for name in sorted(COSMETIC_FIELD_ATTRIBUTES):
        before, after = getattr(old, name), getattr(new, name)
        if before != after:
            found.append(
                _change(
                    ChangeKind.FIELD_METADATA_CHANGED,
                    target,
                    f"{target} {name} changed",
                    before,
                    after,
                )
            )
    for name in sorted(SEMANTIC_FIELD_ATTRIBUTES):
        before, after = getattr(old, name), getattr(new, name)
        if before != after:
            found.append(
                _change(
                    ChangeKind.FIELD_CHANGED,
                    target,
                    f"{target} {name} changed from {before!r} to {after!r}",
                    before,
                    after,
                )
            )
    return found


def _field_changes(target: str, old: FieldSpec, new: FieldSpec) -> list[SpecChange]:
    """Classify every difference between two versions of one field."""
    found = [
        change
        for change in (
            _requirement_change(target, old, new),
            _type_change(target, old, new),
            _items_change(target, old, new),
        )
        if change is not None
    ]
    found.extend(_constraint_changes(target, old.constraints, new.constraints))
    found.extend(_attribute_changes(target, old, new))
    return found


def _field_set_changes(
    entity: str, old: EntityDefSpec, new: EntityDefSpec
) -> list[SpecChange]:
    """Classify fields removed, added, reordered, and edited within one entity."""
    old_fields = {f.name: f for f in old.fields}
    new_fields = {f.name: f for f in new.fields}
    found: list[SpecChange] = []

    for name in (n for n in old_fields if n not in new_fields):
        found.append(
            _change(
                ChangeKind.FIELD_REMOVED,
                f"{entity}.{name}",
                f"{entity}.{name} was removed",
                old_fields[name],
            )
        )
    for name in (n for n in new_fields if n not in old_fields):
        field = new_fields[name]
        kind = (
            ChangeKind.REQUIRED_FIELD_ADDED
            if field.required
            else ChangeKind.OPTIONAL_FIELD_ADDED
        )
        state = "required" if field.required else "optional"
        found.append(
            _change(
                kind,
                f"{entity}.{name}",
                f"{entity}.{name} was added as a{'' if field.required else 'n'} "
                f"{state} field",
                None,
                field,
            )
        )

    kept_old = [n for n in old_fields if n in new_fields]
    kept_new = [n for n in new_fields if n in old_fields]
    if kept_old != kept_new:
        found.append(
            _change(
                ChangeKind.FIELDS_REORDERED,
                entity,
                f"{entity} fields were reordered",
                kept_old,
                kept_new,
            )
        )

    for name in kept_new:
        found.extend(
            _field_changes(f"{entity}.{name}", old_fields[name], new_fields[name])
        )
    return found


# ----------------------------------------------------------------------
# Entities, rules, profile
# ----------------------------------------------------------------------
def _entity_metadata_changes(
    entity: str, old: EntityDefSpec, new: EntityDefSpec
) -> list[SpecChange]:
    """Classify differences in an entity's own (non-field) attributes."""
    return [
        _change(
            ChangeKind.ENTITY_METADATA_CHANGED,
            entity,
            f"{entity} {name} changed",
            getattr(old, name),
            getattr(new, name),
        )
        for name in _ENTITY_METADATA_ATTRIBUTES
        if getattr(old, name) != getattr(new, name)
    ]


def _entity_changes(old: ProfileSpec, new: ProfileSpec) -> list[SpecChange]:
    """Classify entities removed, added, and edited."""
    found: list[SpecChange] = []
    for name in (n for n in old.entities if n not in new.entities):
        found.append(
            _change(
                ChangeKind.ENTITY_REMOVED,
                name,
                f"entity {name} was removed",
                old.entities[name],
            )
        )
    for name in (n for n in new.entities if n not in old.entities):
        found.append(
            _change(
                ChangeKind.ENTITY_ADDED,
                name,
                f"entity {name} was added",
                None,
                new.entities[name],
            )
        )
    for name in (n for n in new.entities if n in old.entities):
        before, after = old.entities[name], new.entities[name]
        found.extend(_entity_metadata_changes(name, before, after))
        found.extend(_field_set_changes(name, before, after))
    return found


def _rule_changes(old: ProfileSpec, new: ProfileSpec) -> list[SpecChange]:
    """Classify validation rules removed, added, and edited.

    An added or edited rule is breaking: a rule exists to reject data, so a new
    one can reject data the previous version accepted.
    """
    old_rules: dict[str, ValidationRuleSpec] = {r.name: r for r in old.validation_rules}
    new_rules: dict[str, ValidationRuleSpec] = {r.name: r for r in new.validation_rules}
    found: list[SpecChange] = []

    for name in (n for n in old_rules if n not in new_rules):
        found.append(
            _change(
                ChangeKind.VALIDATION_RULE_REMOVED,
                name,
                f"validation rule {name!r} was removed",
                old_rules[name],
            )
        )
    for name in (n for n in new_rules if n not in old_rules):
        found.append(
            _change(
                ChangeKind.VALIDATION_RULE_ADDED,
                name,
                f"validation rule {name!r} was added",
                None,
                new_rules[name],
            )
        )
    for name in (n for n in new_rules if n in old_rules):
        if old_rules[name] != new_rules[name]:
            found.append(
                _change(
                    ChangeKind.VALIDATION_RULE_CHANGED,
                    name,
                    f"validation rule {name!r} changed",
                    old_rules[name],
                    new_rules[name],
                )
            )
    return found


def _profile_changes(old: ProfileSpec, new: ProfileSpec) -> list[SpecChange]:
    """Classify profile-level differences.

    ``version`` and ``spec_version`` are excluded on purpose: the comparator
    describes the content, and the version is the claim being checked against it.
    """
    target = new.name or old.name or "profile"
    found: list[SpecChange] = []
    if old.root_entity != new.root_entity:
        found.append(
            _change(
                ChangeKind.ROOT_ENTITY_CHANGED,
                target,
                f"root entity changed from {old.root_entity} to {new.root_entity}",
                old.root_entity,
                new.root_entity,
            )
        )
    found.extend(
        _change(
            ChangeKind.PROFILE_METADATA_CHANGED,
            target,
            f"profile {name} changed",
            getattr(old, name),
            getattr(new, name),
        )
        for name in _PROFILE_METADATA_ATTRIBUTES
        if getattr(old, name) != getattr(new, name)
    )
    return found


def compare_specs(old: ProfileSpec, new: ProfileSpec) -> SpecComparison:
    """Classify every difference between two versions of a profile spec.

    Args:
        old: The spec being superseded.
        new: The spec superseding it.

    Returns:
        A :class:`SpecComparison` holding the classified changes, the two
        partitions, and the version bump they require.
    """
    changes = [
        *_profile_changes(old, new),
        *_entity_changes(old, new),
        *_rule_changes(old, new),
    ]
    return SpecComparison(
        old_version=old.version, new_version=new.version, changes=tuple(changes)
    )


def required_bump(old: ProfileSpec, new: ProfileSpec) -> BumpLevel:
    """Return the smallest honest version bump from ``old`` to ``new``.

    Args:
        old: The spec being superseded.
        new: The spec superseding it.

    Returns:
        ``"major"`` if any change is breaking, ``"minor"`` if there are only
        compatible changes, and ``"none"`` if the content is identical.
    """
    return compare_specs(old, new).required_bump
