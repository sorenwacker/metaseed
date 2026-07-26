# ADR 002: Repository and Validator Behavior at the Edges

**Date:** 2026-07-26
**Status:** Accepted
**Context:** Codebase-review remediation (see `docs/REVIEW.md`)

## Decision

Define the behavior of the file-backed repository and the lightweight extraction
validator for malformed input, missing state, and boundary constraint values, so
the edge cases are a documented contract rather than incidental behavior.

## Context

The codebase review surfaced a cluster of low-severity findings where the code's
behavior at an edge was either silently wrong or simply undefined. Each is small
on its own, but together they are the difference between "a green suite means
correct" and "a green suite means the happy path works". This ADR records the
chosen behavior and the reasoning, because for several of these there is no
single obviously-correct answer and a future reader needs to know the choice was
deliberate.

## Decisions and rationale

### 1. A dangling `parent_id` promotes the entity to a root

`FileEntityRepository._build_hierarchy` previously dropped any entity whose
`parent_id` referenced an id not present in the file: it was neither attached to
a parent (the parent did not exist) nor collected as a root (it had a
`parent_id`), so it vanished from `get_tree()` and the UI.

**Chosen:** treat a missing-parent reference as a root.

**Why:** silent data loss is the worst outcome for a metadata tool — a user who
opens a slightly corrupt file must still see and be able to repair every entity.
The considered alternatives were *log-and-drop* (the loss is recorded but the
data is still gone) and *raise* (refuse to load a corrupt file at all). Promotion
keeps the data reachable and lets the user fix the reference, which is the least
surprising and least destructive of the three.

### 2. `reload()` keeps the loaded state when the backing file is gone

`reload()` re-reads the JSON file; if the file no longer exists it now leaves the
in-memory store untouched rather than clearing it.

**Why:** a vanished file is far more likely to be an external accident (a synced
directory, a moved file, a transient mount) than a deliberate "empty this
dataset" signal. Preserving the last-known state avoids turning a filesystem hiccup
into data loss. The alternative — clearing the store to match the absent file —
was rejected because it makes the destructive outcome the default.

### 3. `get_entity`/`list_entities` return deep copies

The file backend returned its live internal `EntityData` objects, so a caller
mutating a result corrupted the repository's store (and the corruption was then
written to disk on the next save). The in-memory backend already copies on read.

**Why:** the two backends must present one contract, and a read must not be able
to mutate the store. Copy-on-read is the least astonishing behavior and matches
the sibling implementation.

### 4. The validator enforces every constraint it advertises

`_validate_field` did not check list cardinality (`min_items`/`max_items`) at
all, and used a truthiness test for `min_length`/`max_length` so a bound of `0`
was skipped (`max_length: 0`, meaning empty-only, was silently unenforced).

**Chosen:** validate list cardinality, and test `is not None` for length bounds.

**Why:** a validator that certifies input it never actually checks is worse than
no validator — it produces false confidence. This mirrors the project rule that a
passing conformance check must mean the content conforms.

### 5. `delete_user_spec` normalizes the name the same way `save_spec` does

`save_spec` stored specs under a lowercased, sanitized directory name;
`delete_user_spec` used the raw name, so deleting by the originally-supplied name
silently matched nothing. Both now share one `_normalize_profile_name` helper. A
side effect is that a traversal-style name is sanitized before the path is built,
so name-based traversal is neutralized earlier (version-component traversal is
still caught by the containment check).

**Why:** save and delete must agree on identity, or delete is unreliable.

### 6. SEEK role is validated against `SEEK_ROLES`

`SeekEntityConfig.role` was validated by a hardcoded `Literal` that could drift
from the `SEEK_ROLES` tuple the docstring named as the single source of truth. A
field validator now checks membership in `SEEK_ROLES` directly.

**Why:** a documented single source of truth must be the thing that actually
enforces the constraint, not a parallel copy that can silently diverge.

## Consequences

### Positive

- The edge behaviors are covered by tests that fail against the pre-fix code, so
  they are now gates rather than incidental behavior.
- No silent data loss on load, reload, or read.
- The lightweight validator no longer certifies unchecked content.

### Neutral

- Promotion (decision 1) changes the tree shape of a corrupt file rather than
  rejecting it; a caller that wants strict rejection must check separately.
- Keeping state on a vanished file (decision 2) means a genuine external deletion
  is not reflected until an explicit reload against a present (empty) file.

## References

- `docs/REVIEW.md` — the review findings these decisions resolve
- `src/metaseed/repositories/file.py`
- `src/metaseed/agent/core.py`
- `src/metaseed/specs/persistence.py`
- `src/metaseed/specs/schema.py`
