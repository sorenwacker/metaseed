# Metaseed Code Review

Per-file consistency and correctness review of all `src/metaseed` Python modules,
produced by a 19-group multi-agent pass with an adversarial verification stage.
Every high/medium finding below was independently re-checked against the actual
code by a second agent that tried to refute it; severities reflect the verifier's
correction where it disagreed with the original reviewer.

- Reviewed at commit: `9541529` (260614)
- Files reviewed: 126 (all of `src/metaseed`, plus one stray test picked up by the agent grouping)
- Findings: 81 raw -> 24 confirmed (1 high, 14 medium, 9 low) + 57 unverified low-confidence notes
- Refuted during verification: 0

## Baseline (objective gates)

These are the project's own definition of "passing", run from its Makefile and
`.pre-commit-config.yaml`.

| Gate | Command | Result |
|---|---|---|
| Lint | `uv run ruff check src tests` | Pass |
| Format | `ruff-format` (pre-commit) | Pass (lint clean) |
| Dead code | `uv run vulture src/ --min-confidence=80` | Pass, no findings |
| Tests | `uv run python -m pytest -m "not ui and not network"` | 1519 passed, 6 skipped, 1 xfailed |
| File size (<=1000 LOC) | project style rule | Pass (largest: `services/ontology.py`, 742 LOC) |
| Type check (mypy) | configured `strict` in `pyproject.toml` | Not a wired CI gate; not run as a pass/fail gate |

All objective gates pass. The findings below are issues the gates do not catch:
data-losing logic in code paths the tests do not exercise, behavioural divergence
between sibling implementations of a shared interface, dead public symbols, and
docstrings that describe behaviour the code does not implement.

## Summary

The codebase is in good shape: it lints clean, has no high-confidence dead code by
the gate threshold, no oversized files, and a large passing test suite. The
confirmed findings cluster into a few recurring themes rather than scattered
one-offs.

Recurring themes:

1. **The `ontologies` FieldSpec attribute is handled incompletely across the merge
   subsystem.** It is dropped by two merge strategies (data loss) and ignored by the
   comparator (false "unchanged"). This is the single highest-impact theme because it
   silently loses real spec data — `ontologies` is populated in MIAPPE 1.1/1.2,
   MIAPPE-HTP, MetaboLights, and PRIDE profiles.

2. **Sibling implementations of one interface have drifted apart.** The two
   `EntityRepository` backends (memory vs file), the two entity-extraction paths
   (`ExtractionContext` vs module-level `extract_instances`), and several duplicated
   route helpers behave differently for the same contract. Data created through one
   path is processed differently than through the other.

3. **Falsy-value and unguarded-conversion correctness bugs.** Truthiness filters
   (`and v`) drop legitimate `0`/`False`/`""` values; `fromisoformat` runs on raw
   YAML strings with no `try/except`, so a malformed date crashes a validation run
   instead of reporting a validation error.

4. **Dead public symbols and dishonest docstrings.** A handful of exported functions
   and dataclass fields are never used or never populated, and several docstrings
   claim behaviour the code does not implement (the most prominent: a serialization
   helper whose docstring calls it "the ONLY safe way" while no production code calls
   it).

None of these block the build, but the merge-strategy data loss (the one high) and
the date-parse crash are behavioural bugs that the current tests do not cover.

## Confirmed findings

Grouped by verifier-corrected severity. Each carries file:line, the concrete
problem, and the suggested fix.

### High

#### 1. MostRestrictive/LeastRestrictive merge strategies silently drop the `ontologies` field
`src/metaseed/specs/merge/strategies.py:128` (and `:239`) — correctness

Both `MostRestrictiveStrategy.resolve_field` (lines 128-140) and
`LeastRestrictiveStrategy.resolve_field` (lines 239-251) reconstruct a `FieldSpec`
field-by-field but never copy `base_spec.ontologies`. `FieldSpec` defines
`ontologies: list[str] | None` (`schema.py:99`) and it is populated in real specs
(MIAPPE 1.2 has 4 fields with `ontologies:`, MIAPPE 1.1 has 5; also MIAPPE-HTP,
MetaboLights, PRIDE). When a conflicting `ontology_term`-typed field is resolved by
these strategies, the OLS ontology search list is lost from the merged profile. The
merger's own `_apply_manual_resolution` uses `model_dump()`/`model_validate()` and
therefore preserves all fields, so these strategies diverge from the established
pattern and lose data.

Fix: build the merged spec from `base_spec.model_copy(update=...)` (or
`model_dump()`/`model_validate()`) so all `FieldSpec` fields including `ontologies`
are preserved, overriding only `required` and `constraints`.

### Medium

#### 2. `extract_instances()` is unused and duplicates `ExtractionContext` logic
`src/metaseed/agent/core.py:496` — dead-code

`extract_instances()` is exported in `agent/__init__.py.__all__` but is never called
anywhere in `src/`, `tests/`, or the sole external consumer `../metaseed-hub`. The
production extraction path (`agent/mcp/tools/extraction.py:181`) goes through
`ExtractionContext.extract_entities()` / `_extract_row()`. The function is a dead
public symbol carrying a second, divergent copy of the row-extraction loop.

Fix: remove `extract_instances()` and its `__all__`/import entries, or route it
through the same `_extract_row`/`TypeConverter` logic and add a test.

#### 3. `extract_instances()` skips type conversion the canonical path applies
`src/metaseed/agent/core.py:519` — consistency

`extract_instances()` (lines 519-537) assigns raw row values directly
(`instance[field.name] = value`) and never calls `TypeConverter.convert()`, so
integer/float/boolean/list fields stay as raw strings — unlike `_extract_row()`
(lines 314-316) which converts and records a `ValidationError` on failure. The same
operation produces different output types depending on the entry point.

Fix: have both entry points delegate to one shared conversion helper. (Resolving
finding 2 by removing the function also resolves this.)

#### 4. `entity_counts` counts only root entities while `total_entities` counts all
`src/metaseed/agent/mcp/tools/datasets.py:234` — correctness

`get_dataset_info` builds `entity_counts` by iterating `state.entity_tree` (root
`TreeNode`s only) but sets `total_entities = len(state.nodes_by_id)` (every nested
child, via the recursive `_index_tree_node`). For any dataset with nested children
(e.g. Study under Investigation, Sample under Study) the per-type counts will not
sum to `total_entities`.

Fix: iterate `state.nodes_by_id.values()` when building `entity_counts`, or compute
`total_entities` from the same root-only traversal if top-level counts are intended.

#### 5. `to_json_dict` docstring claims it is the ONLY safe serialization path, but no production code uses it
`src/metaseed/core/serialization.py:20` — docstring

The docstring states "This is the ONLY safe way to serialize entity instances for
JSON/YAML output." `to_json_dict` is referenced only in tests; ~82 production sites
call `instance.model_dump(mode="json", exclude_none=...)` directly, inlining the
exact logic the helper wraps. The helper is neither the only nor the actually-used
path — an inaccurate docstring on effectively test-only code.

Fix: route the production sites through `to_json_dict` (making the claim true and
removing duplicated inline logic), or soften the docstring to "convenience helper".

#### 6. `FileEntityRepository.create_entity` diverges from `MemoryEntityRepository`
`src/metaseed/repositories/file.py:252` — consistency

Both implement the same `EntityRepository.create_entity` contract, but
`MemoryEntityRepository.create_entity` (memory.py:83-140) auto-detects the parent
from reference fields, validates the parent-child relationship, and normalizes
reference fields before validation; `FileEntityRepository.create_entity` does none
of these. The same divergence exists for `update_entity` (memory normalizes
references at memory.py:142; file does not at file.py:314). Data created/loaded
through the file backend (used by metaseed-hub) is processed differently than
through the memory backend.

Fix: factor the shared create/update logic (reference normalization, parent-child
validation, parent auto-detection) into the `helpers` module and have both
repositories call it, or document why the file backend intentionally omits it.

#### 7. `search()`/`search_sync()` return and cache a shared mutable list
`src/metaseed/services/ontology.py:322` (and `:404`) — correctness

On a cache hit, `search` returns the exact list object stored in the cache (`return
cached`). If any caller mutates the returned list (sort/filter in place/append), the
mutation persists in the cache and corrupts results for all subsequent callers until
the TTL expires. The `OntologySearchResult` dataclasses are also not frozen.

Fix: return a shallow copy on cache hit (`return list(cached)`), or cache an
immutable representation.

#### 8. Field comparison omits `ontologies`, so differences are not detected
`src/metaseed/specs/merge/comparator.py:398` — correctness

In `_analyze_field_diff`, `attributes_to_compare` (lines 398-407) omits `ontologies`
(defined on `FieldSpec`). Two profiles defining the same field with different
`ontologies` lists are reported as UNCHANGED. (Same theme as finding 1.)

Fix: add `ontologies` to `attributes_to_compare`.

#### 9. MostRestrictive enum intersection produces None (no restriction) when empty
`src/metaseed/specs/merge/strategies.py:204` — correctness

`merged.enum = sorted(intersection) if intersection else None`. Disjoint enums (e.g.
`["x"]` and `["y"]`) intersect to the empty set, so `merged.enum` becomes `None`,
removing the enum constraint and letting the merged field accept ANY value — the
inverse of "most restrictive".

Fix: set `merged.enum = sorted(intersection)` (allow the empty list to signal an
unsatisfiable enum), or record an unresolved conflict; do not fall back to `None`.

#### 10. `edge_profiles` annotated as 3-tuple key but keys are 4-tuples
`src/metaseed/specs/merge/visualizer.py:179` — typing

`edge_profiles: dict[tuple[int, int, str], set[str]]` is declared with a 3-element
key, but the keys constructed (lines 208, 217) and unpacked (line 228) are 4-tuples
`(from_id, to_id, label, is_reference)`. The annotation is wrong and would fail mypy
strict.

Fix: change the annotation to `dict[tuple[int, int, str, bool], set[str]]`.

#### 11. Empty-helper fallback in `get_table_column_info` omits `column_ontologies`, callers KeyError
`src/metaseed/ui/helpers/table_helpers.py:70` — correctness

When `helper` is None (unknown `entity_type`), the fallback dict (lines 70-76)
returns without a `column_ontologies` key, while the success path (line 99) includes
it. Every caller in `routes/table.py` accesses `col_info["column_ontologies"]`
unconditionally (table.py:98, 191, 317), so an unresolved entity type raises
`KeyError: 'column_ontologies'`.

Fix: add `"column_ontologies": {}` to the fallback dict.

#### 12. `_clean_item_for_child_entity` drops falsy field values (0, False, "")
`src/metaseed/ui/helpers/validation.py:126` — correctness

The comprehension (lines 144-148) filters with `... and v ...`, silently discarding
legitimate falsy values: `0`, `0.0`, `False`, `""`. A child entity with a boolean
set to False or an integer set to 0 loses that field. This diverges from the sibling
`collect_form_values` (form_helpers.py:158-161), which only skips `None` and `""`.

Fix: replace `and v` with `and v not in (None, "")`, consistent with
`collect_form_values`.

#### 13. Redundant `build_inline_tables` wrapper duplicates the helper and is inconsistently re-exported
`src/metaseed/ui/routes/core.py:76` — design

`core.py` defines a thin wrapper that lazily imports and calls
`helpers.table_helpers.build_inline_tables`. `crud.py` and `forms.py` import the
wrapper from `.core`; `nested.py` imports the real helper directly from `..helpers`.
The wrapper also drops the helper's `items_source` parameter, so it can never reach
the nested-context path.

Fix: delete the wrapper; have `crud.py` and `forms.py` import `build_inline_tables`
from `..helpers` like `nested.py`.

#### 14. Unused method `get_current_entity_field_count`
`src/metaseed/ui/spec_builder/state.py:66` — dead-code

`SpecBuilderState.get_current_entity_field_count` (lines 66-73) is never called;
sibling helpers (`is_active`, `get_entity_names`, `mark_saved`, `mark_changed`,
`reset`) are all exercised by tests, but this one is not used by any route,
template, or test.

Fix: remove the method, or add a caller/test if it is intended to be public.

#### 15. `DateRangeRule.validate` crashes on malformed date strings (uncaught ValueError)
`src/metaseed/validators/rules.py:60` — correctness

`DateRangeRule.validate` calls `date.fromisoformat` / `datetime.fromisoformat` on
raw string values (lines 64-71) with no `try/except`. In the `DatasetValidator`
path the engine runs against raw YAML dicts that have NOT been Pydantic-coerced, so
a malformed date string (e.g. `start='2024-13-99'`) raises an uncaught `ValueError`
that aborts `validate_file()`/`validate_directory()` instead of producing a
validation error. The unit test only feeds well-formed values, so this is untested.

Fix: wrap the `fromisoformat` conversions in `try/except ValueError` and emit a
`ValidationError` (rule `date_range`) so a bad date string is reported as a
validation failure rather than crashing the run.

### Low

#### 16. `start()` ignores its own `port` argument in the already-running guard
`src/metaseed/agent/mcp/manager.py:77` — correctness

`start(self, transport, host, port=8001)` calls `if self.is_running():` with no
argument, so the guard always checks the default port 8001 rather than the requested
`port`. The orphan check below it correctly uses `port`.

Fix: pass the requested port through: `if self.is_running(port):`.

#### 17. `ValidationMixin` depends on a method defined only in `SerializationMixin`
`src/metaseed/api/validation.py:35` — design

`ValidationMixin` calls `self._get_instance_data` (lines 35, 83), which is defined
only in `SerializationMixin` (serialization.py:148). It works solely because
`MetaseedClient` inherits both and MRO resolves the attribute; composing
`ValidationMixin` alone, or reordering bases, would raise `AttributeError`.

Fix: move `_get_instance_data` into a shared base both mixins inherit, or declare it
as an abstract/Protocol method so the dependency is explicit.

#### 18. Broad `except Exception` swallows all errors during dataset migration
`src/metaseed/cli/migrate.py:130` (and `migrate_specs.py:109`) — correctness

`except Exception as e:` catches every error (including `KeyError`/`AttributeError`
programming bugs) and records only `str(e)`, masking real defects behind a catch-all.

Fix: catch the specific expected exceptions (`json.JSONDecodeError`, `OSError`), or
at minimum log the traceback.

#### 19. `OntologyTerm.parents` and `.children` are declared and serialized but never populated
`src/metaseed/services/ontology.py:112` — dead-code

`OntologyTerm` declares `parents`/`children` (lines 113-114) and `to_dict()`
serializes them (lines 125-126), but neither `get_term` nor `get_term_sync` parse
hierarchy data from the OLS4 response — only `synonyms` is filled. Every returned
term has empty `parents`/`children` regardless of the real hierarchy; the dataclass
advertises information it never provides.

Fix: populate them from the OLS4 hierarchical-links endpoints, or remove the two
fields and their `to_dict` entries.

#### 20. `list_datasets()` and `delete_dataset()` bypass the factory used by their save/load siblings
`src/metaseed/ui/datasets.py:86` (and `:181`) — consistency

The module-level `list_datasets()`/`delete_dataset()` directly instantiate
`FilesystemDatasetRepository()`, while their siblings `save_dataset()`/
`load_dataset()` resolve a manager via `_resolve_factory()` (which prefers the
MCP-context factory). In an MCP session a saved dataset can land in one repository
while list/delete operate on the default filesystem repository.

Fix: route `list_datasets()`/`delete_dataset()` through `_resolve_factory()` like
save/load, or remove them if no production caller needs them.

#### 21. `_get_dataset_manager` duplicated verbatim between `core.py` and `api.py` with divergent typing
`src/metaseed/ui/routes/api.py:141` — consistency

The nested helper is defined identically in `core.py` (typed `(state: AppState) ->
Any`) and again in `api.py` (untyped `def _get_dataset_manager(state):`), both doing
the same `context.dataset_factory` lookup with the same fallback. The api.py copy has
no annotations and no Google-style docstring.

Fix: extract one shared, annotated `_get_dataset_manager` and import it in both.

#### 22. Unused duplicate `AppStateAdapter` alias
`src/metaseed/ui/services/entities.py:18` — dead-code

`AppStateAdapter = MemoryEntityRepository` ("Backwards compatibility alias") is never
imported from this module; the canonical alias lives in `repositories/memory.py:286`.

Fix: remove line 18 (and the now-unused `MemoryEntityRepository` import if nothing
else uses it).

#### 23. Reaches into private `SpecLoader._find_profile_file` across a module boundary
`src/metaseed/ui/spec_builder/routes_main.py:128` — design

`clone_template` calls `loader._find_profile_file(version, profile)` — the only
external caller of a private method of `SpecLoader`, which exposes no public
path-resolution API. Renaming the private helper would silently break the route.

Fix: add a public `get_profile_path`/`find_profile_file` method on `SpecLoader` and
call that.

#### 24. Module-level `validate()` in `engine.py` is dead code
`src/metaseed/validators/engine.py:461` — dead-code

The module-level `validate(data, entity, version, profile)` (lines 461-481) is never
imported or called: the public `validate` everywhere comes from
`metaseed.validators.__init__` (a richer implementation with cascade/BaseModel
support). The engine copy duplicates a subset of it and is unreachable.

Fix: remove the `engine.py` module-level `validate` function.

## Appendix: unverified lower-confidence notes

These 57 low-severity notes were surfaced by the reviewers but NOT put through the
adversarial verification pass (the run used `verifyLow: false`). They are leads, not
confirmed defects — treat each as "check this", and verify against the code before
acting. Grouped by category.

### Docstring accuracy (15)

- `agent/mcp/manager.py:211` — `_check_port_in_use` docstring omits the `-1` sentinel return value
- `agent/mcp/tools/datasets.py:44` — `list_datasets` docstring claims "JSON array of dataset names" but returns an object with full metadata
- `agent/mcp/tools/profiles.py:132` — `get_field_spec` docstring omits that it resolves from current dataset state, not an explicit profile/version
- `cli/migrate.py:142` — public helper docstrings missing Args/Returns (not Google-style)
- `core/__init__.py:3` — docstring lists "configuration" the module does not provide
- `facade/store.py:101` — `add_entity` docstring claims it generates a UUID but it generates an 8-char hex
- `models/factory.py:223` — `EntityBaseModel` docstring claims a JSON serialization mode that is not configured
- `models/factory.py:23` — `ModelContext` docstring references a "model registry" the class does not encapsulate
- `repositories/helpers.py:4` — module docstring references the old name `AppStateAdapter`
- `repositories/helpers.py:43` — `get_identifier` docstring claims "first field is the identifier" but code uses `helper.identifier_field`
- `ui/helpers/entity_helpers.py:232` — `collect_entities_by_type` docstring return example does not match produced keys
- `ui/helpers/table_helpers.py:63` — `get_table_column_info` docstring lists an incomplete set of returned keys (related to finding 11)
- `ui/spec_builder/routes_export.py:232` — `import_yaml` docstring documents a `request` parameter the signature does not have
- `ui/spec_builder/routes_fields.py:88` — docstring documents `base_url` but the parameter is `_base_url`
- `ui/spec_builder/routes_rules.py:94` — docstring documents `base_url` but the parameter is `_base_url`

### Sibling consistency (14)

- `agent/mcp/server.py:228` — loop variable `field` shadows the `dataclasses.field` import
- `agent/mcp/tools/entities.py:108` — mixed logging idioms within the module
- `api/client.py:356` — inconsistent helper lookup: `getattr(facade, ...)` vs `facade.get_helper(...)`
- `cli/migrate.py:141` — two divergent `print_migration_report` implementations with incompatible signatures
- `facade/helper.py:342` — `validate_ontology_terms` still runs network validation on the `skip_validation=True` path
- `facade/store.py:160` — `_resolve_parent` uses exact-match `_get_helper` while instance creation uses case-insensitive `getattr`
- `llm/__init__.py:57` — inconsistent `self` typing within `LLMService`
- `logging.py:84` — `get_logger` wrapper coexists with the prescribed `logging.getLogger` pattern
- `repositories/helpers.py:74` — `derive_label` uses the literal first field while `get_identifier` uses the first non-reference field
- `ui/datasets.py:176` — `import_dataset()` uses `_get_factory()` instead of `_resolve_factory()`
- `ui/helpers/entity_helpers.py:147` — `extract_nested_from_tree` reaches into private `_spec` instead of the public `reference_fields`
- `ui/routes/explore.py` — diverges from sibling route modules: no `from __future__ import annotations`, eager imports
- `ui/spec_builder/routes_export.py:129` — `display_name`/`ontology` stored as `""` instead of `None`, diverging from `update_profile_metadata`
- `validators/rules.py:88` — `RequiredFieldsRule` does not share the `has_value` emptiness semantics used by sibling rules

### Correctness leads (7)

- `agent/parsers/csv.py:22` — `csv.Sniffer` can silently override the explicit `.tsv` delimiter
- `repositories/filesystem_dataset.py:76` — dataset sort mixes ISO timestamps and float-string mtimes, producing inconsistent ordering
- `specs/schema.py:281` — `_to_pascal_case` mishandles already-PascalCase input and embedded acronyms
- `ui/helpers/table_helpers.py:45` — `infer_entity_type_from_field` uses `rstrip('s')`, which strips all trailing `s` and mis-capitalizes multi-word names
- `ui/routes/api.py:244` — `validate_dataset_api` swallows all exceptions with a bare `except Exception`
- `ui/routes/table.py:295` — `bulk_update_rows` does not validate `field_name` is a nested field, yielding a TypeError 500 instead of a clean 404
- `ui/spec_provider.py:199` — version selection uses lexicographic sort (would order `1.10` before `1.2`)

### Dead code leads (7)

- `agent/parsers/registry.py:49` — `mime_types` declared on the Protocol and all parsers but never read
- `cli/output.py:53` — `echo_info` is never imported or called
- `models/factory.py:122` — `get_global_context` is exported but never called
- `specs/loader.py:172` — unreachable `except yaml.YAMLError` in `SpecLoader.load`
- `specs/merge/merger.py:204` — `_merge_entity_fields` takes an unused `_profile_specs` parameter; docstring names it `profile_specs`
- `ui/helpers/validation.py:67` — `_format_validation_error` first parameter is unused and named "reserved for future use"
- `ui/spec_filesystem.py:114` — redundant local re-imports of `SpecLoadError`

### Design leads (7)

- `agent/core.py:154` — `from_profile` passes `profile` to both the `SpecLoader` ctor and `load_profile`, redundantly
- `agent/parsers/excel.py:53` — `workbook.sheetnames` accessed after `workbook.close()`
- `agent/parsers/registry.py:11` — `ParsedContent` defined before the `ParsedTable` it references
- `cli/migrate_specs.py` — standalone script never wired into the CLI app
- `ui/routes/crud.py:348` — HX-Trigger chosen by substring-matching a human-readable message instead of the existing `message_type`/`is_edit` signal
- `ui/spec_builder/routes_fields.py:24` — `FieldUpdateData` abstraction is incomplete: `ontologies` handled outside the model
- `validators/dataset.py:183` — `DatasetValidator._detect_entity_type` hardcodes MIAPPE-specific field names for a profile-agnostic validator

### Typing leads (7)

- `agent/mcp/server.py:93` — several public module-level functions lack parameter/return annotations
- `api/client.py:415` — `facade` property annotated as `Any` instead of `ProfileFacade`
- `api/client.py:423` — `get_model` return type annotated as `Any` instead of a Pydantic model type
- `profiles/factory.py:64` — `get_profile_info` uses a bare `list[dict]` return annotation
- `ui/routes/validation.py:286` — `_separate_field_values` `entity_spec` parameter is unannotated
- `ui/spec_builder/routes_fields.py:99` — `_require_entity`/`_require_field`/`_auto_create_back_reference` lack the entity type annotations present in the sibling file
- `utils/json.py:13` — `DateAwareEncoder.default` lacks type annotations

## Method

- Source root: `src/metaseed` (126 files, ~27k LOC), grouped into 19 review units.
- One reviewer agent per group found candidate issues; an adversarial verifier then
  tried to refute each high/medium finding against the actual code, adjusting
  severity where it disagreed. Low-severity findings were not verified and appear in
  the appendix as leads.
- This review only *finds* issues; no code was modified. Remediation is a separate,
  user-approved step.
