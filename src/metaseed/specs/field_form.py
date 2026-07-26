"""Map a flat field form to a :class:`FieldSpec`.

This is the single source of truth for turning the raw values a field editor
collects (all strings/booleans) into a populated ``FieldSpec`` -- every attribute
including the spec_version 0.6 markers (``owns``, ``is_identifier``, ``is_label``,
``tier``, ``label``, ``unit``, ``example``, ``options``) and the ``Constraints``.

It is pure (no I/O) and is meant to be shared by every field editor -- the
built-in spec builder UI, the metaseed-hub spec builder, and the MCP
``spec_add_field`` / ``spec_update_field`` tools -- so the mapping cannot drift
between them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from metaseed.specs.schema import Constraints, FieldSpec, FieldType

_TIERS: tuple[str, ...] = ("required", "recommended", "optional")
Tier = Literal["required", "recommended", "optional"]


@dataclass
class FieldForm:
    """Raw field-editor input, normalized into a :class:`FieldSpec`.

    Every value is the raw form input (string or checkbox boolean); normalization
    (trimming, splitting lists, dropping empties, coercing constraint numbers)
    happens in :meth:`apply_to` / :meth:`to_field_spec`.
    """

    name: str
    field_type: str = "string"
    required: bool = False
    description: str = ""
    ontology_term: str = ""
    ontologies: str = ""  # comma/newline-separated
    codename: str = ""
    items: str = ""
    parent_ref: str = ""
    unique_within: str = ""
    reference: str = ""
    # Constraints
    pattern: str = ""
    min_length: str = ""
    max_length: str = ""
    minimum: str = ""
    maximum: str = ""
    min_items: str = ""
    max_items: str = ""
    enum_values: str = ""  # newline-separated
    # spec_version 0.6 markers
    owns: bool = False
    is_identifier: bool = False
    is_label: bool = False
    tier: str = ""
    label: str = ""
    unit: str = ""
    example: str = ""
    options: str = ""  # comma-separated

    def build_constraints(self) -> Constraints | None:
        """Return a ``Constraints`` from the constraint inputs, or None if none set."""
        if not any(
            [
                self.pattern,
                self.min_length,
                self.max_length,
                self.minimum,
                self.maximum,
                self.min_items,
                self.max_items,
                self.enum_values,
            ]
        ):
            return None
        return Constraints(
            pattern=self.pattern.strip() or None,
            min_length=int(self.min_length) if self.min_length.strip() else None,
            max_length=int(self.max_length) if self.max_length.strip() else None,
            minimum=float(self.minimum) if self.minimum.strip() else None,
            maximum=float(self.maximum) if self.maximum.strip() else None,
            min_items=int(self.min_items) if self.min_items.strip() else None,
            max_items=int(self.max_items) if self.max_items.strip() else None,
            enum=[v.strip() for v in self.enum_values.split("\n") if v.strip()]
            if self.enum_values.strip()
            else None,
        )

    def _tier(self) -> Tier | None:
        value = self.tier.strip()
        return cast("Tier | None", value if value in _TIERS else None)

    def apply_to(self, field: FieldSpec) -> None:
        """Populate an existing ``FieldSpec`` in place from this form.

        Booleans and empty strings normalize to ``None`` so an unset marker is
        dropped on serialization rather than written as ``false``/``""``.
        """
        field.name = self.name.strip()
        field.type = FieldType(self.field_type)
        field.required = self.required
        field.description = self.description.strip()
        field.ontology_term = self.ontology_term.strip() or None
        field.ontologies = [
            o.strip()
            for o in self.ontologies.replace("\n", ",").split(",")
            if o.strip()
        ] or None
        field.codename = self.codename.strip() or None
        field.items = self.items.strip() or None
        field.parent_ref = self.parent_ref.strip() or None
        field.unique_within = self.unique_within.strip() or None
        field.reference = self.reference.strip() or None
        field.constraints = self.build_constraints()
        field.owns = self.owns or None
        field.is_identifier = self.is_identifier or None
        field.is_label = self.is_label or None
        field.tier = self._tier()
        field.label = self.label.strip() or None
        field.unit = self.unit.strip() or None
        field.example = self.example.strip() or None
        field.options = [
            o.strip() for o in self.options.split(",") if o.strip()
        ] or None

    def to_field_spec(self) -> FieldSpec:
        """Build a fresh ``FieldSpec`` from this form."""
        field = FieldSpec(name=self.name.strip(), type=FieldType(self.field_type))
        self.apply_to(field)
        return field
