# Codebase Review — metaseed + metaseed-hub

Multi-agent per-file review (20 module groups) with an adversarial verification pass on every high/medium finding. Only verified findings are reported as confirmed; lower-confidence notes are in the appendix.

## Baseline gates

| Gate | metaseed | metaseed-hub |
|---|---|---|
| ruff check | pass | pass |
| mypy (strict) | pass (175 files) | pass (60 files) |
| vulture (min-confidence 80) | clean | clean |
| file-size (<=1000 LOC) | none over | none over |
| tests | pass | pass |

## Summary

- Files reviewed: **211**
- Findings: 74 raw -> **19 confirmed** (7 medium, 12 low, **0 high**), 2 refuted, 53 unverified (low-confidence)
- **Coverage gap:** the `ms-adapters-ebi` group (ENA / PRIDE / MetaboLights / BrAPI importers) failed mid-stream and was **not reviewed**; re-run needed.

Recurring themes: (1) dead/stale code & docstring honesty; (2) a few correctness bugs in edge cases; (3) one hub comment-scoping gap.

## Confirmed — Medium (7)

### M1. get_identifier called without helper always returns None, making the dict branch dead
`src/metaseed/facade/graph.py:216` — *correctness* (ms-facade)

In to_graph's nested_fields reference pass, for a list item that is a dict the code does:

    elif isinstance(item, dict):
        from metaseed.repositories.helpers import get_identifier
        item_id = get_identifier(item)
        if item_id:
            ref_ids.append(item_id)

get_identifier(data, helper=None) returns None unconditionally when no helper is supplied (repositories/helpers.py: `if helper and helper.identifier_field:` ... else `return None`). So item_id is always None and no reference edge is ever produced for nested list items serialized as dicts. The branch is effectively dead and the intended reference edges are silently missing from the vis.js graph.

**Fix:** Resolve the target helper for the nested field and pass it, e.g. `target_helper = entities.get(helper.nested_fields[field_name]); item_id = get_identifier(item, target_helper)`.

### M2. material_source coordinate-pair rule silently validates the wrong (nonexistent) fields
`src/metaseed/validators/engine.py:318` — *correctness* (ms-validators)

In `_infer_rule_type`, the coordinate-pair inference only special-cases the `biological_material_` prefix:

    if "latitude" in rule_spec.condition and "longitude" in rule_spec.condition:
        if "biological_material_latitude" in rule_spec.condition:
            return CoordinatePairRule(lat_field="biological_material_latitude", ...)
        return CoordinatePairRule(lat_field="latitude", lon_field="longitude", ...)

The MIAPPE profile also declares `material_source_coordinate_pair` (applies_to BiologicalMaterial) with condition `(material_source_latitude AND material_source_longitude) OR (NOT material_source_latitude AND NOT material_source_longitude)`. Its condition contains the substring `latitude`/`longitude` but not `biological_material_latitude`, so inference falls through to the generic branch and builds `CoordinatePairRule(lat_field="latitude", lon_field="longitude")`. BiologicalMaterial has no bare `latitude`/`longitude` fields (they are `material_source_latitude`/`material_source_longitude`, confirmed at profile.yaml:825/834), so `has_value(data,'latitude')` and `has_value(data,'longitude')` are always False, the pair-equality check always passes, and the rule never fires. A BiologicalMaterial that supplies only `material_source_latitude` is wrongly accepted. The matching by substring is inherently fragile: any future coordinate rule not using one of the two hardcoded prefixes silently degrades to a no-op. No test exercises this rule (grep for `material_source_coordinate` in tests returns nothing).

**Fix:** Do not infer coordinate field names by substring/prefix. Derive lat/lon field names from the rule condition itself (parse the operands of the `(A AND B) OR (NOT A AND NOT B)` form), or require explicit `lat_field`/`lon_field` in the rule spec. Add a red-first test asserting that a BiologicalMaterial with only `material_source_latitude` set produces a coordinate-pair error.

### M3. Nested-form save cannot clear a field, unlike the table-cell editors
`src/metaseed/ui/routes/nested.py:207` — *consistency* (ms-ui-routes)

In save_nested_item, only non-None coerced values are written back: `coerced = _coerce_form_value(value, field_type); if coerced is not None: item[key] = coerced`. _coerce_form_value returns None for a blank submission (value == ""), so submitting a cleared field leaves the prior value in place — the field cannot be emptied through the nested form. The sibling editors on the same row store do the opposite: update_table_cell (`item[key] = value`), paste_cells (`item[field] = value`), and bulk_update_rows (`item[field] = value`) all write blank strings straight through, clearing the cell. Editing the same nested item via the table grid vs. the nested form therefore produces divergent results for a cleared field. The _coerce_form_value docstring compounds the confusion by saying a blank value should be 'dropped', which reads as 'removed' but the caller actually retains the stale value.

**Fix:** Decide on one clearing semantic for the shared row store and apply it in both paths (e.g. distinguish 'field present but blank' -> set to ""/remove key from 'field absent' -> keep), and align the _coerce_form_value docstring with the caller's actual behavior.

### M4. Unguarded tuple unpacking of rule.reference can raise ValueError
`metaseed/src/metaseed/ui/helpers/navigation_helpers.py:97` — *correctness* (ms-ui-helpers-specbuilder)

In get_reference_fields the field-based branch guards `if len(parts) == 2` before building the reference mapping (lines 80-85), but the legacy validation-rule branch does `target_entity, target_field = rule.reference.split(".")` with no length check. rule.reference is free-form text set by the spec builder (RuleUpdateData.apply_to_rule: `rule.reference = self.reference.strip() or None`). If a user enters a value without exactly one dot (e.g. "Study" or "a.b.c") on a rule that also has `field` set, the split does not yield 2 elements and the unpacking raises ValueError. get_reference_fields is called from build_inline_tables during form/table rendering, so this surfaces as an unhandled 500 rather than being ignored like a malformed field-level reference.

**Fix:** Mirror the field-branch guard: `parts = rule.reference.split("."); if len(parts) != 2: continue` before assigning target_entity/target_field.

### M5. AppState.reset() docstring claims "Reset all state" but leaves catalog_metadata (and version/profile/spec_draft) stale
`src/metaseed/ui/state.py:399` — *correctness* (ms-ui-core)

reset() clears the tree caches, editing_node_id, nested state and _current_dataset, but does NOT clear catalog_metadata, version, profile, spec_builder, or spec_draft. The docstring says "Reset all state." This is not merely cosmetic: switch_profile (routes/core.py:210) does `state.profile = name; state.facade = None; state.reset()` and the POST /reset handler calls reset() to return to a clean overview. In both paths the previously entered CatalogMetadata (DCAT title/description/publisher/license/contact) survives and is subsequently attached to a brand-new or different-profile dataset — see dcat.py:53/102 and dataset_manager._build_dataset_data (line 100) reading state.catalog_metadata. Reproduction: `s = AppState(); s.catalog_metadata = CatalogMetadata(title='X'); s.reset(); assert s.catalog_metadata is None` fails (it is still CatalogMetadata(title='X')). (The only path that resets it correctly, _restore_state_from_data, sets it explicitly before calling reset().)

**Fix:** Either clear catalog_metadata (and reconcile version/profile) inside reset(), or narrow the docstring to state exactly which fields it clears and clear catalog_metadata explicitly in switch_profile and the new-dataset flows.

### M6. save_dataset_state user_id parameter is never supplied by any caller
`metaseed-hub/src/metaseed_hub/ui/helpers/dataset_state.py:111` — *dead-code* (hub-ui-helpers-services)

save_dataset_state(session, dataset, state, user_id=None) sets DatasetVersion.created_by_id=user_id at line 141. A grep of the whole source tree and tests shows all 12 call sites (table.py, editor.py, crud.py) invoke it with three positional args only; no caller ever passes user_id. Consequently created_by_id is always None and version authorship is never recorded through this path. The parameter is an inert, aspirational hook that misleads readers into believing authorship is tracked.

**Fix:** Either thread the current user_id from the route dependencies into every call site so authorship is actually recorded, or remove the unused parameter and the created_by_id assignment until it is wired up.

### M7. add_spec_comment does not scope/validate parent_id to the draft
`src/metaseed_hub/ui/spec_builder/routes/comment_routes.py:88` — *correctness* (hub-spec-builder)

add_spec_comment inserts SpecComment(spec_draft_id=draft_id, parent_id=parent_id if parent_id else None, ...) using the client-supplied parent_id without any check that the parent comment exists or belongs to draft_id. This is exactly the class of cross-draft issue that the sibling routes were explicitly hardened against: delete_spec_comment and react_to_spec_comment carry comments ('Scope by spec_draft_id ...' / 'Confirm the comment belongs to the URL draft ...') and re-query the comment with SpecComment.spec_draft_id == draft_id, but add_spec_comment omits the equivalent guard. Failure scenarios: (1) a member of draft A supplies a parent_id belonging to draft B; the row is stored with spec_draft_id=A but parent_id pointing into B, producing an orphaned reply that renders under neither draft; (2) a non-existent parent_id violates the spec_comments FK and raises an unhandled IntegrityError -> HTTP 500.

**Fix:** Before inserting a reply, when parent_id is provided, load the parent comment and require parent.spec_draft_id == draft_id (mirroring delete_spec_comment/react_to_spec_comment); reject otherwise.

## Confirmed — Low (12)

### L1. SeekEntityConfig.role Literal duplicates SEEK_ROLES; docstring claim of single source of truth is false
`src/metaseed/specs/schema.py:98` — *consistency* (ms-specs)

SEEK_ROLES (line 72) is documented (lines 79-84) as "The single source of truth for the Spec Builder's role dropdown and the SeekEntityConfig.role validation". But SeekEntityConfig.role is validated by a separately hardcoded Literal["Investigation", "Study", "ObservationUnit", "Sample", "Assay"] (lines 98-100) that is NOT derived from SEEK_ROLES. Editing SEEK_ROLES (e.g. adding/removing a role) leaves the validating Literal unchanged, so the two silently drift and the documented invariant breaks. No test enforces that the tuple and the Literal agree. This violates the project's 'gates, not cleanup' and honest-docstring conventions: the docstring overstates SEEK_ROLES's role in validation.

**Fix:** Either derive the field constraint from SEEK_ROLES (e.g. validate role membership against SEEK_ROLES in a validator instead of a duplicate Literal), or add a test asserting the Literal args equal SEEK_ROLES, and correct the docstring to describe what actually enforces the constraint.

### L2. get_entity/list_entities leak live internal EntityData objects
`src/metaseed/repositories/file.py:251` — *consistency* (ms-repositories)

FileEntityRepository.get_entity returns `self._entities.get(entity_id)` and list_entities returns `list(self._entities.values())` / filtered live objects. These are the same mutable EntityData instances the repository persists via _save(). The sibling MemoryEntityRepository (memory.py get_entity/list_entities) never leaks internals: it constructs fresh EntityData copies from TreeNodes. A consumer that mutates a returned entity's `data` dict (and EntityService at ui/services/entities.py:87 hands `entity.data` straight into a response dict by reference) silently corrupts the repository's in-memory store, and the corruption is written to disk on the next create/update/delete. The two backends must present the same contract.

**Fix:** Return copies (e.g. deep-copy the EntityData / its data dict) from get_entity and list_entities, matching MemoryEntityRepository's copy-on-read behavior.

### L3. MemorySpecDraftStore.now parameter typed as Any instead of a callable type
`src/metaseed/repositories/spec_draft_store.py:89` — *typing* (ms-repositories)

`def __init__(self, now: Any = None)` and `self._now = now or _utc_now`. `now` is always used as a zero-arg callable returning an ISO timestamp string (see create/save calling `self._now()`). Typing it `Any` on a public constructor defeats the strict mypy gate and misrepresents the contract; a caller passing a non-callable would not be caught.

**Fix:** Type it `now: Callable[[], str] | None = None` (import Callable from collections.abc under TYPE_CHECKING) and annotate `self._now: Callable[[], str]`.

### L4. Reference-linked children loop in build_inline_tables is a no-op
`metaseed/src/metaseed/ui/helpers/table_helpers.py:140` — *dead-code* (ms-ui-helpers-specbuilder)

Lines 137-146 build `field_to_type = dict(helper.nested_fields)` and then, for each field_name in the source that is NOT already in field_to_type, call infer_entity_type_from_field(facade, entity_type, field_name). But infer_entity_type_from_field resolves purely from `parent_helper.nested_fields.get(field_name)` (its own docstring: "Resolution is spec-driven only"). For any field_name absent from field_to_type — i.e. absent from helper.nested_fields — that lookup returns None, so nothing is ever added. The loop and its comment "Also include reference-linked children from source (e.g., files linked via run_ref)" describe behavior the code cannot perform; reference-linked children are actually materialized as tree nodes by validation.process_reference_linked_children, not surfaced here.

**Fix:** Remove the dead loop (lines 139-146) and its misleading comment, or, if inline tables really need to display reference-linked children, resolve them via helper.reference_fields / tree children rather than infer_entity_type_from_field which only knows nested_fields.

### L5. List cardinality constraints (min_items/max_items) are never validated
`src/metaseed/agent/core.py:415` — *correctness* (ms-agent)

Constraints defines min_items and max_items (schema.py lines 67-68), and the validate_extracted MCP tool advertises that validate_instance 'Checks required fields, type constraints, and field-level validations'. However _validate_field only handles enum, pattern, min_length, max_length, minimum, and maximum — it never checks min_items or max_items. A profile declaring `min_items: 1` on a required list field will pass validate_extracted even when the list is empty or over-length, so a validator certifies content it does not actually check.

**Fix:** Add min_items/max_items checks for list values in _validate_field, or narrow the tool/docstring to state that list-cardinality constraints are not enforced by this lightweight validator.

### L6. Duplicate __all__ definition
`src/metaseed/forms/__init__.py:246` — *dead-code* (ms-cli-services-llm-forms)

`__all__` is defined twice with identical contents: once at lines 20-27 and again at lines 246-253. The second definition simply re-binds the same list at the end of the module, adding no value. It is redundant code that the project's "remove dead code" gate should not tolerate, and it invites the two lists to drift out of sync on future edits.

**Fix:** Remove the second `__all__` block (lines 246-253) and keep a single definition (either at the top or bottom of the module).

### L7. Unused duplicate CSRFValidationError class
`src/metaseed_hub/ui/dependencies.py:312` — *dead-code* (hub-ui-core)

dependencies.py defines `class CSRFValidationError(Exception)` (lines 312-315). Grepping the whole tree shows every actual import/use of CSRFValidationError resolves to the one in security.py (`class CSRFValidationError(HTTPException)`) - e.g. routes/auth.py imports it `from metaseed_hub.ui.security import CSRFValidationError`, and tests import from security. The dependencies.py definition is never imported or raised anywhere. It is dead code and, worse, a same-named shadow that invites confusion (the two classes have different base classes and behavior).

**Fix:** Delete the CSRFValidationError class from dependencies.py; keep only the security.py definition.

### L8. Unused DatasetNotFoundError class
`src/metaseed_hub/ui/dependencies.py:318` — *dead-code* (hub-ui-core)

`class DatasetNotFoundError(Exception)` (lines 318-321) is defined but never imported or raised anywhere in src/ or tests/ (grep for `DatasetNotFoundError` returns only this definition). The mutation dependency `get_dataset_state_for_mutation` and `get_dataset_for_user` raise fastapi HTTPException(404) instead. This violates the project's remove-dead-code rule.

**Fix:** Remove the class.

### L9. Unused unauthorized_response helper
`src/metaseed_hub/ui/dependencies.py:95` — *dead-code* (hub-ui-core)

`unauthorized_response()` (lines 95-103) returns an HTMLResponse for expired sessions but is never referenced anywhere in src/ or tests/ (grep returns only the definition). HTMX auth failures are handled by `handle_auth_required_error` / the AuthRequiredError path instead. This is dead code.

**Fix:** Remove the function, or wire it into the HTMX unauthorized path if it is intended to be used.

### L10. Unused backwards-compat aliases KeycloakAuth / get_keycloak_auth
`src/metaseed_hub/auth/__init__.py:188` — *dead-code* (hub-repos-api-auth)

`KeycloakAuth = OIDCAuth` (line 188), `get_keycloak_auth = get_oidc_auth` (line 209), and their `__all__` entries (lines 250, 254) are labelled "Backwards compatibility alias" but grepping the whole source tree and tests shows no consumer references either name (only OIDCAuth / get_oidc_auth are used). metaseed-hub is the top-level application, not a library other code imports, so there is no downstream caller these aliases preserve compatibility for. Their presence in `__all__` also hides them from the vulture gate. This is dead code plus an aspirational "backwards compatibility" label for compatibility no one needs.

**Fix:** Remove both aliases and their `__all__` entries, or add a comment justifying a concrete external consumer the way AsyncDatasetRepository was documented.

### L11. Database class docstring shows an unusable `async with db.session()` example
`metaseed-hub/src/metaseed_hub/database.py:24` — *docstring* (hub-infra)

The class docstring demonstrates usage as `async with db.session() as session:`. But `session()` (lines 77-89) is a plain async generator function (`async def ... yield`), so calling `db.session()` returns an `async_generator` object which implements `__aiter__`/`__anext__` but NOT `__aenter__`/`__aexit__`. Executing the documented example raises `AttributeError: __aenter__` (object does not support the asynchronous context manager protocol). Every real caller (database.py:102 in `get_session`, main.py:130 in `websocket_endpoint`) correctly uses `async for session in db.session():`, confirming the docstring is wrong, not the callers.

**Fix:** Replace the docstring example with `async for session in db.session():`, or decorate `session()` with `contextlib.asynccontextmanager` so the documented `async with` form actually works.

### L12. Listener holds _pubsub_lock across the 1s get_message timeout, stalling every join/leave
`metaseed-hub/src/metaseed_hub/websocket/__init__.py:91` — *correctness* (hub-infra)

In `_listen`, the `async with self._pubsub_lock:` block (lines 91-101) wraps `await self._pubsub.get_message(..., timeout=1.0)`, which awaits up to 1 second for a message while holding the lock. `join_room` (lines 206-207) and `leave_room` (lines 252-253) must acquire the same lock to `subscribe`/`unsubscribe`. Once at least one room is subscribed, the listener re-enters the timed read continuously, so any concurrent subscribe/unsubscribe is blocked until the current read returns, adding up to ~1s latency to every user join and leave (including the initial presence broadcast). Concrete case: with one room already subscribed, a second user's join_room awaits the lock at line 207 while the listener sits inside get_message(timeout=1.0) holding it; the subscribe and presence delivery are delayed up to ~1s, and this recurs on every join/leave under steady traffic. The lock is legitimately needed to serialize RESP access but should not be held across the blocking read.

**Fix:** Use a short get_message poll timeout (e.g. 0.05s) or acquire the lock only around the actual RESP read/subscribe operations so subscribe/unsubscribe are not starved by the read loop.

## Appendix — unverified low-confidence notes

Not adversarially verified (verifyLow=false); triage before acting.

- `src/metaseed/specs/persistence.py:174` — delete_user_spec does not lowercase name while save_spec does, risking a silent no-op delete *(ms-specs)*
- `src/metaseed/specs/builder.py:295` — add_field does not validate **attrs against model_fields, unlike update_field *(ms-specs)*
- `src/metaseed/specs/merge/strategies.py:151` — Misleading comment: 'Start with first constraint as base' but an empty Constraints is created *(ms-specs)*
- `src/metaseed/facade/store.py:146` — add_entity reimplements identifier-field indexing instead of reusing _get_identifier_fields *(ms-facade)*
- `src/metaseed/validators/engine.py:467` — Engine reaches into loader private `_load_profile` while dataset.py uses public `load_profile` *(ms-validators)*
- `src/metaseed/validators/rules.py:773` — PatternRule is a public rule class but is omitted from rules.__all__ *(ms-validators)*
- `src/metaseed/repositories/file.py:431` — reload()/_load() does not clear state when the backing file is gone *(ms-repositories)*
- `src/metaseed/repositories/file.py:197` — _build_hierarchy silently drops entities with a dangling parent_id *(ms-repositories)*
- `src/metaseed/repositories/memory.py:231` — _find_parent_from_references keeps an unused _facade parameter that the file backend dropped *(ms-repositories)*
- `metaseed/src/metaseed/api/validation.py:96` — ValidationIssue.field carries two different formats across the two public validate methods *(ms-api-models)*
- `metaseed/src/metaseed/models/factory.py:298` — _build_field_type annotated `-> type` but returns Any and list[Any] special forms; TYPE_MAP typed dict[FieldType, type] holds Any *(ms-api-models)*
- `metaseed/src/metaseed/api/schema.py:59` — EntitySchema docstring describes tuple attributes as "List" *(ms-api-models)*
- `metaseed/src/metaseed/api/client.py:454` — get_model reaches into EntityHelper private attribute _model *(ms-api-models)*
- `src/metaseed/ui/routes/__init__.py:1` — Package docstring omits seek, settings, and dcat route modules *(ms-ui-routes)*
- `src/metaseed/ui/routes/dcat.py:88` — register_dcat_routes is not re-exported from routes/__init__.py like its siblings *(ms-ui-routes)*
- `metaseed/src/metaseed/ui/helpers/entity_helpers.py:202` — Redundant `not isinstance(item, str)` after isinstance(item, dict) *(ms-ui-helpers-specbuilder)*
- `metaseed/src/metaseed/ui/helpers/spec_builder_helpers.py:19` — Private _list_specs re-exported but consumed nowhere *(ms-ui-helpers-specbuilder)*
- `metaseed/src/metaseed/ui/helpers/navigation_helpers.py:93` — applies_to == 'all' silently excludes rule from reference detection *(ms-ui-helpers-specbuilder)*
- `src/metaseed/ui/dataset_manager.py:302` — Two divergent implementations of "prefer MCP-context factory, else default" that can resolve to different factories *(ms-ui-core)*
- `src/metaseed/ui/spec_filesystem.py:114` — Redundant local re-import of SpecLoadError shadows the module-level import *(ms-ui-core)*
- `src/metaseed/ui/dataset_manager.py:302` — resolve_dataset_manager types the FastAPI app as Any on a public function *(ms-ui-core)*
- `src/metaseed/agent/core.py:437` — min_length/max_length use truthiness while minimum/maximum use `is not None` *(ms-agent)*
- `src/metaseed/agent/mcp/server.py:174` — reset_entity_service is a no-op whose name implies it resets state *(ms-agent)*
- `src/metaseed/agent/mcp/tools/profiles.py:75` — Duplicated field-type -> placeholder mapping in two functions *(ms-agent)*
- `src/metaseed/dcat/__init__.py:6` — Package docstring references a non-existent metaseed.dcat.mapping module *(ms-adapters-other)*
- `src/metaseed/seek/fairds.py:170` — to_fair_data_station_rdf docstring understates which entities are emitted *(ms-adapters-other)*
- `src/metaseed/seek/importer.py:135` — SEEK import direction is implemented and exported but not registered as an adapter action or wired to any host *(ms-adapters-other)*
- `src/metaseed/forms/__init__.py:205` — Public function field_errors_from_validation omitted from __all__ *(ms-cli-services-llm-forms)*
- `src/metaseed/cli/migrate_specs.py:0` — Orphaned one-off spec migration script *(ms-cli-services-llm-forms)*
- `metaseed/src/metaseed/_http.py:66` — Redundant exception in except tuple (TimeoutException is a subclass of TransportError) *(ms-core-root)*
- `metaseed/src/metaseed/core/serialization.py:16` — Docstring promises non-model tolerance that the type annotation forbids *(ms-core-root)*
- `metaseed/src/metaseed/core/__init__.py:1` — Stale legacy 'MIAPPE-API' naming in module docstring *(ms-core-root)*
- `metaseed-hub/src/metaseed_hub/models/__init__.py:398` — Enum persistence split: reactions stored by value, roles/status stored by name *(hub-models)*
- `metaseed-hub/src/metaseed_hub/ui/routes/dataset/versions.py:28` — _flatten_tree carries an unused `prefix` parameter *(hub-ui-routes)*
- `metaseed-hub/src/metaseed_hub/ui/routes/table.py:27` — _handle_primitive_list_row declares three unused parameters *(hub-ui-routes)*
- `metaseed-hub/src/metaseed_hub/ui/routes/table.py:254` — Logger imported and created inside functions rather than at module level *(hub-ui-routes)*
- `metaseed-hub/src/metaseed_hub/ui/routes/dataset/editor.py:483` — Redundant local re-import of HTTPException *(hub-ui-routes)*
- `metaseed-hub/src/metaseed_hub/ui/routes/dataset/crud.py:55` — Redundant local re-import of Path in dataset_new *(hub-ui-routes)*
- `metaseed-hub/src/metaseed_hub/ui/routes/auth.py:28` — OIDC config typed as dict[str, str] but holds non-string values *(hub-ui-routes)*
- `metaseed-hub/src/metaseed_hub/ui/services/entity_service.py:505` — Two divergent tree-serialization formats write the same dataset.data field *(hub-ui-helpers-services)*
- `metaseed-hub/src/metaseed_hub/ui/services/entity_service.py:505` — EntityService version creation drops created_by_id that the sibling path records *(hub-ui-helpers-services)*
- `metaseed-hub/src/metaseed_hub/ui/helpers/text.py:9` — humanize_field_name docstring example does not match actual output *(hub-ui-helpers-services)*
- `metaseed-hub/src/metaseed_hub/ui/helpers/dataset_state.py:32` — Public helpers annotate the DB session as Any while the sibling service uses AsyncSession *(hub-ui-helpers-services)*
- `src/metaseed_hub/ui/spec_builder/routes/draft_routes.py:148` — reset_draft leaves stale editing pointers in persisted state *(hub-spec-builder)*
- `src/metaseed_hub/ui/spec_builder/routes/draft_routes.py:382` — export_yaml redundantly re-imports load_state_for_draft *(hub-spec-builder)*
- `src/metaseed_hub/ui/spec_builder/forms.py:58` — Constraint numeric parsing raises unhandled ValueError on malformed input *(hub-spec-builder)*
- `src/metaseed_hub/ui/spec_builder/routes/list_routes.py:134` — hasattr(spec, 'name') guard is always true *(hub-spec-builder)*
- `src/metaseed_hub/ui/explore_routes.py:221` — Mixed user.keycloak_id vs user.sub for the same subject *(hub-ui-core)*
- `src/metaseed_hub/ui/explore_routes.py:24` — Unused module-level TYPE_CHECKING import of Spec/SpecDraft *(hub-ui-core)*
- `src/metaseed_hub/ui/explore_routes.py:412` — get_diff_graph omits the empty-profiles guard that compare has *(hub-ui-core)*
- `src/metaseed_hub/auth/__init__.py:42` — _oidc_config typed dict[str, str] but discovery document holds lists and bools *(hub-repos-api-auth)*
- `src/metaseed_hub/api/health.py:31` — Health-check engine leaked when connect() raises *(hub-repos-api-auth)*
- `src/metaseed_hub/api/datasets.py:136` — create_dataset bypasses dataset-name validation enforced by the repository *(hub-repos-api-auth)*

## Refuted (dropped by verification)

- src/metaseed/agent/mcp/tools/entities.py:663 bulk_update_entities aborts whole batch on a ValidationError
- src/metaseed/seek/client.py:252 SEEK list lookups read only the first JSON:API page, breaking documented idempotency
