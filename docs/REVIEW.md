# Codebase Review — metaseed

Generated 2026-06-28 by the `codebase-review` multi-agent workflow (19 module groups, 138 files, adversarial verification of every high/medium finding).

## Baseline gates

The project's own definition of "flawless". All pass.

| Gate | Command | Result |
|------|---------|--------|
| Lint | `ruff check .` | pass |
| Format | `ruff format --check .` | pass (230 files) |
| Dead code | `vulture src/ --min-confidence=80` | pass (none) |
| Types | `python -m mypy src/metaseed` (strict) | pass (138 files) |
| Tests | `pytest -n auto -m "not network and not selenium"` | 1611 passed, 6 skipped, 1 xfailed |
| File size | ≤1000 LOC | pass (largest 793) |

## Summary

- Findings: **54** total → **14** confirmed (adversarially verified), 1 refuted, 39 low-confidence unverified.
- Confirmed by severity: **2 high**, **7 medium**, **5 low**.
- Recurring themes: a few **dual-path consistency gaps** (one code path does something a sibling path doesn't — auto-fill, error translation, validation strictness), and a couple of **value/identity bugs** (returning a pre-update object; an argument resolved then dropped).

All gates pass, so every item below is something gates cannot catch (logic, consistency, naming, docstrings).

## Confirmed — High

### cli/app.py:251 — convert command resolves --profile but ignores it when loading the model
*Severity:* high · *Category:* correctness

The `convert` command resolves the profile via `profile, version = resolve_profile_version(profile, version)` (line 244) and then calls `Model = get_model(entity, version)` on line 251. `get_model(name, version='1.2', profile='miappe')` defaults the profile to 'miappe', so the resolved `profile` value is dropped. When a user runs e.g. `metaseed convert ... --profile isa`, `resolve_profile_version` returns the latest ISA version, but that version string is then passed to `get_model` under the default 'miappe' profile, producing a wrong-profile model lookup (or a SpecLoadError for an ISA-only version under miappe). Every sibling command threads the resolved profile through: `validate` calls `validate_data(data, entity, version, profile=profile)` (line 150), `template`/`entities` use `SpecLoader(profile=profile)` (lines 180, 300). `convert` is the only one that silently discards it.

### repositories/memory.py:167 — update_entity returns stale data captured before the update
*Severity:* high · *Category:* correctness

In MemoryEntityRepository.update_entity the TreeNode is fetched up front (`node = self._state.nodes_by_id.get(entity_id)` at line 144), then `self._state.update_node(entity_id, instance)` is called and its return value discarded, and finally `return self._node_to_entity(node, include_children=False)` (line 167) serializes the ORIGINAL `node`. The wrapper holds a direct reference to the pre-update Pydantic instance: `state.update_node` delegates to facade store.update_entity which reassigns `node.instance = self._create_instance(...)` on the EntityNode and invalidates the TreeNode cache, returning a *new* TreeNode wrapping the new instance. The old `node` variable still points at the old wrapper/old instance, so `_node_to_entity(node)` dumps the pre-update `data` and `label`. The returned EntityData therefore does not reflect the update. This propagates: ui/services/entities.py:142-150 uses `entity.label` for its response and broadcasts the stale entity via `_notify_change("updated", entity)`, so MCP/UI report the value before the edit. Contrast create_entity (line 130) which correctly uses the fresh node returned by `add_node`, and file.py update_entity which mutates `entity.data` in place and returns the same live object.

## Confirmed — Medium

### agent/mcp/tools/entities.py:691 — batch_create omits reference-field auto-fill that create_entity performs
*Severity:* medium · *Category:* consistency

create_entity (line 498) calls `_auto_fill_reference_fields(entity_type, entity_data, service)` before delegating to the service, so a single created entity gets its reference field value (e.g. study_ref) filled in when exactly one candidate parent exists. batch_create (line 742-743) calls `service.create_entity(entity_type, data, parent_id)` directly with no auto-fill, so entities created in a batch do not get their reference field values populated even when the situation is unambiguous. Parent detection still happens at the repository layer for both paths, but the reference-field value auto-fill diverges, producing different stored data depending on whether an entity was created singly or in a batch.

### api/client.py:102 — Alternate constructors do not translate internal errors into MetaseedError
*Severity:* medium · *Category:* consistency

The errors.py module documents the design contract "Internal errors are caught at the API boundary and translated", and __init__ honors this by wrapping SpecLoadError/ValueError into ProfileNotFoundError (lines 97-100). But the two alternate constructors from_spec (line 102) and from_yaml (line 139) bypass this: from_spec calls ProfileSpecCls(**spec) and ProfileFacade(...) which can raise pydantic ValidationError; from_yaml calls ProfileFacade.from_yaml(path) which can raise FileNotFoundError, yaml.YAMLError, or pydantic ValidationError. None of these are translated, so a user calling MetaseedClient.from_yaml("missing.yaml") receives a raw internal/stdlib exception rather than a MetaseedError subclass, contradicting the documented boundary contract and diverging from __init__.

### facade/store.py:458 — load_from_dict validates strictly and silently drops incomplete entities, while the sibling tree-load path and add/update API support skip_validation
*Severity:* medium · *Category:* consistency

_create_node_from_dict calls `self._create_instance(entity_type, fields)` with the default skip_validation=False and catches ValidationError to skip+log the entity (lines 458, 501-516). The whole rest of the pipeline supports progressive editing with incomplete data: ProfileFacade.add_entity/update_entity expose skip_validation, to_dict serializes whatever was stored (with model_construct'd partial instances), and the sibling flat->tree loader api/serialization.py:_load_tree calls add_entity(..., skip_validation=True). As a result a draft dataset saved via to_dict (the flat format the UI dataset_manager and api/serialization use) cannot be reloaded via load_from_dict - every entity missing a required field is silently discarded. Verified: a DiSSCo dataset built with skip_validation=True and serialized via to_dict reloads as 0 entities. This also undercuts the node-id-persistence design documented at store.py:359-361/462-466, which explicitly aims to let identifier-less entities survive reload.

### models/factory.py:111 — ModelContext.get suppresses the wrong exceptions for lazy load failures
*Severity:* medium · *Category:* correctness

The on-demand loader is wired to get_model (set_model_loader(get_model) in models/__init__.py). When an entity/version cannot be resolved, get_model -> SpecLoader.load_entity raises SpecLoadError, which subclasses plain Exception (specs/loader.py:35). Internally load_entity already catches KeyError and re-raises it as SpecLoadError, so KeyError/LookupError can never escape the loader. The guard `with contextlib.suppress(KeyError, LookupError): model = self._loader(...)` therefore suppresses exceptions that are never raised, while the exception that IS raised (SpecLoadError) propagates out of get(). This contradicts the method's documented contract ('Returns: Model class or None if not found') and defeats the graceful `if model_class is None: continue` handling in EntityBaseModel._convert_nested_entities (factory.py:254): a nested-entity field referencing an unresolvable `items` type will crash model validation instead of being left for Pydantic to validate.

### specs/merge/merger.py:272 — Constraint-only differences bypass the merge strategy, breaking 'tighter/looser constraints win'
*Severity:* medium · *Category:* correctness

In `_merge_entity_fields`, `strategy.resolve_field` is only invoked for `DiffType.CONFLICT`; `DiffType.MODIFIED` fields are merged by taking the first available spec (`elif field_diff.diff_type in [DiffType.UNCHANGED, DiffType.MODIFIED]: ... merged_fields.append(spec); break`). However, in `comparator._analyze_field_diff` a field is only marked CONFLICT when `type`/`required`/`items` differ; differences confined to constraints (e.g. `max_length`, `minimum`, `enum`) are appended to `changed_attrs` as `constraints.<attr>` but leave `has_conflict=False`, so the field is classified MODIFIED. Consequently a field that differs only in its constraints never reaches `MostRestrictiveStrategy._merge_constraints_restrictive` / `LeastRestrictiveStrategy._merge_constraints_permissive`, and the documented behavior 'Tighter constraints win (lower max, higher min) / Enum values are intersected' (strategies.py lines 96-101, 203-209) silently does not apply. The constraint-merging code only runs when a constraint difference happens to co-occur with a type/required/items conflict.

### ui/routes/crud.py:339 — HX-Trigger selected by fragile substring match on the user-facing message
*Severity:* medium · *Category:* correctness

render_entity_form decides which client event to fire by inspecting the human-readable message string: `if "Created" in message: response.headers["HX-Trigger"] = "entityCreated" else "entityUpdated"`. The message is built from caller-supplied text that interpolates the entity type and node label (e.g. `f"Created {entity_type}: {node.label}"`, `f"Saved {entity_type}: {node.label}"`). If an entity type or label ever contains the word "Created" (e.g. a study labelled 'Created plots'), an update would emit the entityCreated event. The create/update distinction is already known unambiguously at every call site, so it should be passed explicitly rather than re-derived from prose.

### validators/api.py:217 — Missing required fields are reported twice in validate_entity / validate_entity_with_report
*Severity:* medium · *Category:* correctness

validate_entity runs Pydantic validation (lines 190-214) and then engine validation (lines 217-218). create_model_from_spec marks required fields with `...` (factory.py line 404/411-413), so when a required field is absent, `model_class(**simple_data)` raises a Pydantic 'Field required' error recorded with rule='constraint'. Separately, create_engine_for_entity always adds RequiredFieldsRule built from the SAME spec.get_required_fields() (engine.py lines 422-424), so engine.validate(data) emits a second error 'Field \'x\' is required' with rule='required_fields' for the identical field. The result is two user-facing errors for one missing field. validate_entity_with_report has the same double-reporting (Pydantic constraint failure plus the engine's required_fields check via validate_with_report). The docstrings frame the engine layer as adding only cross-field rules (date_range, coordinate_pair) on top of Pydantic constraints, so the required-fields overlap is unintended duplication.

## Confirmed — Low

### cli/output.py:53 — echo_info is a public helper that is never used
*Severity:* low · *Category:* dead-code

`echo_info` (line 53) is defined alongside `echo_error`, `echo_success`, and `echo_warning`, but a grep across `src` and `tests` shows no caller anywhere in the tree (the other three are all used). This is public-but-unused API that vulture at confidence 80 will not flag.

### repositories/memory.py:284 — AppStateAdapter backwards-compat alias has no consumers
*Severity:* low · *Category:* dead-code

`AppStateAdapter = MemoryEntityRepository` is declared as a "Backwards compatibility alias" but a grep across src, tests, and the sole external consumer (../metaseed-hub) finds zero references; it is also not exported in repositories/__init__.py __all__. It preserves compatibility with nothing.

### ui/helpers/spec_builder_helpers.py:31 — Private symbol _list_specs re-exported in __all__ but never imported via the shim
*Severity:* low · *Category:* dead-code

The shim imports `_list_specs` from metaseed.specs.persistence and lists it in `__all__`. A grep of the whole tree shows `_list_specs` is only ever called inside persistence.py itself (lines 119, 127); no consumer imports it through this shim, and tests do not use it. Re-exporting a private (`_`-prefixed) helper as part of a module's public API is contradictory, and vulture@80 misses it because membership in `__all__` marks it as used. The module docstring justifies re-exports as 'functions the UI has historically imported', but this one is neither historically imported here nor used anywhere.

### ui/helpers/entity_helpers.py:148 — extract_nested_from_tree reimplements reference-field lookup over private _spec instead of helper.reference_fields
*Severity:* low · *Category:* consistency

Lines 148-156 iterate `child_helper._spec.fields` and test `field.reference and field.reference.startswith(f"{parent_type}.")` to find children that reference the parent. The public property `helper.reference_fields` (facade/helper.py:117) already returns `{field_name: (target_entity, target_field)}` derived from exactly the same `reference` attribute, and the sibling module validation.py:198 uses it (`for ref_field, (target_type, _) in child_helper.reference_fields.items(): if target_type == entity_type`). This file instead reaches into the private `_spec` and duplicates the parse, diverging from the established idiom for the identical task.

### ui/spec_builder/routes_fields.py:243 — Invalid field_type raises uncaught ValueError (HTTP 500) instead of inline error
*Severity:* low · *Category:* correctness

In update_field, `field.type = FieldType(update_data.field_type)` constructs a FieldType enum directly from the submitted form value. If the value is not a valid FieldType member, `FieldType(...)` raises ValueError which is not caught, producing an HTTP 500. The sibling add_field route (lines 147-156) explicitly catches ValueError from the builder and renders an inline error via _entity_editor_response, so this is both an unhandled error path and an inconsistency between the two write routes. Although the value normally originates from a select element, an invalid POST bypasses the graceful handling.

## Appendix — unverified low-confidence notes

Reviewer-raised, not adversarially verified (the run targeted high/medium). Triage as time permits.

- `agent/__init__.py:1` [docstring] — Package docstring describes the mapping as 'AI-powered' but the agent-core logic is deterministic heuristic matching
- `agent/mcp/server.py:49` [consistency] — Unnecessary field(default=None) inconsistent with sibling field; sole use of the dataclasses.field import
- `agent/mcp/server.py:141` [dead-code] — Redundant standalone-state assignment already performed by set_context
- `agent/mcp/tools/__init__.py:0` [consistency] — spec_builder register function missing from package exports
- `agent/mcp/tools/datasets.py:100` [dead-code] — save_dataset has redundant duplicate except clauses
- `agent/mcp/tools/entities.py:200` [consistency] — _auto_fill_reference_fields uses stdlib logging at INFO, diverging from module's logging facade
- `agent/parsers/registry.py:49` [dead-code] — mime_types is declared on the parser interface but never read anywhere
- `api/client.py:437` [design] — get_model reaches into EntityHelper private attribute _model
- `api/rest.py:129` [correctness] — get_entity_schema only catches SpecLoadError, leaking ModelNotFoundError as 500
- `cli/migrate.py:141` [consistency] — print_migration_report has divergent signatures across the two near-mirror migration modules
- `core/__init__.py:1` [docstring] — Stale 'MIAPPE-API' project name in core package docstring
- `core/context.py:29` [consistency] — ProfileContext.cache_key duplicates loader logic but diverges (no lowercasing) and is unused in production
- `dcat/__init__.py:5` [docstring] — Package docstring references a non-existent metaseed.dcat.mapping module
- `dcat/serialize.py:188` [consistency] — to_graph binds vcard but not spdx prefix
- `repositories/memory.py:223` [consistency] — _find_parent_from_references takes an unused _facade parameter, diverging from file.py
- `services/ontology.py:498` [consistency] — get_term returns cached mutable OntologyTerm without defensive copy, unlike search
- `specs/loader.py:190` [dead-code] — Unreachable except yaml.YAMLError branch in load()
- `specs/loader.py:326` [consistency] — Divergent error message for the same missing-profile condition
- `specs/merge/merger.py:204` [dead-code] — Unused `_profile_specs` parameter with mismatched docstring
- `specs/merge/strategies.py:151` [docstring] — Misleading comment: 'Start with first constraint as base'
- `specs/merge/strategies.py:301` [dead-code] — Unreachable else branch in enum union
- `ui/dataset_manager.py:427` [dead-code] — AsyncDatasetManager and get_async_manager are unused public API
- `ui/helpers/__init__.py:6` [docstring] — Package docstring lists submodule names that do not exist
- `ui/helpers/entity_helpers.py:204` [dead-code] — Redundant `not isinstance(item, str)` guard that can never be False
- `ui/helpers/spec_builder_helpers.py:35` [dead-code] — get_custom_specs_dir re-exported but never consumed through the shim
- `ui/helpers/validation.py:68` [dead-code] — _format_validation_error parameter _entity_type is unused and labelled 'reserved for future use'
- `ui/routes/__init__.py:0` [consistency] — dcat route module omitted from package docstring and not re-exported
- `ui/routes/api.py:579` [design] — Reaches into another package's private helper (_make_request)
- `ui/routes/explore.py:1` [consistency] — Divergent import style from sibling route modules
- `ui/routes/table.py:140` [dead-code] — Unreachable else branch: entity_type already guaranteed non-None
- `ui/services/graph.py:6` [docstring] — Module docstring mislabels build_graph as a backward-compatibility wrapper
- `ui/spec_builder/routes_entities.py:142` [correctness] — update_entity mutates entity before rename, leaving partial changes and no mark_changed on rename failure
- `ui/spec_builder/routes_export.py:242` [docstring] — import_yaml docstring documents a 'request' parameter that does not exist
- `ui/spec_builder/routes_export.py:38` [docstring] — register_export_routes docstring omits the _base_url parameter
- `ui/spec_builder/routes_fields.py:111` [consistency] — _entity_editor_response duplicated verbatim across routes_entities and routes_fields
- `ui/state.py:78` [dead-code] — TreeNode.to_dict is never called
- `validators/engine.py:220` [correctness] — Spec-defined reference rules always receive an empty available_ids set
- `validators/engine.py:437` [consistency] — Engine reaches into SpecLoader private _load_profile while sibling uses the public load_profile
- `validators/rules.py:615` [docstring] — UniquenessRule docstring claims IdRegistry enforces identifier uniqueness, but it does not

## Refuted (rejected by verification)

- /Users/sdrwacker/workspace/metaseed-project/metaseed/src/metaseed/facade/store.py:368 to_dict only serializes parent links keyed on unique_id/alias, silently flattening the hierarchy on reload for most profiles
