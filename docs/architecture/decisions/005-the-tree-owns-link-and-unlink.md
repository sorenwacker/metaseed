# ADR 005: The tree owns link and unlink

Date: 260814

## Status

Accepted

## Context

Three components each hand-maintained the parent-child invariant of the
entity tree: `EntityStore` (facade), `FileEntityRepository`, and
`MemoryEntityRepository`. The invariant has three parts — membership in
`parent.children`, the child's `parent_id`, and the parent's nested
reference field naming the child — and each component kept its own copy of
the bookkeeping.

The 260814 review triage fixed three bugs that are all the same bug:
creation wrote the child's identifier into the parent's reference field and
deletion forgot to take it out (dangling references, in two components
separately); and the writer treated every reference field as a list, so an
exactly-one-child (`type: entity`) reference was silently coerced into one.
Structure-maintenance logic living outside the structure is how a class of
defect stays writable after any single instance of it is fixed.

The two data representations differ in how a write lands: the repositories
mutate a plain `data` dict on `EntityData`, while the store replaces an
immutable-by-convention pydantic instance via `model_copy`. A single
component cannot own the *write* without absorbing both representations.

## Decision

One module, `metaseed.facade.linking`, owns the DECISIONS of the invariant;
the components apply them to their own representation.

- `target_reference_field(parent_helper, child_type)` — which parent field
  references a child of this type (the first-match rule over
  `nested_fields`, stated once).
- `linked_reference_value(parent_helper, field, current, child_ref)` — the
  field's new value when a child is linked: append for a list field, claim
  if empty for an exactly-one-child field, `NO_CHANGE` otherwise. The
  LIST-vs-ENTITY shape rule lives here and nowhere else.
- `unlinked_reference_value(parent_helper, field, current, child_refs)` —
  the field's new value when a child is unlinked: the member removed from a
  list, an exactly-one-child scalar cleared when it names the child,
  `NO_CHANGE` otherwise.
- `link_child(parent, child)` / `unlink_child(parent, child)` — the
  structural half (children membership plus `parent_id`), generic over any
  node carrying `id`, `children`, and `parent_id`, which both `EntityData`
  and `EntityNode` do.

`repositories.helpers.update_parent_reference` and
`remove_parent_reference` keep their public signatures and become thin
appliers of these decisions onto a data dict. The store's instance-side
removal applies the same decision via `model_copy`.

## Enforcement

A gate test fails when the shape rule grows a second home: within
`src/metaseed`, the discriminator `single_entity_fields` may be referenced
only where it is defined (`facade/helper.py`) and where it is decided
(`facade/linking.py`). A repository that starts deciding shapes again turns
the gate red.

## Consequences

- A future field shape (or a change to the first-match rule) is one edit.
- The dangling-reference class of bug requires editing `linking.py` to
  reintroduce, where the whole invariant is in view.
- The appliers stay per-representation, so no component takes on the other's
  mutation model.
