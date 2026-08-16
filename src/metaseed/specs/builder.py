"""Spec builder engine.

`SpecBuilder` is the shared domain layer for authoring profile specifications.
Both the web UI (`metaseed.ui.spec_builder`) and the MCP tools
(`metaseed.agent.mcp.tools.spec_builder`) are thin adapters over this class, so
the two interfaces cannot drift apart. The engine has no UI or MCP dependencies.

See `docs/architecture/spec-builder.md` for the design.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Self

import yaml
from pydantic import ValidationError

from metaseed.specs.predicates import profile_predicate_issues
from metaseed.specs.schema import (
    Constraints,
    EntityDefSpec,
    FieldSpec,
    FieldType,
    ProfileSpec,
    ValidationRuleSpec,
    identifying_field,
)
from metaseed.specs.versioning import check_profile_version
from metaseed.utils.text import to_snake_case

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


_PROFILE_METADATA_FIELDS = frozenset(
    {"name", "version", "display_name", "description", "ontology", "spec_version"}
)

CONSTRAINT_NAMES: tuple[str, ...] = tuple(Constraints.model_fields)
"""The names :meth:`SpecBuilder.update_field_constraints` accepts and can clear.

Derived from :class:`~metaseed.specs.schema.Constraints` so adding a constraint
to the schema makes it editable and clearable without a second edit here.
"""

_CORE_FIELD_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "name",
        "type",
        "required",
        "description",
        "items",
        "ontology_term",
        "reference",
        "parent_ref",
        "constraints",
    }
)
"""The :class:`FieldSpec` attributes a field editor already takes as its own argument.

``constraints`` is here because it is exposed flattened, as the eight
:data:`CONSTRAINT_NAMES` arguments, rather than as one object.
"""

RULE_ATTRIBUTE_NAMES: tuple[str, ...] = tuple(
    name for name in ValidationRuleSpec.model_fields if name != "name"
)
"""Every :class:`ValidationRuleSpec` attribute a rule editor can set.

Derived from the model for the same reason as :data:`FIELD_MARKER_NAMES`: an
adapter reads the set instead of hardcoding it, so a key added to the format
reaches the editors rather than being quietly unauthorable. Half of these were
unauthorable over MCP until #211 -- an agent could declare a cardinality rule's
type but not its bounds.
"""

FIELD_MARKER_NAMES: tuple[str, ...] = tuple(
    name for name in FieldSpec.model_fields if name not in _CORE_FIELD_ATTRIBUTES
)
"""Every other declarative :class:`FieldSpec` attribute a field editor can set.

Derived by subtracting :data:`_CORE_FIELD_ATTRIBUTES` from the model, so a marker
added to the schema becomes settable without a second edit here -- the same
contract as :data:`CONSTRAINT_NAMES`, and exported for the same reason: an
adapter (the MCP field tools, and the metaseed-hub tools that mirror them) reads
the set instead of hardcoding the names.
"""


def normalize_markers(values: Mapping[str, Any]) -> dict[str, Any]:
    """Split "not supplied" from "unset this" in raw marker input.

    A marker, unlike a numeric constraint, has a representable empty value, so it
    needs no ``clear`` list: ``False``, ``""`` and ``[]`` *are* the removal
    request. They are mapped onto ``None`` -- matching
    :meth:`~metaseed.specs.field_form.FieldForm.apply_to` -- so an unset marker is
    absent from the serialized spec rather than written as ``owns: false``, and a
    spec's ``content_hash`` does not record whether a marker was ever toggled.

    Args:
        values: Raw marker input, where ``None`` means the caller did not supply
            the marker at all.

    Returns:
        The markers to assign, with omitted ones dropped and explicitly emptied
        ones mapped to ``None``. Suitable to splat into
        :meth:`SpecBuilder.update_field`.
    """
    normalized: dict[str, Any] = {}
    for name, value in values.items():
        if value is None:
            continue
        # `is False` rather than `not value`: 0 is a legitimate `example`.
        normalized[name] = None if (value is False or value in ("", [])) else value
    return normalized


def validate_marker_values(values: Mapping[str, Any]) -> str | None:
    """Validate marker names and values against :class:`FieldSpec`.

    Exposed alongside :data:`FIELD_MARKER_NAMES` so an adapter can reject bad
    input before it starts mutating a draft, rather than leaving a half-applied
    edit behind. Checking by constructing a throwaway ``FieldSpec`` keeps the
    schema the only place a marker's allowed values are written down: ``tier``'s
    three levels are not restated here.

    Args:
        values: Marker names mapped to their proposed values.

    Returns:
        Error message naming the offenders, or None if every name and value is
        acceptable.
    """
    unknown = sorted(set(values) - set(FIELD_MARKER_NAMES))
    if unknown:
        return (
            f"Unknown field marker(s): {', '.join(unknown)}. "
            f"Valid field markers: {', '.join(FIELD_MARKER_NAMES)}"
        )
    try:
        FieldSpec(name="_probe", type=FieldType.STRING, **dict(values))
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        return f"Invalid field marker value(s): {problems}"
    return None


def validate_entity_name(name: str) -> str | None:
    """Validate an entity name (PascalCase).

    Args:
        name: The entity name to validate.

    Returns:
        Error message if invalid, None if valid.
    """
    if not name:
        return "Entity name is required"
    if not name[0].isupper():
        return "Entity name must start with uppercase letter (PascalCase)"
    if not name.replace("_", "").isalnum():
        return "Entity name can only contain letters, numbers, and underscores"
    return None


def validate_constraint_names(names: Iterable[str]) -> str | None:
    """Validate names used as constraints (to set or to clear).

    Exposed alongside :meth:`SpecBuilder.update_field_constraints` so an adapter
    can reject a bad name before it starts mutating a draft, rather than leaving
    a half-applied edit behind when the merge raises.

    Args:
        names: Candidate constraint names.

    Returns:
        Error message naming the offenders and the valid options, or None if
        every name is a constraint.
    """
    unknown = sorted(set(names) - set(CONSTRAINT_NAMES))
    if not unknown:
        return None
    return (
        f"Unknown constraint name(s): {', '.join(unknown)}. "
        f"Valid constraint names: {', '.join(CONSTRAINT_NAMES)}"
    )


_IDENTIFIER_NAME_HINTS: tuple[str, ...] = (
    "id",
    "identifier",
    "uuid",
    "accession",
    "doi",
    "code",
)
"""Field-name words that state the field is an identifier.

Used only to keep the weak-identifier advisory quiet, never to resolve identity:
resolution reads ``is_identifier``. A field the author named ``sample_id`` is
taken at its word even though it is optional; a field named ``name`` or ``title``
is not, because those state a display *label*, which is precisely what the
markers exist to keep separate from identity.
"""


def _name_states_an_identifier(name: str) -> bool:
    """Whether a field's own name claims it identifies the entity."""
    lowered = name.lower()
    if lowered in _IDENTIFIER_NAME_HINTS:
        return True
    if any(lowered.endswith(f"_{hint}") for hint in _IDENTIFIER_NAME_HINTS):
        return True
    # camelCase identifiers such as Darwin Core's `locationID`.
    return len(name) > 2 and name.endswith("ID")


def validate_field_name(name: str) -> str | None:
    """Validate a field name (snake_case).

    Args:
        name: The field name to validate.

    Returns:
        Error message if invalid, None if valid.
    """
    if not name:
        return "Field name is required"
    if not name[0].islower() and name[0] != "_":
        return "Field name must start with lowercase letter or underscore"
    if not name.replace("_", "").replace("-", "").isalnum():
        return "Field name can only contain letters, numbers, underscores, and hyphens"
    return None


class SpecBuilder:
    """Build and edit a single :class:`ProfileSpec`.

    All spec mutations are defined here so the UI and MCP interfaces share one
    implementation. Entities, fields, and rules are addressed by name.
    """

    def __init__(self: Self, spec: ProfileSpec) -> None:
        """Wrap an existing spec. Prefer the classmethod constructors."""
        self._spec = spec

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    @property
    def spec(self: Self) -> ProfileSpec:
        """The underlying profile spec being edited."""
        return self._spec

    @classmethod
    def empty(
        cls,
        name: str,
        version: str,
        *,
        display_name: str | None = None,
        description: str = "",
        ontology: str | None = None,
    ) -> SpecBuilder:
        """Create a builder around a new, entity-less spec."""
        return cls(
            ProfileSpec(
                version=version,
                name=name,
                display_name=display_name if display_name is not None else "",
                description=description,
                ontology=ontology,
                root_entity="",
                validation_rules=[],
                entities={},
            )
        )

    @classmethod
    def from_template(cls, profile: str, version: str) -> SpecBuilder:
        """Create a builder from a deep copy of an existing profile.

        The clone keeps the source ``version``: it is a derivative *of that
        version*, and the author sets the new name and version with
        :meth:`set_metadata` before saving. A marker suffix is not an option --
        a profile version is ``MAJOR.MINOR`` (see
        :mod:`metaseed.specs.versioning`), so a suffixed draft would serialize
        to YAML that could not be loaded back.

        Raises:
            ValueError: If the profile/version cannot be loaded.
        """
        from metaseed.specs.loader import SpecLoader, SpecLoadError

        loader = SpecLoader(profile=profile)
        try:
            source = loader.load_profile(version=version, profile=profile)
        except SpecLoadError as exc:
            raise ValueError(
                f"Cannot load profile {profile} v{version}: {exc}"
            ) from exc

        return cls(copy.deepcopy(source))

    @classmethod
    def from_yaml(cls, text: str) -> SpecBuilder:
        """Create a builder from a YAML spec document.

        Raises:
            ValueError: If the YAML is malformed or fails schema validation.
        """
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML: {exc}") from exc
        try:
            return cls(ProfileSpec.model_validate(data))
        except Exception as exc:  # pydantic ValidationError and friends
            raise ValueError(f"Invalid spec: {exc}") from exc

    @classmethod
    def from_spec(cls, spec: ProfileSpec) -> SpecBuilder:
        """Wrap an existing spec object (mutated in place)."""
        return cls(spec)

    # ------------------------------------------------------------------
    # Profile metadata
    # ------------------------------------------------------------------
    def set_metadata(self: Self, **fields: Any) -> None:
        """Update profile-level fields.

        Accepts: name, version, display_name, description, ontology, spec_version.

        Raises:
            ValueError: If an unknown field is supplied.
        """
        unknown = set(fields) - _PROFILE_METADATA_FIELDS
        if unknown:
            raise ValueError(f"Unknown profile field(s): {', '.join(sorted(unknown))}")
        for key, value in fields.items():
            setattr(self._spec, key, value)

    def set_root_entity(self: Self, entity: str) -> None:
        """Set the root entity. The entity must already exist.

        Raises:
            ValueError: If the entity is not defined.
        """
        self._require_entity(entity)
        self._spec.root_entity = entity

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------
    def add_entity(
        self: Self,
        name: str,
        *,
        description: str = "",
        ontology_term: str | None = None,
    ) -> None:
        """Add a new entity.

        Raises:
            ValueError: If the name is invalid or already exists.
        """
        error = validate_entity_name(name)
        if error:
            raise ValueError(error)
        if name in self._spec.entities:
            raise ValueError(f"Entity '{name}' already exists")
        self._spec.entities[name] = EntityDefSpec(
            ontology_term=ontology_term,
            description=description,
            fields=[],
        )

    def update_entity(
        self: Self,
        name: str,
        *,
        description: str | None = None,
        ontology_term: str | None = None,
    ) -> None:
        """Update an entity's metadata. Unset arguments are left unchanged.

        Raises:
            ValueError: If the entity is not defined.
        """
        entity = self._require_entity(name)
        if description is not None:
            entity.description = description
        if ontology_term is not None:
            entity.ontology_term = ontology_term

    def rename_entity(self: Self, old_name: str, new_name: str) -> None:
        """Rename an entity and rewrite every reference to it.

        Updates ``field.items``, ``field.reference``, ``field.parent_ref``, and
        validation-rule ``applies_to`` / ``reference`` across the whole spec.

        Raises:
            ValueError: If the old entity is missing, the new name is invalid,
                or the new name already exists.
        """
        self._require_entity(old_name)
        if old_name == new_name:
            return
        error = validate_entity_name(new_name)
        if error:
            raise ValueError(error)
        if new_name in self._spec.entities:
            raise ValueError(f"Entity '{new_name}' already exists")

        # Preserve insertion order while replacing the key.
        self._spec.entities = {
            (new_name if key == old_name else key): value
            for key, value in self._spec.entities.items()
        }
        if self._spec.root_entity == old_name:
            self._spec.root_entity = new_name
        self._update_references(old_name, new_name)

    def delete_entity(self: Self, name: str) -> None:
        """Delete an entity. Clears ``root_entity`` if it pointed here.

        Raises:
            ValueError: If the entity is not defined.
        """
        self._require_entity(name)
        del self._spec.entities[name]
        if self._spec.root_entity == name:
            self._spec.root_entity = ""

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------
    def add_field(
        self: Self,
        entity: str,
        name: str,
        field_type: FieldType | str,
        **attrs: Any,
    ) -> None:
        """Add a field to an entity.

        A nested field (``list`` of entities or a single ``entity``) auto-creates
        the parent ``identifier`` field and a back-reference on the target.

        Raises:
            ValueError: If the field name is invalid, the entity is missing, the
                field already exists, or an attribute is not a valid field
                property.
        """
        error = validate_field_name(name)
        if error:
            raise ValueError(error)
        entity_def = self._require_entity(entity)
        if any(f.name == name for f in entity_def.fields):
            raise ValueError(f"Field '{name}' already exists on '{entity}'")

        unknown = set(attrs) - set(FieldSpec.model_fields)
        if unknown:
            raise ValueError(
                f"Unknown field attribute(s): {', '.join(sorted(unknown))}"
            )

        field = FieldSpec(name=name, type=FieldType(field_type), **attrs)
        # Deliberately NOT re-validating the entity here, unlike update_field.
        # The spec-builder flow is add-then-validate: an agent adds fields and
        # `spec_validate` reports what is wrong, including a second
        # `is_identifier` (tests/test_agent/test_mcp_spec_builder.py pins that
        # as an issue rather than a warning). Refusing at add time makes that
        # report unreachable for a spec built through the tools and turns a
        # correctable draft into a hard error mid-build.
        entity_def.fields.append(field)
        self._auto_create_back_reference(entity, entity_def, field)

    def update_field(self: Self, entity: str, field_name: str, **attrs: Any) -> None:
        """Update a field in place. Only supplied attributes change.

        Each supplied attribute is assigned whole. For ``constraints`` that means
        **replacement, not merge**: passing ``constraints=Constraints(minimum=1)``
        substitutes the entire object, so any ``enum``, ``pattern`` or other
        constraint the field already carried is discarded. Use
        :meth:`update_field_constraints` to change individual constraints while
        keeping the rest.

        Raises:
            ValueError: If the entity or field is missing, or an attribute is
                not a valid field property.
        """
        field = self._require_field(entity, field_name)
        valid = set(FieldSpec.model_fields)
        unknown = set(attrs) - valid
        if unknown:
            raise ValueError(
                f"Unknown field attribute(s): {', '.join(sorted(unknown))}"
            )
        # Rebuilt rather than assigned onto, like update_rule: pydantic does
        # not validate an assignment, so a bad isa_tag or a second
        # is_identifier sat in the spec and surfaced only on load-back.
        merged = {**field.model_dump(exclude_none=True), **attrs}
        try:
            rebuilt = FieldSpec.model_validate(merged)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        entity_def = self._spec.entities[entity]
        index = entity_def.fields.index(field)
        replaced = list(entity_def.fields)
        replaced[index] = rebuilt
        # The single-identifier invariant lives on the entity model; swapping
        # the list through model_validate is what makes it re-run.
        try:
            entity_def.__class__.model_validate(
                {**entity_def.model_dump(exclude_none=True), "fields": replaced}
            )
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        entity_def.fields[index] = rebuilt

    def update_field_constraints(
        self: Self,
        entity: str,
        field_name: str,
        *,
        clear: Iterable[str] = (),
        **values: Any,
    ) -> None:
        """Merge constraint values into a field's existing constraints.

        The partial-update counterpart to ``update_field(constraints=...)``:
        supplied values overwrite those constraints only, every other constraint
        on the field is preserved, and the ``Constraints`` object is created if
        the field had none.

        An omitted keyword means "unchanged", so it cannot express removal;
        ``clear`` names the constraints to unset. When the merge leaves every
        constraint unset, ``constraints`` becomes ``None`` rather than an
        all-``None`` object: both dump to nothing under ``exclude_none``, but an
        empty object still serializes as an empty mapping and would give the same
        spec a second :attr:`~metaseed.specs.schema.ProfileSpec.content_hash`.

        Args:
            entity: Name of the entity owning the field.
            field_name: Name of the field to edit.
            clear: Constraint names to unset. Must be disjoint from ``values``.
            **values: Constraint names from :data:`CONSTRAINT_NAMES` mapped to
                their new values.

        Raises:
            ValueError: If the entity or field is missing, a name in ``values``
                or ``clear`` is not a constraint, a name appears in both (the two
                requests contradict each other), or a value fails the
                ``Constraints`` schema. The field is left untouched.
        """
        field = self._require_field(entity, field_name)
        cleared = set(clear)
        name_error = validate_constraint_names(set(values) | cleared)
        if name_error:
            raise ValueError(name_error)
        conflicting = sorted(set(values) & cleared)
        if conflicting:
            raise ValueError(
                "Cannot set and clear the same constraint(s) in one call: "
                f"{', '.join(conflicting)}"
            )

        merged: dict[str, Any] = (
            field.constraints.model_dump() if field.constraints else {}
        )
        merged.update(values)
        merged.update(dict.fromkeys(cleared))
        constraints = Constraints(**merged)
        field.constraints = None if constraints == Constraints() else constraints

    def delete_field(self: Self, entity: str, field_name: str) -> None:
        """Delete a field by name.

        Raises:
            ValueError: If the entity or field is missing.
        """
        entity_def = self._require_entity(entity)
        index = self._field_index(entity_def, field_name)
        if index is None:
            raise ValueError(f"Field '{field_name}' not found on '{entity}'")
        del entity_def.fields[index]

    def move_field(self: Self, entity: str, field_name: str, direction: str) -> None:
        """Reorder a field one position ``up`` or ``down``.

        Movement past either boundary is a no-op.

        Raises:
            ValueError: If the entity or field is missing, or the direction is
                not 'up' or 'down'.
        """
        if direction not in ("up", "down"):
            raise ValueError("direction must be 'up' or 'down'")
        entity_def = self._require_entity(entity)
        index = self._field_index(entity_def, field_name)
        if index is None:
            raise ValueError(f"Field '{field_name}' not found on '{entity}'")
        target = index - 1 if direction == "up" else index + 1
        if 0 <= target < len(entity_def.fields):
            fields = entity_def.fields
            fields[index], fields[target] = fields[target], fields[index]

    # ------------------------------------------------------------------
    # Validation rules
    # ------------------------------------------------------------------
    def add_rule(self: Self, name: str, **attrs: Any) -> None:
        """Add a validation rule.

        Raises:
            ValueError: If a rule with the same name exists.
        """
        if any(r.name == name for r in self._spec.validation_rules):
            raise ValueError(f"Validation rule '{name}' already exists")
        self._spec.validation_rules.append(ValidationRuleSpec(name=name, **attrs))

    def update_rule(self: Self, rule_name: str, **attrs: Any) -> None:
        """Update a validation rule in place.

        Raises:
            ValueError: If the rule is missing or an attribute is invalid.
        """
        rule = self._require_rule(rule_name)
        valid = set(ValidationRuleSpec.model_fields)
        unknown = set(attrs) - valid
        if unknown:
            raise ValueError(f"Unknown rule attribute(s): {', '.join(sorted(unknown))}")
        # Rebuilt rather than assigned onto: pydantic does not validate an
        # assignment, so a `where` set as a plain mapping would sit in the spec
        # unparsed and the rule would silently do nothing with it.
        merged = {**rule.model_dump(exclude_none=True), **attrs}
        index = self._spec.validation_rules.index(rule)
        self._spec.validation_rules[index] = ValidationRuleSpec.model_validate(merged)

    def delete_rule(self: Self, rule_name: str) -> None:
        """Delete a validation rule by name.

        Raises:
            ValueError: If the rule is missing.
        """
        self._require_rule(rule_name)
        self._spec.validation_rules = [
            r for r in self._spec.validation_rules if r.name != rule_name
        ]

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    def to_yaml(self: Self) -> str:
        """Serialize the spec to a YAML document."""
        data = self._spec.model_dump(
            exclude_none=True, exclude_defaults=False, mode="json"
        )

        class _SpecDumper(yaml.Dumper):  # type: ignore[misc]  # yaml.Dumper is untyped
            pass

        def str_representer(dumper: yaml.Dumper, value: str) -> yaml.Node:
            if "\n" in value:
                return dumper.represent_scalar(
                    "tag:yaml.org,2002:str", value, style="|"
                )
            return dumper.represent_scalar("tag:yaml.org,2002:str", value)

        _SpecDumper.add_representer(str, str_representer)

        rendered: str = yaml.dump(
            data,
            Dumper=_SpecDumper,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )
        return rendered

    def validate(self: Self) -> list[str]:
        """Validate the draft via a full model build plus reference checks.

        Constructs a :class:`ProfileFacade` from the in-memory spec, which runs
        every entity through the model factory, and additionally checks that the
        root entity and all entity references resolve.

        The ``version`` format is reported here rather than raised on
        assignment: ``ProfileSpec`` rejects a malformed version when a spec is
        *loaded*, but pydantic does not re-validate attribute assignment, so
        ``set_metadata(version=...)`` can leave a draft that would not load
        back. Reporting keeps the draft editable and still catches the problem
        before ``save_spec`` (which refuses it) writes the file.

        Returns:
            A list of human-readable issues. An empty list means the spec is
            structurally sound and builds cleanly.
        """
        issues: list[str] = []
        spec = self._spec

        version_problem = check_profile_version(spec.version)
        if version_problem is not None:
            issues.append(version_problem)

        if spec.root_entity and spec.root_entity not in spec.entities:
            issues.append(f"root_entity '{spec.root_entity}' is not a defined entity")

        issues.extend(self._field_issues(spec.entities.items()))
        # A predicate problem is a defect, not an advisory: the rule carrying it
        # would never fire. Reported here so a draft is told while it is being
        # edited rather than when someone tries to load the saved profile.
        issues.extend(profile_predicate_issues(spec))

        try:
            from metaseed.facade.core import ProfileFacade

            ProfileFacade(spec.name or "draft", spec.version, spec=spec)
        except Exception as exc:  # surface any build failure as an issue
            issues.append(f"model build failed: {exc}")

        return issues

    def warnings(self: Self) -> list[str]:
        """Advisory findings: the spec builds, but something is likely unintended.

        Kept separate from :meth:`validate` rather than folded into its list.
        An advisory is not a defect -- positional inference always yields a
        working identifier, so a draft that trips one still builds, loads and
        validates datasets. ``validate()`` returning only defects also keeps its
        documented ``list[str]`` shape intact for the callers that treat a
        non-empty result as "this spec is broken".

        Returns:
            A list of human-readable advisories. An empty list means nothing
            looks suspect.
        """
        return self._weak_identifier_warnings()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _weak_identifier_warnings(self: Self) -> list[str]:
        """Report an entity whose identifier is inferred onto a weak field.

        Which field is asked about comes from
        :func:`~metaseed.specs.schema.identifying_field`, the one definition of
        the rule, so the advisory cannot name a different field than the one a
        dataset actually gets indexed by.

        A field is "weak" when nothing in the spec says its value will be present
        (not ``required``), distinguishing (no ``unique_within``) or shaped (no
        ``pattern``, ``enum`` or ``options``), it is free text (``string``), and
        its own name does not state that it is an identifier.
        """
        issues: list[str] = []
        for entity_name, entity_def in self._spec.entities.items():
            inferred = identifying_field(entity_def.fields)
            if inferred is None or inferred.is_identifier:
                continue
            if not self._is_weak_identifier(inferred):
                continue
            issues.append(
                f"{entity_name}: no field declares is_identifier, so the "
                f"identifier is inferred as '{inferred.name}', an optional "
                f"free-text field. Mark the intended field with "
                f"is_identifier: true."
            )
        return issues

    @staticmethod
    def _is_weak_identifier(field: FieldSpec) -> bool:
        """Whether a field is too unconstrained to be a credible identifier."""
        if field.required or field.type != FieldType.STRING:
            return False
        if field.options or field.unique_within:
            return False
        if field.constraints and (field.constraints.pattern or field.constraints.enum):
            return False
        return not _name_states_an_identifier(field.name)

    def _require_entity(self: Self, name: str) -> EntityDefSpec:
        if name not in self._spec.entities:
            raise ValueError(f"Entity '{name}' not found")
        return self._spec.entities[name]

    def _require_field(self: Self, entity: str, field_name: str) -> FieldSpec:
        entity_def = self._require_entity(entity)
        index = self._field_index(entity_def, field_name)
        if index is None:
            raise ValueError(f"Field '{field_name}' not found on '{entity}'")
        return entity_def.fields[index]

    def _require_rule(self: Self, rule_name: str) -> ValidationRuleSpec:
        for rule in self._spec.validation_rules:
            if rule.name == rule_name:
                return rule
        raise ValueError(f"Validation rule '{rule_name}' not found")

    @staticmethod
    def _field_index(entity_def: EntityDefSpec, field_name: str) -> int | None:
        for index, field in enumerate(entity_def.fields):
            if field.name == field_name:
                return index
        return None

    def _update_references(self: Self, old_name: str, new_name: str) -> None:
        """Rewrite all references to ``old_name`` after a rename."""
        for entity_def in self._spec.entities.values():
            for field in entity_def.fields:
                if field.items == old_name:
                    field.items = new_name
                if field.reference and field.reference.startswith(f"{old_name}."):
                    field.reference = f"{new_name}.{field.reference.split('.', 1)[1]}"
                if field.parent_ref and field.parent_ref.startswith(f"{old_name}."):
                    field.parent_ref = f"{new_name}.{field.parent_ref.split('.', 1)[1]}"

        for rule in self._spec.validation_rules:
            if isinstance(rule.applies_to, list):
                rule.applies_to = [
                    new_name if name == old_name else name for name in rule.applies_to
                ]
            elif rule.applies_to == old_name:
                rule.applies_to = new_name
            if rule.reference and rule.reference.startswith(f"{old_name}."):
                rule.reference = f"{new_name}.{rule.reference.split('.', 1)[1]}"

    def _auto_create_back_reference(
        self: Self, entity_name: str, entity: EntityDefSpec, field: FieldSpec
    ) -> None:
        """Create the parent identifier and target back-reference for a nested field."""
        if not field.is_nested() or not field.items:
            return
        target_name = field.items.strip()
        if target_name not in self._spec.entities:
            return
        target = self._spec.entities[target_name]

        # Resolve the parent's identifier field: a field already marked
        # is_identifier wins, then one literally named "identifier". Only inject a
        # synthetic "identifier" when the entity designates none -- otherwise an
        # entity whose identifier is e.g. project_id would gain a redundant,
        # required "identifier" and its generated model could not be instantiated.
        id_field = next((f.name for f in entity.fields if f.is_identifier), None)
        if id_field is None:
            id_field = next(
                (f.name for f in entity.fields if f.name == "identifier"), None
            )
        if id_field is None:
            entity.fields.insert(
                0,
                FieldSpec(
                    name="identifier",
                    type=FieldType.STRING,
                    required=True,
                    description="Unique identifier",
                ),
            )
            id_field = "identifier"

        # A field of that NAME already there is a collision whether or not it
        # declares a reference: appending a second one produced a spec with two
        # fields of the same name, which nothing rejects.
        back_ref_name = f"{to_snake_case(entity_name)}_id"
        has_back_ref = any(
            (f.reference and f.reference.startswith(f"{entity_name}."))
            or f.name == back_ref_name
            for f in target.fields
        )
        if not has_back_ref:
            target.fields.insert(
                0,
                FieldSpec(
                    # snake_case, not lower(): every shipped profile writes
                    # `observation_unit_id`, and a generated profile that says
                    # `observationunit_id` does not read like the ones it sits
                    # beside. The reference below is what carries the meaning.
                    name=f"{to_snake_case(entity_name)}_id",
                    type=FieldType.STRING,
                    required=True,
                    description=f"Reference to parent {entity_name}",
                    reference=f"{entity_name}.{id_field}",
                ),
            )

    def _field_issues(
        self: Self, entities: Iterable[tuple[str, EntityDefSpec]]
    ) -> list[str]:
        """Report container fields with no element type, and dangling targets.

        Also a ``reference_scope`` on a field that declares no ``reference``,
        which says how something resolves that does not exist.

        A ``list`` or ``entity`` field must name its element type in ``items``.
        The model build cannot catch an omission -- ``list`` becomes
        ``list[Any]`` and ``entity`` becomes ``Any`` whatever ``items`` says --
        so such a field validates while accepting anything and is never
        resolved as a nested entity. For a ``list``, ``items`` may name a
        primitive (``string``, ``integer``, ...); anything else must name a
        defined entity.

        Args:
            entities: The (name, definition) pairs to inspect.

        Returns:
            One human-readable issue per offending field.
        """
        issues: list[str] = []
        defined = set(self._spec.entities)
        for entity_name, entity_def in entities:
            for field in entity_def.fields:
                if (
                    field.type in (FieldType.LIST, FieldType.ENTITY)
                    and not (field.items or "").strip()
                ):
                    issues.append(
                        f"{entity_name}.{field.name}: {field.type.value} field "
                        f"has no 'items' element type"
                    )
                elif field.is_nested() and field.items and field.items not in defined:
                    issues.append(
                        f"{entity_name}.{field.name}: items target "
                        f"'{field.items}' is not a defined entity"
                    )
                for attr in ("reference", "parent_ref"):
                    ref = getattr(field, attr)
                    if ref and ref.split(".")[0] not in defined:
                        issues.append(
                            f"{entity_name}.{field.name}: {attr} target "
                            f"'{ref.split('.')[0]}' is not a defined entity"
                        )
                if field.reference_scope and not field.reference:
                    # Otherwise the marker is decorative: it says how a
                    # reference resolves on a field that declares none.
                    issues.append(
                        f"{entity_name}.{field.name}: reference_scope "
                        f"'{field.reference_scope}' needs a 'reference'"
                    )
        return issues
