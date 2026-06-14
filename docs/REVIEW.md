# Metaseed Code Review

Per-file consistency and correctness review of all `src/metaseed` Python modules, produced by a 19-group multi-agent pass with an adversarial verification stage. Every high/medium finding below was independently confirmed against the actual code by a second agent; severities reflect the verifier's correction where it disagreed with the reviewer.

## Status

All 47 confirmed findings listed below have been **resolved** (commits `868c2b1`..`ddb22e5`), each paired with tests. The three originally deferred design/feature items were also addressed: the unused `agent/llm` package was removed, dataset JSON import (`/import`) was implemented, and the MCP parent-detection duplication was refactored onto the facade's `reference_fields` map.

The appendix leads were subsequently put through the same adversarial verification: of 71 checked, 13 were refuted, 5 were upgraded to medium and fixed (`14d5a32`..`9134cc8`), and 53 were confirmed low. Of those, the in-scope safe subset (docstrings, typing, internal dead code, small robustness fixes) was applied (`4f3ed24`..`2845eb9`), and the public-API dead code — verified unused in both this repo and `metaseed-hub`, the sole consumer — was removed (`9db4cd2`, `350208d`).

Finally, the remaining design-smell items were tackled (`78c884e`..`1195f78`): the graph service now uses the public `facade.entities` property; dataset factory resolution is centralized across save/load/auto_save; the sync LLM entry point forwards conversation history; `to_snake_case` is a single shared `utils` helper; `MIAPPEBaseModel` was renamed `EntityBaseModel`; `PRIMITIVE_TYPES` now recognizes canonical `FieldType` scalar spellings (so typed lists are not misread as nested) while keeping the legacy `int`/`bool` spellings; and the redundant MCP-manager ContextVar was dropped. The ontology service's docstrings were already accurate (context-scoped), so no change was needed there.

All confirmed findings across the original review and the appendix are now resolved. The full suite passes (1517 tests).

## Baseline (objective gates)

| Gate | Result |
|---|---|
| ruff (lint) + ruff-format | Pass |
| vulture dead code @ 80% (gate threshold) | Pass, no findings |
| pytest (`not ui and not network`) | 1471 passed, 6 skipped, 1 xfailed, 0 failures |
| File-size rule (<1000 LOC) | Pass, largest 677 LOC |
| mypy | Not a configured gate; not enforced |

## Summary

- Files reviewed: **134**
- Confirmed findings: **47** (1 high, 26 medium, 20 low)
- Lower-confidence notes (unverified): **72** (appendix)
- Refuted by verification: **0**

Themes: a recurring **dead-code** cluster (whole `agent/llm` package, a shadowed top-level `facade.py`, several unused private helpers and methods), a recurring **`identifier`/`label` helper-not-passed** bug in `repositories/file.py`, **ontology service** correctness gaps (URL encoding, fail-open vs fail-closed, ineffective negative cache), and a few **`any`/`callable` builtins used as type annotations**.

## High severity

### `src/metaseed/services/ontology.py:457` — OLS4 term IRI is not double-URL-encoded; get_term builds a malformed URL
*correctness*

In get_term (line 457) and get_term_sync (line 526): `encoded_iri = httpx.URL(iri).raw_path.decode()`. For iri='http://purl.obolibrary.org/obo/PATO_0000001', httpx.URL(...).raw_path.decode() returns only the path component '/obo/PATO_0000001' (verified by running it), NOT a percent-encoded full IRI. The OLS4 endpoint `/ontologies/{ontology}/terms/{iri}` requires the FULL IRI double-URL-encoded (e.g. 'http%253A%252F%252Fpurl.obolibrary.org%252Fobo%252FPATO_0000001'). The current code yields a URL like '.../ontologies/pato/terms//obo/PATO_0000001' (note the double slash and missing scheme/host), so real term lookups will fail (404 / wrong term). Tests only cover the cached path, so this is uncaught.

**Fix:** Double-URL-encode the full IRI, e.g. `from urllib.parse import quote; encoded_iri = quote(quote(iri, safe='')) if iri else ''` and request `f"{self.base_url}/ontologies/{ontology}/terms/{encoded_iri}"`.

## Medium severity

### `src/metaseed/ui/routes/import_export.py:0` — Module named/documented for import provides only export; templates post to a non-existent /import route
*consistency*

The file is named import_export.py and routes/__init__.py documents it as 'import_export: Data import/export', but `register_export_routes` registers only `/export`. There is no `/import` route in the main app. Meanwhile templates included in the main page (templates/index.html and templates/datasets_list.html, both included via base.html which core routes render) issue `hx-post="{{ base_url }}/import"`. The only `/import` handler in the codebase is under the spec_builder router with prefix `/spec-builder` (i.e. `/spec-builder/import`), so `{{ base_url }}/import` has no matching route and will 404.

**Fix:** Either add a real `/import` route here (matching the documented purpose) or rename the module/docstring to export.py / 'export' to honestly reflect its contents, and fix the template targets to point at the actual import endpoint.

### `src/metaseed/agent/core.py:314` — Optional fields that convert to None are written as explicit null keys
*correctness*

In `_extract_row`, line 314: `if converted is not None or not field_spec.required:` then `instance[field_spec.name] = converted`. For an optional field whose source value is empty or unconvertible, `converted` is None and `not field_spec.required` is True, so `instance[name] = None` is stored. This pollutes extracted instances with explicit null keys for every unmapped/empty optional field, which then differ from the convenience function `extract_instances` (lines 524-533) that skips empty/None values entirely. The two extraction paths produce divergent output shapes for the same input.

**Fix:** Only assign when `converted is not None` (skip None for optional fields), mirroring `extract_instances`. e.g. `if converted is not None: instance[field_spec.name] = converted` and keep the required-failure error branch separate.

### `src/metaseed/agent/llm/anthropic.py:16` — Default model is a deprecated, near-retired Claude model ID
*correctness*

AnthropicProvider.__init__ defaults `model: str = "claude-sonnet-4-20250514"`. Per the current Anthropic model catalog this ID is deprecated and scheduled to retire 2026-06-15 (the project's currentDate is 2026-06-13 — two days out). After retirement the API returns 404. The default should be a current model alias such as `claude-opus-4-8` or `claude-sonnet-4-6` (bare aliases, no date suffix).

**Fix:** Change the default to `model: str = "claude-opus-4-8"` (or `claude-sonnet-4-6` for the speed/cost tier). Use the bare alias, not a date-suffixed ID.

### `src/metaseed/agent/mcp/tools/extraction.py:181` — extract_entities does not bound-check table_index and does not catch IndexError
*correctness*

Unlike analyze_mapping (which guards `if table_index >= len(content.tables)`), extract_entities passes table_index straight to ctx.extract_entities(0, entity, table_index=table_index). ExtractionContext.extract_entities raises IndexError for an out-of-range source_index or table_index (core.py:242-247), but the tool only catches (ValueError, SpecLoadError, json.JSONDecodeError). An out-of-range table_index therefore propagates an uncaught IndexError instead of returning the standard {"error": ...} JSON, breaking the tool's error contract and diverging from sibling tools.

**Fix:** Add a table_index range check mirroring analyze_mapping, or include IndexError in the except clause so the tool returns a JSON error.

### `src/metaseed/api/client.py:180` — create_entity/update_entity raise pydantic.ValidationError, not the documented api ValidationError
*correctness*

The docstrings of create_entity (line 182) and the surrounding API contract state "Raises: ValidationError: If data fails schema validation", and __init__.py exports metaseed.api.errors.ValidationError as part of the public exception hierarchy. However the actual code path (create_entity -> _facade.add_entity -> store.add_entity -> _create_instance -> helper.create -> self._model(**kwargs)) lets pydantic.ValidationError propagate unchanged. metaseed.api.errors.ValidationError is never raised anywhere in src/ (grep for 'raise ValidationError' / 'ValidationError(' under src/metaseed/api returns only the class definition). Callers who do `except metaseed.api.errors.ValidationError` per the documented contract will not catch validation failures.

**Fix:** Either catch pydantic.ValidationError at the API boundary in create_entity/update_entity and translate it into metaseed.api.errors.ValidationError(errors=[...]) (consistent with the 'Internal errors are caught at the API boundary and translated' design note in errors.py), or correct the docstrings to document that pydantic.ValidationError is raised and remove the unused public ValidationError.

### `src/metaseed/cli/__init__.py:205` — `template` command produces invalid JSON keys for optional fields
*correctness*

For optional fields the template builder inserts a YAML comment key: `template_data[f"# {field.name}"] = None`. This works only for the YAML branch. When `--format json` is requested, `json.dumps(template_data, indent=2)` serializes these as real object keys, e.g. `"# author": null`, which are not comments and pollute the JSON template with bogus `# `-prefixed properties. The 'commented example' technique is YAML-specific.

**Fix:** Skip optional fields entirely for JSON output (or use a separate representation), e.g. only add `# name` keys when `format` is YAML, and omit optional fields for JSON.

### `src/metaseed/facade/store.py:287` — delete_entity removes index entries without verifying ownership
*correctness*

In delete_entity's remove_recursively (lines 287-297), the index cleanup deletes `self._index[str(id_value)]` whenever the value is present, without checking that the entry actually points to the node being deleted: `if id_value and str(id_value) in self._index: del self._index[str(id_value)]`. Compare update_entity (lines 259-261) which correctly guards with `if self._index[str(old_value)] == node_id`. If two entities ever share an identifier value (e.g. an alias collision, which can occur because add_entity blindly overwrites the index at lines 140/151), deleting one node can drop the index entry pointing at the surviving node, leaving get_entity_by_ref unable to resolve it.

**Fix:** Mirror update_entity: only delete the index entry when `self._index[str(id_value)] == n.id`.

### `src/metaseed/repositories/file.py:274` — get_identifier called without helper always returns None, making parent auto-reference dead
*correctness*

In create_entity, the parent reference auto-fill calls get_identifier(parent.data) with no helper argument:

    parent_identifier = get_identifier(parent.data)
    if parent_identifier:
        data[ref_field] = parent_identifier

But helpers.get_identifier only returns a value when a helper with identifier_field is supplied: `if helper and helper.identifier_field: ...; return None`. With helper omitted it ALWAYS returns None, so the child's reference field to its parent is never populated. The sibling MemoryEntityRepository does this correctly via get_identifier_from_instance(parent.instance, parent_helper) (memory.py:122). FileEntityRepository has the parent helper available (it called find_parent_ref_field(helper, ...) just above) and the parent's helper can be fetched from the facade.

**Fix:** Pass the parent's helper: parent_helper = getattr(facade, parent.entity_type, None); parent_identifier = get_identifier(parent.data, parent_helper). Add a test asserting the child's ref field is filled with the parent's identifier value (not just truthy).

### `src/metaseed/repositories/file.py:286` — derive_label called without spec always returns generic 'New {entity_type}' fallback
*correctness*

All three derive_label calls in FileEntityRepository omit the spec argument:
  line 161: entity.label = derive_label(entity.entity_type, entity.data)
  line 286: label=derive_label(entity_type, validated_data)
  line 331: entity.label = derive_label(entity.entity_type, validated_data)

helpers.derive_label only derives a label from data when spec is provided: `if spec and hasattr(spec, 'fields') and spec.fields: ... return str(data[first_field])[:50]`; otherwise it returns the fallback `f"New {entity_type}"`. So every entity created/loaded via FileEntityRepository gets a generic label like 'New Investigation' instead of a label derived from its data. The facade EntityHelper exposes the spec (facade.helper.py:220 calls derive_label(self._name, data, spec=self._spec)), so file.py could pass helper._spec. The existing test test_derives_label_if_missing only asserts `entity.label` is truthy, so it does not catch this.

**Fix:** Pass the entity's spec to derive_label (e.g. via the EntityHelper obtained from the facade). Strengthen the test to assert the derived label equals the expected field value rather than just being truthy.

### `src/metaseed/services/ontology.py:580` — validate_term reports network failures as 'term not found', contradicting documented fail-open behavior
*correctness*

validate_term (line 580) and validate_term_sync (line 602) call get_term and return `(False, f"Ontology term '{term_id}' not found in OLS4")` whenever get_term returns None. But get_term returns None for BOTH a genuine 404 AND for network failures (httpx.RequestError at lines 473-475/541-543 and non-404 HTTPStatusError at lines 471-472/539-540 all `return None`). The facade wrapper metaseed/facade/helper.py:22 documents 'Network failures are treated as valid (fail-open) to avoid blocking work', which is NOT what happens here: a transient OLS4 outage will cause every term to be flagged invalid. There is no way for validate_term to distinguish 'absent' from 'unreachable'.

**Fix:** Have get_term signal network errors distinctly from a true 404 (e.g. raise on transport errors, or return a sentinel/3-state), and make validate_term return (True, None) on network failure to honor the documented fail-open contract.

### `src/metaseed/services/ontology.py:469` — Negative cache entries are ineffective; _get_cached cannot distinguish cached None from a cache miss
*correctness*

get_term caches a negative result on 404 via `self._set_cached(cache_key, None)` (lines 469, 537). However _get_cached (lines 213-228) returns entry.value, which is None for a negative entry, and callers test `if cached is not None`. So a cached negative result is indistinguishable from a cache miss and the term is re-fetched on every call, defeating the negative cache and still hitting the rate limiter / network each time. (Note: tests/test_services/test_ontology.py:211 only validates the validate_term path, where None happens to map to 'invalid', masking the issue.)

**Fix:** Use a distinct sentinel for cached misses (e.g. a module-level _MISSING object stored as the cache value) and have _get_cached return that sentinel so callers can tell a cached-negative from an absent key.

### `src/metaseed/specs/merge/comparator.py:478` — _compare_validation_rules only detects presence differences, not content differences
*correctness*

Despite the name 'compare validation rules', the method only flags a rule when it is absent from some profile: it includes a rule in diffs solely when present_count != len(profile_specs) (lines 507-509). ValidationRuleSpec carries many semantic attributes (type, message, condition, pattern, minimum, maximum, enum, reference, etc., per schema.py:189-199). Two profiles that both define a rule of the same name but with different conditions/patterns are reported as identical (no diff), which is incorrect for a comparator.

**Fix:** Compare the ValidationRuleSpec contents (e.g., model_dump equality) for rules present in all profiles and include them in diffs when they differ; or rename/scope the method to honestly reflect that it only reports presence differences.

### `src/metaseed/ui/helpers/table_helpers.py:14` — Broken TYPE_CHECKING import path for AppState
*correctness*

Under TYPE_CHECKING the module does `from .state import AppState`, but there is no `metaseed/ui/helpers/state.py` module. `AppState` lives in `metaseed/ui/state.py`. Sibling files import it correctly: validation.py uses `from ..state import AppState`, entity_helpers.py/navigation_helpers.py use `from metaseed.ui.state import AppState`. Because it is guarded by TYPE_CHECKING it does not raise at runtime, but every `AppState` annotation in this file (e.g. on `build_inline_tables`, `get_items_store`) references an unresolvable name, so static type checkers cannot resolve it and the annotations are effectively wrong.

**Fix:** Change line 14 to `from ..state import AppState` (or `from metaseed.ui.state import AppState`) to match the siblings.

### `src/metaseed/ui/routes/forms.py:33` — EXAMPLES_DIR resolves to a non-existent path, disabling the example-loading affordance
*correctness*

forms.py computes `EXAMPLES_DIR = UI_DIR.parent.parent.parent / "examples"` where UI_DIR is the `ui` package dir. That resolves to the repo-root `<repo>/examples`, which does not exist. The actual examples live in `src/metaseed/examples/` (confirmed: it contains darwin-core, dissco, ena, isa, miappe). At line 99 `example_exists = (EXAMPLES_DIR / state.profile / facade.version).exists()` therefore always evaluates to False, so `example_available` is never True and the form never offers to load an example, even when one exists. examples.py computes the correct path differently: `UI_DIR = Path(__file__).parent.parent` then `EXAMPLES_DIR = UI_DIR.parent / "examples"` -> `src/metaseed/examples`.

**Fix:** Make forms.py use the same resolution as examples.py: `EXAMPLES_DIR = UI_DIR.parent / "examples"` (i.e. `src/metaseed/examples`). Better, share a single EXAMPLES_DIR constant across examples.py/forms.py/core.py instead of recomputing it three different ways.

### `src/metaseed/ui/routes/validation.py:482` — validate_form constructs ProfileFacade without version, ignoring state.version
*correctness*

`facade = ProfileFacade(profile=state.profile)` omits the version argument. ProfileFacade defaults to the latest available version when version is None (facade/core.py: if version is None it uses `versions[-1]`). Every other route obtains the facade via `state.get_or_create_facade()`, which passes `self.version` (state.py line 245). So if the user selected a non-latest version, /validate validates against the wrong (latest) spec, and `facade.version` passed to `_validate_entity_deep` (line 493) won't match the version used elsewhere in the form lifecycle. This is both a correctness bug and a divergence from the sibling pattern.

**Fix:** Use `facade = state.get_or_create_facade()` like all other routes, so state.version is honored.

### `src/metaseed/ui/spec_builder/routes_export.py:264` — import_yaml assigns a string to template_source, which is typed/consumed as a tuple
*correctness*

In import_yaml the code does `builder.template_source = f"Imported: {file.filename}"`. But SpecBuilderState.template_source is declared `template_source: tuple[str, str] | None` (state.py:34) and the template `spec_builder/base.html` consumes it via index access: `Cloned from {{ template_source[0] }} v{{ template_source[1] }}` (base.html:39). After import, the route redirects to the index which renders base.html with this string value; indexing a string yields single characters, so the banner renders nonsense like 'Cloned from I vm' instead of indicating an imported file. This is both a type-contract violation and a user-visible rendering bug.

**Fix:** Either keep template_source a tuple (e.g. set it to None on import, or introduce a separate `import_source: str | None` field and a distinct template branch), or change the state attribute and template to handle the imported-string case explicitly. Do not overload a (profile, version) tuple field with a free-form string.

### `src/metaseed/agent/llm/anthropic.py:0` — Entire agent/llm package (base.py, anthropic.py) is unused
*dead-code*

The `metaseed.agent.llm` package (LLMProvider protocol, Message/Tool/Response/ToolCall, AnthropicProvider) is imported only within itself. Grepping all of src/ and tests/ shows no external importer: `grep -rn 'agent.llm' src tests` returns only the package's own files and JS noise. There are no tests for it (tests/test_llm.py tests an entirely different module, `metaseed.llm.LLMService`, an OpenAI-compatible HTTP client at src/metaseed/llm/). The MCP server, core.py, mapping.py, questions.py, and the UI never reference AnthropicProvider or LLMProvider. This is a complete, parallel LLM abstraction that nothing calls.

**Fix:** Remove the agent/llm/ package (base.py, anthropic.py, __init__.py), or wire it into an actual caller. If kept intentionally as a future API, document why and add at least one test; otherwise vulture (a configured pre-commit hook per CLAUDE.md) should be flagging this.

### `src/metaseed/api/validation.py:101` — ValidationMixin._get_instance_data is dead code shadowed by SerializationMixin via MRO
*dead-code*

MetaseedClient(SerializationMixin, ValidationMixin) resolves _get_instance_data to SerializationMixin._get_instance_data (confirmed: MetaseedClient.__mro__ is [MetaseedClient, SerializationMixin, ValidationMixin, object] and _get_instance_data.__qualname__ == 'SerializationMixin._get_instance_data'). ValidationMixin is never used standalone (grep). Therefore the copy at validation.py:101-113 is never executed. Worse, it diverges from the serialization copy: serialization uses model_dump(mode="json", exclude_none=True) while this one uses model_dump(exclude_none=True) (no mode="json"), so the two definitions are inconsistent in addition to one being dead.

**Fix:** Remove the duplicate _get_instance_data from ValidationMixin and rely on a single shared implementation, or extract it into a common base/helper used by both mixins so there is one source of truth.

### `src/metaseed/facade/node.py:59` — EntityNode.to_dict() is never called externally
*dead-code*

EntityNode.to_dict() (lines 59-67) is only referenced by its own recursion (line 66: `[c.to_dict() for c in self.children]`, where each `c` is itself a facade EntityNode). I grepped all of src/ and tests/ for `.to_dict()` call sites: the only consumers of node trees are graph.py `get_tree()` which builds an equivalent dict structure manually (lines 48-54), the store's own serializers, and the API client / UI which use their own distinct EntityNode/TreeNode classes (metaseed.api.entities.EntityNode, metaseed.ui.state.TreeNode), each with their own to_dict. No code path instantiates a facade EntityNode and calls .to_dict() on it. The method is dead code that also duplicates the dict shape produced by graph.get_tree().

**Fix:** Remove EntityNode.to_dict(), or have graph.get_tree() delegate to it to consolidate the duplicated tree-dict construction.

### `src/metaseed/repositories/filesystem_dataset.py:176` — serialize_tree_node is never called anywhere
*dead-code*

serialize_tree_node is defined at module level in filesystem_dataset.py but is only referenced by its own recursive call (line 209). Grep across src/ and tests/ finds no importer or caller; consumers import only FilesystemDatasetRepository from this module. The active serialization path uses facade.to_dict() (which emits _parent_unique_id). Note also that this dead function emits `_parent_unique_id`, whereas FileEntityRepository._parse_entities reads `_parent_id`/`parent_id` (file.py:156), so even if revived it would not interoperate with the file repository's parser.

**Fix:** Remove serialize_tree_node, or if it is intended public API, export it from __init__ and add a test/caller. The project rule requires removing dead code.

### `src/metaseed/specs/loader.py:402` — SpecLoader.save_user_profile is never called
*dead-code*

save_user_profile (lines 402-424) writes a profile to the user specs dir and clears the cache, but a grep across src/ and tests/ finds no callers. It is also the only write path on the loader, so its omission means user-profile persistence is handled entirely elsewhere (ui/spec_persistence.py via paths.get_user_specs_dir()). The method duplicates that responsibility and is unused. Notably it also persists `content` verbatim without validating it as a ProfileSpec, so even if revived it could write malformed profiles that later silently fail to load.

**Fix:** Remove save_user_profile, or if it is intended as the canonical save path, wire the UI persistence code to use it and add ProfileSpec.model_validate(yaml.safe_load(content)) before writing.

### `src/metaseed/ui/routes/validation.py:368` — Unused private function `_validate_nested_entities`
*dead-code*

`_validate_nested_entities(...)` is a near-duplicate of `_validate_nested_entities_with_checks` (line 405) but without the check_list tracking. Only the `_with_checks` variant is actually called (from `_validate_entity_deep` at line 227). grep of src/ and tests/ shows `_validate_nested_entities` has no callers. This is dead, duplicated logic.

**Fix:** Delete `_validate_nested_entities`; keep only the `_with_checks` version.

### `src/metaseed/ui/spec_builder/decorators.py:0` — decorators.py / require_spec is never imported or used anywhere
*dead-code*

The entire module decorators.py defines `require_spec(get_builder_state)`, an async-wrapping decorator factory. Grep across src/ and tests/ shows no import of the module and no call to `require_spec(` other than its own definition. Every route module instead duplicates a local `_require_spec()` helper (routes_main.py:49, routes_entities.py:38, routes_fields.py:92, routes_rules.py:97, routes_export.py:52). Per project rules dead code must be removed. The decorator also passes `builder` as the first positional argument to the handler, which does not match how any of the route handlers are written, so it could not be adopted as-is.

**Fix:** Delete decorators.py, or actually adopt it and remove the five duplicated `_require_spec()` helpers. Do not leave it unused.

### `src/metaseed/agent/mcp/tools/entities.py:157` — MCP-level parent auto-detection duplicates repository logic already invoked by the service
*design*

_find_parent_from_references (and _auto_fill_reference_fields) reimplement reference-based parent detection by iterating helper._spec.fields, parsing field.reference as 'EntityType.field', and scanning service.list_entities. However EntityService.create_entity -> MemoryEntityRepository.create_entity already auto-detects the parent from reference fields when parent_id is None (memory.py:100 calls its own _find_parent_from_references using helper.reference_fields). The MCP tool therefore runs a second, parallel parent-detection pass before delegating to the service, duplicating logic and risking divergence between the two implementations (one keys off field.reference, the other off helper.reference_fields).

**Fix:** Rely on the repository/service layer for parent detection and remove the MCP-level _find_parent_from_references pre-pass (or factor a single shared helper used by both layers).

### `src/metaseed/specs/loader.py:94` — _load_profile swallows ValidationError and returns None, hiding malformed profiles
*design*

In _load_profile the except clause `except (yaml.YAMLError, ValidationError) as e: logger.warning(...); return None` (lines 134-136) treats a structurally-invalid profile.yaml identically to a missing file. Callers like load_profile/load_entity/list_entities then report 'Profile not found' / 'Version not found' instead of surfacing the actual validation error. For a user-supplied profile with a schema mistake, the diagnostic is misleading (file exists but is reported absent). This contradicts the explicit, informative error mapping done in load_from_string (lines 178-185).

**Fix:** Distinguish 'file absent' (return None) from 'file present but invalid' (raise SpecLoadError with the formatted ValidationError, mirroring load_from_string).

### `src/metaseed/agent/mcp/tools/profiles.py:39` — Type annotation uses builtin `any` instead of `typing.Any`
*typing*

def _field_to_dict(field: any) -> dict: annotates the parameter with the builtin function `any`, not the type `Any`. Because of `from __future__ import annotations` the annotation is a deferred string so it does not raise at runtime, but it is semantically wrong, misleads readers, and would fail under tools that evaluate annotations (e.g. get_type_hints). The intended type is FieldSpec (which is already imported indirectly) or at minimum typing.Any.

**Fix:** Annotate as `field: FieldSpec` (import already available via metaseed.specs.schema) or `field: Any` with `from typing import Any`.

## Low severity

### `src/metaseed/cli/__init__.py:97` — `-v` short flag means --verbose in `profiles` but --version everywhere else
*consistency*

The `profiles` command binds `-v` to `--verbose` (`typer.Option("--verbose", "-v", ...)`), while every other command (`validate`, `template`, `convert`, `entities`, `check`) binds `-v` to `--version` for the profile version. The top-level callback even deliberately uses uppercase `-V` for its verbose flag to avoid this collision, but `profiles` reverts to lowercase `-v`. This makes `-v` ambiguous across sibling commands and is a usability/consistency hazard.

**Fix:** Use `-V` (or no short flag) for `--verbose` in the `profiles` command to keep `-v` consistently meaning `--version` across all commands.

### `src/metaseed/models/__init__.py:85` — name.title() mangles multi-word PascalCase entity names in the registry cache key
*correctness*

get_model normalizes the lookup name with `normalized_name = name.title().replace("_", "")`. For multi-word PascalCase names this corrupts the name: `"BiologicalMaterial".title()` -> `"Biologicalmaterial"`, `"ObservationUnit"` -> `"Observationunit"`, `"DataFile"` -> `"Datafile"`. 64 such entity names exist across the shipped profiles (MIAPPE 1.1/1.2, miappe-htp, pride). Consequences: (1) the key under which the model is stored in ModelRegistry (`normalized_name`) no longer equals the model's real class name `spec.name` (e.g. registry key "Biologicalmaterial" vs class __name__ "BiologicalMaterial"); (2) it diverges from create_model_from_spec, which registers into ModelContext under the un-mangled `spec.name`. The two caches therefore use different key conventions for the same entity. The lookup is internally self-consistent only because get_model always re-applies the same mangling, but any consumer that lists/inspects ModelRegistry keys, or that expects registry keys to match class names or the spec.name used elsewhere, will be wrong. `.title()` is the wrong tool for normalizing already-PascalCase names.

**Fix:** Normalize to PascalCase via a deterministic snake->Pascal conversion that preserves existing PascalCase (e.g. only transform when input contains underscores or is all-lower), or key the registry on `spec.name` after loading the spec so the cache key always equals the real class name. Avoid str.title() on identifiers.

### `src/metaseed/ui/helpers/validation.py:372` — Unreachable fallback branch in rebuild_nested_items_with_failures
*correctness*

The function does `updated_node = state.nodes_by_id.get(node_id)` then `if updated_node: ... else:` and inside the else re-runs the identical lookup `instance = state.nodes_by_id.get(node_id)` followed by `if instance:`. Since the else branch is only entered when `state.nodes_by_id.get(node_id)` already returned None, `instance` is always None here and the `if instance:` block (calling extract_nested_items) is dead/unreachable. The comment even says 'shouldn't happen'. The dead branch hides the fact that the only real fallback is `state.current_nested_items = {}`.

**Fix:** Remove the redundant second lookup and dead `if instance:` block; the else branch should simply set `state.current_nested_items = {}`.

### `src/metaseed/ui/spec_builder/routes_export.py:224` — Broad `except Exception` re-wraps the intentional HTTPException raised inside the same try block, masking its message
*correctness*

In apply_yaml_edit, the `if not isinstance(data, dict): raise HTTPException(status_code=400, detail="Invalid YAML: root must be a mapping")` at lines 203-207 is raised inside the try, then caught by `except Exception as e` at line 224 and re-raised as `detail=f"Failed to parse spec: {e}"`, producing a mangled message like 'Failed to parse spec: 400: Invalid YAML: root must be a mapping'. The same pattern exists in import_yaml: the non-dict HTTPException at lines 252-256 is caught by `except Exception` at line 278 and re-wrapped. The intended specific error detail is lost.

**Fix:** Re-raise HTTPException unchanged: add `except HTTPException: raise` before the broad `except Exception` in both apply_yaml_edit and import_yaml, or validate the mapping check outside the try.

### `src/metaseed/agent/mcp/manager.py:198` — Responsiveness check result is discarded; both branches return True
*dead-code*

In is_running(), when self._process is alive the code calls _check_mcp_responding() but returns True regardless of its result:

            if self._process.poll() is None:
                if self._check_mcp_responding(host, port):
                    return True
                # Process running but not responding - might be starting up
                return True

The HTTP request to _check_mcp_responding (a network round-trip with a 2s timeout) has no effect on control flow, so it is pure dead work and the comment implies an intent that is not realized. Either the responsiveness result should affect the return value or the call should be removed.

**Fix:** Remove the _check_mcp_responding call in this branch (just `return True` after poll() is None), or implement the intended distinction (e.g., return a tri-state / record 'starting up' state).

### `src/metaseed/api/errors.py:118` — Public ValidationError exception is never raised
*dead-code*

ValidationError (errors.py:118) is exported from metaseed.api.__init__ and metaseed.api.errors but is never instantiated or raised anywhere under src/ or tests/ (verified by grep). Its __init__ expects errors: list[dict[str,str]] but no code ever constructs it. It is effectively dead code, and its presence reinforces the misleading docstring contract in client.py.

**Fix:** Wire it into the API boundary (translate pydantic.ValidationError in create_entity/update_entity), or remove it and drop it from __all__.

### `src/metaseed/facade.py:0` — Top-level facade.py is permanently shadowed by the facade/ package and is unreachable dead code
*dead-code*

Both a module file `src/metaseed/facade.py` and a package directory `src/metaseed/facade/` exist. Python always resolves the package over the sibling module, so `import metaseed.facade` resolves to `facade/__init__.py` (verified: `metaseed.facade.__file__` -> `.../facade/__init__.py`). The entire content of `facade.py` (its `from metaseed.facade import (...)` re-export block and `__all__`) is never imported and can never execute. Its module docstring even claims 'This module re-exports from the metaseed.facade package for backward compatibility' / 'New code should import directly from metaseed.facade' which is self-contradictory because the file's own import path is the package. It is also stale: it re-exports `EntityHelper, EntityStore, validate_ontology_term, IDENTIFIER_FIELDS` but omits `jerm` and `miappe_htp` which the real package `facade/__init__.py` exports.

**Fix:** Delete `src/metaseed/facade.py`. It is tracked by git (`git ls-files` confirms) and serves no purpose; the `facade/` package is the live implementation.

### `src/metaseed/specs/loader.py:394` — SpecLoader.get_user_specs_dir is never called
*dead-code*

get_user_specs_dir (lines 394-400) returns self._user_specs_dir. Grep shows no callers in src/ or tests/; consumers that need the user specs dir import the module-level metaseed.paths.get_user_specs_dir directly (e.g. ui/helpers/spec_builder_helpers.py:123). This method is an unused wrapper.

**Fix:** Remove the method.

### `src/metaseed/specs/loader.py:345` — SpecLoader.get_profile_path is never called
*dead-code*

get_profile_path (lines 345-366) wraps _find_profile_file with ctx handling. Grep across src/ and tests/ finds no callers. It is unused public API.

**Fix:** Remove the method, or add a test/caller if it is part of the intended public surface.

### `src/metaseed/specs/merge/strategies.py:43` — MergeStrategy.resolve_attribute is never called
*dead-code*

The base-class method resolve_attribute(_attribute, values, profile_order) is defined on MergeStrategy but no subclass overrides it and no caller in src/ or tests/ invokes it (grep finds only the definition at strategies.py:43). The actual merge path uses resolve_field exclusively. This is unused API.

**Fix:** Remove resolve_attribute, or wire it into the attribute-level resolution if it was intended to be used.

### `src/metaseed/specs/merge/visualizer.py:161` — _create_field_nodes is never called
*dead-code*

The method _create_field_nodes builds separate field nodes and parent edges, but build_diff_graph intentionally embeds field data inside the entity node (see comment at line 61: 'fields are included in the node data, not as separate nodes'). Grep across src/ and tests/ finds the definition only at visualizer.py:161 with no callers. It is dead code.

**Fix:** Remove _create_field_nodes entirely (the show_unchanged-driven field-node rendering is unused).

### `src/metaseed/ui/helpers/navigation_helpers.py:153` — Incomplete loop body (pass after comment) in get_parent_identifier
*dead-code*

The `for ctx in reversed(state.nested_edit_stack):` block matches the parent entity type and then contains only comments followed by `pass`, doing nothing before falling through to `return ""`. This is aspirational/placeholder logic: when the parent is found in the nested edit stack the function silently returns an empty string instead of the parent's identifier. Additionally, `get_parent_identifier` is only re-exported via __init__/__all__ and has no actual caller in src/ or tests/, so the unfinished behavior is currently untested and unused.

**Fix:** Either implement the nested-edit-stack lookup (use ctx.row_idx against the parent's nested_items to read target_field) or remove the dead loop; reconsider whether the function should be exported at all given it has no callers.

### `src/metaseed/ui/helpers/spec_builder_helpers.py:101` — spec_to_dict is never called anywhere
*dead-code*

`spec_to_dict(spec)` has no references in src/ or tests/ (grep across *.py/*.html/*.yaml finds only its own definition). It duplicates the `spec.model_dump(...)` call already used internally by spec_to_yaml. Project rules require removing dead code.

**Fix:** Delete spec_to_dict, or add it to a public API surface with a real caller if it is intended to be part of the module's interface.

### `src/metaseed/ui/routes/core.py:136` — Nested helper `_index_context` is defined but never called
*dead-code*

Inside `register_core_routes`, `_index_context(state, **extra)` is defined (lines 136-146) to build a standard index.html context (including `base_url` from `_get_dataset_base_url`). No route in core.py (`index`, `edit_dataset`) or anywhere else calls it; both handlers build their context inline and render `base.html`. grep of src/ and tests/ shows the only occurrence is the definition. The helper is dead code. Note that crud.py's update/delete handlers also build index context inline and omit `base_url`, so the intended shared helper is not being used where it would help.

**Fix:** Either delete `_index_context`, or actually use it from the handlers that render index/base context (including the crud.py `index.html` responses) so `base_url` and tree data are produced consistently in one place.

### `src/metaseed/ui/routes/validation.py:311` — Unused private function `_validate_with_pydantic`
*dead-code*

`_validate_with_pydantic(model_class, values, path_prefix, error_list)` is never called. grep of src/ and tests/ returns only its definition. The active validation path uses `validate_entity_with_report` inside `_validate_entity_deep`. ruff does not flag it because it is a module-level function, but the project rules require removing dead code.

**Fix:** Delete `_validate_with_pydantic`.

### `src/metaseed/ui/routes/validation.py:339` — Unused private function `_validate_with_custom_rules`
*dead-code*

`_validate_with_custom_rules(...)` (which calls `validate_data`) is never invoked. grep of src/ and tests/ returns only the definition. Note `validate as validate_data` is imported at line 18 solely for this dead function, so removing the function also makes that import removable.

**Fix:** Delete `_validate_with_custom_rules` and the now-unused `validate as validate_data` import (line 18).

### `src/metaseed/ui/state.py:44` — TreeNode.create classmethod is never called
*dead-code*

TreeNode.create() (lines 44-74) builds a TreeNode from an entity instance using derive_label. A search of all `.create(` call sites across src/ and tests/ shows every caller is a facade helper (e.g. helper.create(), facade.Run.create()); none target TreeNode. TreeNode instances in this codebase are built either directly via the dataclass constructor (state.py add_node/update_node) or via TreeNode.from_entity_node. The create classmethod and its sole dependency on metaseed.repositories.helpers.derive_label are unreachable.

**Fix:** Remove the TreeNode.create classmethod (and its local derive_label import) since label derivation now flows through from_entity_node / facade helpers. Confirm with vulture as the project's dead-code policy requires.

### `src/metaseed/validators/__init__.py:437` — _field_has_value duplicates base.has_value verbatim
*dead-code*

`_field_has_value(data, field)` (lines 437-454) is byte-for-byte identical in logic to `has_value` already defined and exported in base.py (lines 11-28), which the rules module already imports and reuses. The package-level helper reimplements the same None/empty-string/empty-list check instead of importing the shared one, so the two can drift.

**Fix:** Import `has_value` from `metaseed.validators.base` and call it at line 310 (`if not f.required and has_value(data, f.name)`); delete `_field_has_value`.

### `src/metaseed/specs/merge/__init__.py:80` — compare() docstring claims ValueError for <2 profiles, but single-profile is supported
*docstring*

The package-level compare() docstring states 'Raises: ValueError: If fewer than 2 profiles provided.' (lines 80-81). The underlying SpecComparator.compare() (comparator.py:60-65) only raises when len(profiles) < 1 and explicitly supports a single profile via _explore_single (explore mode). The documented contract is wrong and contradicts the implementation.

**Fix:** Update the docstring to: raises ValueError only if no profiles are provided; a single profile returns an explore-mode ComparisonResult with all entities/fields marked UNCHANGED.

### `src/metaseed/validators/dataset.py:211` — visitor parameter annotated with builtin `callable` instead of a Callable type
*typing*

`_traverse_entity_tree(self, data, entity_type, visitor: callable, path="")` annotates `visitor` with the builtin function `callable`, not a type. `callable` is the runtime predicate function, so this is an invalid type hint that static checkers (mypy/pyright) reject. Every other public-facing signature in this module group uses precise PEP 585 annotations.

**Fix:** Use `from collections.abc import Callable` and annotate as `visitor: Callable[[dict[str, Any], str, str], None]` to match the actual call signature `visitor(data, entity_type, path)`.

## Appendix: lower-confidence notes (unverified)

These were flagged as low severity and not put through the verification stage. Treat as leads, not confirmed defects.

**`src/metaseed/agent/core.py`**
- L41 (correctness): TypeConverter ignores 'entity' field type and does no date/datetime/uri validation
- L316 (correctness): Required-field conversion-failure error is only recorded when the raw value is truthy
- L391 (consistency): `import re` performed inside _validate_field instead of at module top
**`src/metaseed/agent/excel.py`**
- L53 (correctness): Excel metadata reads workbook.sheetnames after workbook.close()
**`src/metaseed/agent/llm/anthropic.py`**
- L120 (design): Module-level type assertion `_: type[LLMProvider] = AnthropicProvider` is fragile and silently wrong
**`src/metaseed/agent/mcp/manager.py`**
- L348 (design): ContextVar wrapper around an already-singleton manager is redundant
**`src/metaseed/agent/mcp/server.py`**
- L14 (docstring): Module docstring lists a non-existent tool name and is out of date
- L164 (dead-code): reset_entity_service is a no-op still threaded through and called
**`src/metaseed/agent/mcp/tools/entities.py`**
- L218 (dead-code): Computed parent_field return value is never consumed by the only caller
**`src/metaseed/agent/mcp/tools/extraction.py`**
- L225 (consistency): export_metadata returns plain-string error instead of JSON error object
**`src/metaseed/agent/mcp/tools/ontology.py`**
- L27 (correctness): _make_request return type allows list but callers assume dict
**`src/metaseed/agent/questions.py`**
- L0 (dead-code): questions module (Question factories, Answer) is exported but never used
**`src/metaseed/api/client.py`**
- L433 (consistency): _validate_entity_type accepts case-insensitive types but does not normalize, propagating user casing into stored node.entity_type
**`src/metaseed/api/schema.py`**
- L39 (dead-code): FieldInfo.reference field is never populated or read
**`src/metaseed/cli/__init__.py`**
- L48 (consistency): EXIT_* constant block duplicated across three CLI files
**`src/metaseed/cli/commands/example.py`**
- L12 (dead-code): Unused exit-code constant EXIT_SUCCESS (and EXIT_VALIDATION_ERROR)
**`src/metaseed/cli/commands/merge.py`**
- L13 (dead-code): Unused exit-code constants EXIT_SUCCESS and EXIT_VALIDATION_ERROR
**`src/metaseed/cli/migrate.py`**
- L130 (correctness): Broad `except Exception` swallows all errors during dataset migration
- L141 (consistency): Two different `print_migration_report` implementations with incompatible signatures
**`src/metaseed/cli/migrate_specs.py`**
- L0 (design): migrate_specs.py is a standalone script never wired into the CLI app
**`src/metaseed/core/config.py`**
- L11 (dead-code): Settings / get_settings are exported public API but never consumed by application code
**`src/metaseed/facade/core.py`**
- L133 (consistency): _create_instance resolves helper via getattr instead of the injected _get_helper
- L209 (docstring): add_entity docstring says node_id 'generates a UUID' but a truncated hex is used
**`src/metaseed/facade/helper.py`**
- L134 (docstring): identifier_field docstring describes a label, not an identifier
**`src/metaseed/facade/store.py`**
- L142 (consistency): add_entity duplicates identifier-indexing logic instead of reusing _get_identifier_fields
- L461 (correctness): Bare `except Exception` silently swallows all node-creation errors during load
**`src/metaseed/llm/__init__.py`**
- L44 (consistency): Inconsistent `self: Self` annotation across methods
- L50 (docstring): Redundant `__init__` docstring duplicates the class Args block
- L204 (design): `get_response_sync` silently drops conversation history support
**`src/metaseed/models/factory.py`**
- L131 (typing): set_model_loader takes Any but the underlying ModelContext.set_loader expects a typed Callable
- L218 (naming): MIAPPEBaseModel is the base for all profiles, not just MIAPPE/ISA
- L367 (correctness): enum constraint on a LIST field would silently produce a scalar Literal instead of list[Literal]
**`src/metaseed/models/registry.py`**
- L18 (docstring): Registry docstrings hardcode 'MIAPPE version' though the registry serves all profiles
**`src/metaseed/models/types.py`**
- L15 (dead-code): is_valid_ontology_term is never called from production code
**`src/metaseed/profiles/factory.py`**
- L24 (docstring): Docstring example outputs are inaccurate vs. actual runtime behavior
**`src/metaseed/repositories/base.py`**
- L29 (dead-code): EntityData.to_dict and from_dict are unused
**`src/metaseed/repositories/helpers.py`**
- L39 (docstring): get_identifier docstring says 'first field' but impl uses helper.identifier_field and returns None without a helper
**`src/metaseed/services/ontology.py`**
- L205 (dead-code): Unused instance attribute OntologyService._lock
- L643 (design): ContextVar-based 'singleton' does not guarantee a single shared instance across tasks/threads
**`src/metaseed/specs/__init__.py`**
- L1 (docstring): Package docstring references MIAPPE-only parsing
**`src/metaseed/specs/merge/merger.py`**
- L204 (consistency): _merge_entity_fields takes a _profile_specs argument it never uses
**`src/metaseed/specs/merge/models.py`**
- L33 (dead-code): FieldDiff.base_value is declared but never populated or read
**`src/metaseed/specs/merge/strategies.py`**
- L380 (docstring): get_strategy docstring references **kwargs but parameter is **_kwargs and unused
**`src/metaseed/specs/merge/visualizer.py`**
- L408 (dead-code): to_mermaid appears unused outside the module
**`src/metaseed/specs/schema.py`**
- L1 (docstring): Module/class docstrings claim MIAPPE-only but the schema is profile-agnostic
- L31 (consistency): PRIMITIVE_TYPES values do not match FieldType enum values
- L129 (typing): example type excludes dict, making nested-entity examples fail to load silently
**`src/metaseed/storage/__init__.py`**
- L1 (docstring): Module docstrings claim MIAPPE-only scope but storage is profile-agnostic
**`src/metaseed/storage/yaml_backend.py`**
- L17 (docstring): YamlStorage docstring contains subjective marketing-style claim
- L17 (consistency): YamlStorage offers no formatting configuration while JsonStorage exposes an indent parameter
- L37 (correctness): save() only catches OSError; serialization errors propagate as raw yaml.YAMLError
**`src/metaseed/ui/datasets.py`**
- L27 (typing): ContextVar and _get_factory lack type parameters/annotations, diverging from sibling modules
- L144 (consistency): auto_save selects the factory differently from save_dataset/load_dataset
- L157 (design): auto_save mutates manager._current directly instead of using the public current_dataset property
**`src/metaseed/ui/helpers/__init__.py`**
- L6 (docstring): Package docstring submodule list omits the spec-builder helpers
- L16 (consistency): __all__ in entity_helpers omits two re-exported public functions
**`src/metaseed/ui/helpers/spec_builder_helpers.py`**
- L175 (typing): Lowercase `callable` used as a type annotation
**`src/metaseed/ui/helpers/table_helpers.py`**
- L45 (correctness): rstrip("s") over-strips multi-s field names when inferring entity type
**`src/metaseed/ui/routes/api.py`**
- L244 (consistency): Broad `except Exception` in validate_dataset_api diverges from specific handling elsewhere
**`src/metaseed/ui/routes/core.py`**
- L29 (dead-code): Unused module-level EXAMPLES_DIR constant (also wrong path)
**`src/metaseed/ui/routes/crud.py`**
- L192 (consistency): index.html context in crud.py omits base_url that core routes provide
**`src/metaseed/ui/routes/validation.py`**
- L483 (consistency): validate_form does not handle unknown entity_type from getattr(facade, ...)
**`src/metaseed/ui/services/entities.py`**
- L18 (dead-code): Unused backwards-compatibility alias AppStateAdapter
**`src/metaseed/ui/services/graph.py`**
- L40 (consistency): Reaches into private facade attribute instead of public property
**`src/metaseed/ui/spec_builder/__init__.py`**
- L33 (typing): get_state typed as builtin `callable` instead of a proper Callable annotation
**`src/metaseed/ui/spec_builder/routes_entities.py`**
- L35 (docstring): Docstring documents `base_url` but the parameter is named `_base_url` and is unused
**`src/metaseed/ui/spec_builder/routes_main.py`**
- L128 (design): Route reaches into SpecLoader private method _find_profile_file when a public API exists
**`src/metaseed/validators/__init__.py`**
- L41 (dead-code): _to_snake_case implemented twice across sibling modules
**`src/metaseed/validators/engine.py`**
- L461 (dead-code): create_engine_from_profile is unused outside docs
- L487 (consistency): Two different `validate` functions with incompatible signatures share the name
**`src/metaseed/validators/rules.py`**
- L209 (design): EntityReferenceRule.is_list is never wired through spec-based rule creation
- L561 (correctness): UniquenessRule is stateful but never reset by the engine pipeline
