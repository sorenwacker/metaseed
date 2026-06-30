# Codebase Review — metaseed core
_Full-codebase multi-agent review, 2026-06-30. 101 files reviewed across 21 groups (adapters excluded — reviewed separately in #94). Adversarial verification on every high/medium; the 5 verifiers that hit a session limit were verified by hand (see Verified-by-hand)._
## Baseline gates
| Gate | Result |
|---|---|
| ruff | pass |
| mypy (strict, 156 files) | pass |
| vulture @80 | pass |
| file size <1000 LOC | pass (largest 710) |
| pytest | 1701 passed |

## Summary
- **Confirmed (workflow):** 17 — 1 high, 15 medium, 1 low
- **Verified by hand (session-limit):** 5 — 0 high (1 downgraded), 5 medium
- **Unverified low-confidence notes:** 23 (appendix)

**Recurring themes:** (1) *false-negative validation* — multiple public paths silently skip Pydantic constraint checks (`validators/api.py validate()`, REST `/validate`, `UniquenessRule` no-op, dataset path, ontology non-OBO, extraction required-None); (2) *dual-path divergence* — the same operation behaves differently across MeteseedClient / facade / repositories / REST; (3) *silent data loss* — dangling parent_id drops entities, DCAT/import paths drop fields.

## Confirmed — HIGH

### `validators/api.py:131` — validate() (REST/CLI path) silently skips all Pydantic constraint checks
*high · correctness · group: validators-api*

Two public validation paths cover the same operation but with different coverage. validate_entity() (the function whose own docstring calls itself "the canonical validation function that both UI and MCP should use") runs BOTH Pydantic model validation (type/pattern/min_length/max_length/minimum/maximum/enum) AND the rule engine. validate() runs ONLY the rule engine: cascade=True dispatches to _validate_nested -> engine.validate, and cascade=False likewise returns engine.validate(data). It never constructs the Pydantic model.

The engine intentionally does NOT implement those constraints — engine.py:_infer_rule_type returns None for pattern, numeric range, and enum rules with the comment "Handled by Pydantic ... constraint". Consequently, on the validate() path those constraints are validated nowhere: a string in an integer field, a value violating a regex pattern, an out-of-range number, or an invalid enum value all pass validation silently (false negative).

This path is not hypothetical: the FastAPI /validate endpoint (api/rest.py:150, `errors = validate_data(request.data, request.entity, request.version)`) and the CLI validate command (cli/app.py:150) both call validate(), whereas the facade validation (api/validation.py) and UI/MCP use validate_entity()/validate_entity_with_report(). The same entity validated through REST vs. through the client facade yields different results, and REST reports valid for data that violates field constraints. (Compounding it, rest.py passes no profile, so validate() also falls back to its profile="miappe" default for every dataset — but the core gap is the missing Pydantic constraint layer in validate().)

**Fix:** Make validate() perform the same Pydantic constraint validation as validate_entity() (e.g. have validate()/_validate_nested run create_model_from_spec checks per entity, or route REST/CLI through validate_entity), so constraint violations are caught on every public validation path.

## Confirmed — MEDIUM

### `specs/builder.py:174` — setattr-based mutators bypass Pydantic validation; add_* paths validate, update_*/set_metadata do not
*medium · consistency · group: specs-builder*

set_metadata (lines 174-175), update_field (lines 313-316), and update_rule (lines 374-375) mutate the spec models with plain `setattr(self._spec, key, value)` / `setattr(field, key, value)` / `setattr(rule, key, value)`. The spec models in schema.py (ProfileSpec, FieldSpec, ValidationRuleSpec) use only `ConfigDict(extra="forbid")` and do NOT set `validate_assignment=True`, so assignment performs no type validation or coercion. This means e.g. `set_metadata(version=123)` silently stores an int into a `str` field, and `update_field(entity, fname, constraints={"minimum": 5})` stores a raw dict instead of a `Constraints` model. In contrast, add_entity/add_field/add_rule construct through the model constructor (lines 206, 295, 361) and ARE validated. This is exactly the dual-path divergence where one route validates and the sibling route silently accepts corrupt values. A dict stored for `constraints` later crashes the model factory (it accesses `constraints.pattern`), and a wrong scalar type can persist into emitted YAML.

**Fix:** Either enable `validate_assignment=True` on the spec models, or have the update_*/set_metadata mutators round-trip the value through the field's validator (e.g. `model_validate`/`model_copy(update=...)`) rather than raw setattr, so the update path matches the validated add path.

### `specs/builder.py:258` — delete_entity leaves dangling references to the removed entity, unlike rename_entity
*medium · consistency · group: specs-builder*

delete_entity (lines 258-267) only removes the entity from `self._spec.entities` and clears root_entity if it matched. It does NOT clean up references to the deleted entity that rename_entity (via _update_references, lines 475-494) carefully maintains: nested `field.items` pointing at the deleted name, `field.reference`/`field.parent_ref` targeting it, validation-rule `applies_to`/`reference`, and the auto-created back-reference field (`{name.lower()}_id`) plus the parent `identifier` field that _auto_create_back_reference injected on its behalf. After a delete, the in-memory spec is left structurally inconsistent (fields referencing an undefined entity). validate() will surface the issue via _reference_issues, but the asymmetry with rename_entity (which guarantees integrity) is a silent foot-gun for the UI/MCP callers that mutate then serialize without calling validate().

**Fix:** On delete, either reject when other entities still reference the target, or rewrite/remove the dangling items/reference/parent_ref and validation-rule references, mirroring _update_references.

### `api/client.py:510` — get_children/get_roots derive node labels differently than get_tree (multi-path label divergence)
*medium · consistency · group: api-client*

The three public tree-traversal methods on MetaseedClient produce EntityNode objects with labels computed via two different code paths for the SAME entity.

- get_tree() delegates to self._facade.get_tree() (facade/graph.py get_tree), which computes label = helper.get_label(node.instance) -- the smart priority-based label (title/name/identifier first), as the code comment there states 'Get label using helper's get_label for consistency'. _dict_to_node then preserves that label.
- get_children() and get_roots() instead call _convert_to_entity_node(), which sets label=node.label, i.e. the internal EntityNode.label property (facade/node.py). That property is only a dumb fallback: 'first non-empty string value' truncated to 50 chars, which can pick an arbitrary field (e.g. a description) rather than the entity's title/identifier.

Result: for an entity whose first stored string field is not its title, client.get_tree() shows e.g. the title while client.get_children()/get_roots() show a different string. metaseed-hub (the downstream consumer) calls these public methods to render the same tree, so labels are inconsistent depending on which entry point is used.

    def _convert_to_entity_node(self: Self, node: InternalEntityNode) -> EntityNode:
        return EntityNode(
            id=node.id,
            entity_type=node.entity_type,
            label=node.label,   # <-- dumb fallback, diverges from get_tree's helper.get_label
            ...

**Fix:** Make _convert_to_entity_node compute the label the same way as get_tree/graph.py: resolve the helper via self._facade.get_helper(node.entity_type) and use helper.get_label(node.instance) when helper and node.instance are present, falling back to node.label otherwise (mirroring get_entity_label and _serialize_tree, which already do this).

### `api/rest.py:150` — REST /validate uses engine-only validate() and silently skips type/pattern/enum/range checks (false-negative)
*medium · consistency · group: api-rest-serialization*

The REST endpoint calls `validate_data(request.data, request.entity, request.version)` where `validate_data` is `metaseed.validators.validate`. That function (api.py `validate` -> `_validate_nested` -> `create_engine_for_entity().validate`) runs ONLY the custom rule engine. The engine deliberately returns None for pattern, numeric-range (minimum/maximum) and enum rules with the comment 'Handled by Pydantic ... constraint' (engine.py lines 246-255) and never constructs the Pydantic model. So those checks are simply never executed on this path. In contrast, the canonical `validate_entity` (validators/api.py line 138, used by the client's ValidationMixin in api/validation.py and documented as 'the canonical validation function that both UI and MCP should use') first builds the Pydantic model and reports type/pattern/range/enum violations as 'constraint' errors (api.py lines 189-218) THEN runs the engine. Result: a payload like `{"unique_id": 123}` (wrong type) or a unique_id violating its pattern, or an out-of-range numeric field, returns `{"valid": true}` from POST /validate while the MetaseedClient.validate path correctly flags it. Required-field checks still fire (RequiredFieldsRule), which is why the existing endpoint tests pass and the gap is untested (tests/test_api/test_endpoints.py only covers missing-required and unknown-entity). This is a divergent validation path producing false negatives on a public REST surface.

**Fix:** In rest.py call the canonical `validate_entity(request.data, entity_type=request.entity, version=request.version)` (the same function the client and UI/MCP use) instead of `validate`, so the REST endpoint applies Pydantic type/pattern/enum/range checking plus the rule engine. Add an endpoint test that posts a wrong-typed / pattern-violating field and asserts valid is False.

### `validators/rules.py:604` — UniquenessRule is a guaranteed no-op on the engine validation path (false-negative uniqueness)
*medium · correctness · group: validators-rules*

UniquenessRule detects duplicates only across repeated calls to the same instance, accumulating in self._seen_values. But engine.py (_create_rule_from_spec / _infer_rule_type, lines 204 and 271) constructs a fresh UniquenessRule per record from a profile's `unique_within` spec, and DatasetValidator builds a fresh engine per entity node. As the class docstring itself admits, each invocation therefore sees exactly one value and no duplicate is ever flagged. The result is that a profile author who declares `unique_within: parent`/`global` on any non-identifier field gets validation that silently always passes (a false negative), even though the rule's name and the spec field promise enforcement. Today this is masked only because the sole spec usage (miappe 1.1/1.2 profile.yaml) applies `unique_within: parent` to the `unique_id` field, whose cross-record uniqueness is enforced separately by DatasetValidator/IdRegistry. Any future `unique_within` on a non-id field would silently never fire.

**Fix:** Either (a) have the engine/DatasetValidator reuse a single UniquenessRule instance across the sibling collection (calling reset() between parent scopes), or (b) route all `unique_within` specs through the IdRegistry/dataset-level uniqueness check and drop the per-record UniquenessRule wiring, so the spec construct cannot silently no-op. At minimum, fail fast or warn when a `unique_within` rule targets a non-identifier field.

### `validators/dataset.py:215` — Tree traversal descends only into list fields, silently skipping single nested `entity` fields
*medium · correctness · group: validators-engine-dataset*

`_traverse_entity_tree` only recurses when `f.type.value == "list" and f.items`:

```python
for f in spec.fields:
    if f.type.value == "list" and f.items:
        ...
```

It never handles `f.type.value == "entity"` (a single nested entity that also carries `items`). Such fields exist in every profile, e.g. MIAPPE 1.2 `study_location` (type: entity, items: Location) and `material_source` (type: entity, items: MaterialSource), and factory.py maps `FieldType.ENTITY` to a nested model (and `_coerce_string_to_entity` turns a string into a nested dict), so the serialized value is a nested object. Because the traversal skips these, every visitor that walks the tree silently ignores nested single entities: their `unique_id`s are never registered (so references to them are unresolvable), their required/pattern rules are never run via `_validate_entity`, their references are never checked, and they are not counted. This is a false-negative validation gap across all profiles.

**Fix:** Also branch on `f.type.value == "entity"` with `f.items`: when the value at `data.get(f.name)` is a dict, recurse once into it with `to_snake_case(f.items)`.

### `validators/dataset.py:243` — Reference integrity registers only `unique_id`, ignoring the reference target field
*medium · correctness · group: validators-engine-dataset*

`_collect_ids` registers exactly one field per entity:

```python
def register_id(d, etype, _path):
    if "unique_id" in d:
        self._registry.register(etype, d["unique_id"])
```

but `_validate_references` resolves a reference `ref_type` of the form `Entity.field` and looks up the value against that registry, discarding the field part:

```python
ref_entity = to_snake_case(ref_type.split(".")[0])
if not self._registry.exists(ref_entity, ref_value):
```

This only works when the reference target field is `unique_id`. Profile specs declare many references to other key fields, e.g. ISA `Study.identifier`, `Investigation.identifier`, ENA `Run.alias`, `Sample.alias`, `Protocol.name`, `Assay.filename`. For those profiles the registry holds `unique_id` values (or nothing, if the entity is keyed by `identifier`/`alias` and has no `unique_id`), so valid references are reported as `Reference not found`. Reference integrity is therefore wrong for every non-`unique_id`-keyed profile (ISA, ENA, etc.). MIAPPE happens to work only because its references all target `unique_id`.

**Fix:** Register the value of the field actually referenced. Collect, per entity type, the set of values of every field that appears as a reference target (the part after the dot in some `f.reference`), or look up `ref_value` against the registered set for the specific target field rather than assuming `unique_id`.

### `validators/dataset.py:309` — Dataset path skips Pydantic constraint validation that the single-entity path performs
*medium · consistency · group: validators-engine-dataset*

`DatasetValidator._validate_entity` validates a node only through the rule engine:

```python
engine = create_engine_for_entity(etype, self.version, self.profile)
for error in engine.validate(d):
    ...
```

The engine deliberately returns `None` for pattern, numeric-range, and enum rules because they are documented as "handled by Pydantic constraints" (engine.py `_infer_rule_type`, lines 246-255). But the dataset path never instantiates the generated Pydantic model, unlike the entity-level API path `validators/api.py:validate_entity` which calls `create_model_from_spec(entity_spec)` and runs `model_class(**simple_data)` before the engine. Consequently, type errors, regex `pattern` constraints, `ge/le` numeric ranges, and `Literal`/enum constraints are silently never enforced when validating a whole dataset (the path used by the CLI `validate` command and MCP `validate_dataset`), while the same data validated one entity at a time would be rejected. This is a dual-path consistency gap that weakens dataset validation to a false negative.

**Fix:** Run the generated model (`create_model_from_spec` + instantiate with simple fields, as `api.validate_entity` does) inside `_validate_entity`, or document explicitly that dataset validation is structural-only; the current state where the engine assumes Pydantic runs but the dataset path never invokes it is the trap.

### `validators/api.py:372` — validate_entity_with_report double-reports missing required fields
*medium · consistency · group: validators-api*

validate_entity() deliberately skips Pydantic "missing" errors to avoid duplicating the engine's RequiredFieldsRule:

    if err["type"] == "missing":
        continue  # reported by the engine's RequiredFieldsRule below

validate_entity_with_report() omits this guard. Its except branch records EVERY Pydantic error, including "missing", as a failed "constraint" check:

    for err in e.errors():
        field_path = ".".join(str(loc) for loc in err["loc"])
        failed_fields.add(field_path)
        checks.append(ValidationCheck(field=field_path, check="constraint", passed=False, message=err["msg"]))

Then line 406 calls engine.validate_with_report(data), and RequiredFieldsRule (rules.py:152) reports the same absent field again as a failed "required_fields" check. A single missing required field therefore produces two distinct FAIL entries in the report (one check="constraint" "Field required", one check="required_fields" "Field 'X' is required"). This report function is the one the UI validation route and the MCP validation tools consume, so the duplication surfaces to users. The two sibling functions diverge in how they de-duplicate the engine vs. Pydantic required-field overlap.

**Fix:** Mirror validate_entity(): in the except branch of validate_entity_with_report, skip err["type"] == "missing" so only the engine's RequiredFieldsRule reports absent required fields.

### `repositories/file.py:299` — FileEntityRepository serializes entity data without mode="json", diverging from MemoryEntityRepository
*medium · consistency · group: repositories-a*

FileEntityRepository stores entity data via `instance.model_dump(exclude_none=True)` (lines 299 and 349), WITHOUT `mode="json"`. MemoryEntityRepository uses `model_dump(mode="json", exclude_none=True)` everywhere (memory.py lines 46, 72, 156, 212, 261, 266), and api/base.py also uses mode="json". The factory maps the `uri` field type to pydantic `AnyUrl`, `date` to `datetime.date`, and `datetime` to `datetime.datetime` (factory.py lines 289-291). As a result, an entity with a uri/date/datetime field, when fetched via FileEntityRepository.get_entity()/list_entities(), carries native Python objects (AnyUrl, date, datetime) in EntityData.data, whereas the same entity via MemoryEntityRepository carries JSON-native strings. This is a dual-path serialization-shape divergence: consumers (the docstring explicitly targets the UI, MCP, and metaseed-hub) that index entity.data and expect JSON-native strings will get Url/date objects from the file backend. It also makes the file backend internally inconsistent across a save+reload cycle (in-session data holds AnyUrl/date objects; after _save -> json.dump(default=str) -> _load, the same fields come back as strings).

**Fix:** Use `instance.model_dump(mode="json", exclude_none=True)` in create_entity (line 299) and update_entity (line 349) so the file backend's in-memory EntityData.data matches the memory backend and the persisted JSON shape.

### `repositories/file.py:192` — Entities with a dangling parent_id are silently dropped from the tree and lost on next save
*medium · correctness · group: repositories-a*

In _build_hierarchy, an entity whose `parent_id` points to a non-existent id is neither attached to a parent (parent not in entities, line 194) nor collected as a root (the `if not entity.parent_id` guard at line 199 is false). It remains in self._entities (so list_entities/get_entity still surface it) but is absent from self._tree. _save serializes by walking self._tree only (lines 225-226), so on the next mutating operation (create/update/delete -> _save) the orphaned entity is permanently dropped from the persisted file even though list_entities reported it. This is silent data loss and an inconsistency between what list_entities returns (self._entities) and what gets persisted (self._tree).

**Fix:** When building the hierarchy, treat entities whose parent_id is unresolved as roots (append to tree) instead of discarding them, or serialize from self._entities with explicit parent_id rather than walking the tree, so list/persist stay consistent.

### `ui/datasets.py:167` — import_dataset drops catalog_metadata, diverging from the filesystem load path (round-trip data loss)
*medium · correctness · group: ui-managers*

import_dataset() builds DatasetData without ever reading payload.get("catalog_metadata"):

    data = DatasetData(
        name=payload.get("name", ""),
        profile=profile,
        version=payload.get("version") or "",
        entities=entities,
        modified=payload.get("modified", ""),
    )

so catalog_metadata defaults to None. The filesystem repository writes catalog_metadata into the saved JSON (filesystem_dataset.py save, lines 110-111) and reconstructs it on load (lines 144-153 -> CatalogMetadata(**catalog_metadata)). The import_dataset docstring claims the accepted JSON "shape matches a saved dataset file", yet uploading a previously-saved dataset file via this path silently discards title/description/publisher/license/keywords/etc. Worse, _restore_state_from_data() then unconditionally assigns self._state.catalog_metadata = data.catalog_metadata (dataset_manager.py line 123), i.e. None, wiping any catalog metadata already in state. If the user subsequently auto-saves, the loss becomes permanent. This is a dual-path consistency gap: load_dataset (repo path) preserves catalog_metadata, import_dataset (upload path) destroys it.

**Fix:** Parse catalog_metadata from the payload in import_dataset (e.g. CatalogMetadata(**payload["catalog_metadata"]) when present) and pass it into DatasetData, mirroring FilesystemDatasetRepository.load. Add a test asserting catalog_metadata survives a save -> read-file -> import round trip.

### `ui/state.py:212` — get_or_create_facade ignores version mismatch, can serve a stale-version facade
*medium · correctness · group: ui-state-spec*

get_or_create_facade only recreates the facade when the profile changes:

    if self.facade is None or self.facade.profile.lower() != self.profile.lower():
        self.facade = ProfileFacade(self.profile, self.version)
        self._invalidate_cache()
    return self.facade

The method's name and docstring ("Get existing facade or create new one") imply it reflects the current AppState. But if `self.version` is changed while `self.profile` stays the same, the previously cached facade (built with the old version) is returned unchanged. Since the facade caches version-specific generated Pydantic models, this would silently produce/validate entities against the wrong profile version. Every current caller (routes/examples.py, routes/forms.py, routes/core.py, dataset_manager.py) works around this by manually setting `state.facade = None` before changing version, so no bug manifests today — but the safety of the whole UI state layer rests on that undocumented convention. A direct `state.version = 'x'` followed by `get_or_create_facade()` corrupts model resolution. Note a naive `self.facade.version != self.version` check is wrong because `self.version` may be None ('latest') while the facade resolves a concrete version; the fix must compare against the resolved version (or the method must document that callers MUST null the facade on version change).

**Fix:** Either recreate the facade when the resolved version differs (compare against facade.version after resolving None->latest), or document explicitly that callers must set facade=None when changing version; do not leave it to convention.

### `cli/app.py:150` — validate command does not handle SpecLoadError, unlike sibling commands
*medium · consistency · group: cli*

The `validate` command calls `errors = validate_data(data, entity, version, profile=profile)` (lines 150-157) with no try/except. `validate_data` -> `_validate_nested` -> `create_engine_for_entity` raises `SpecLoadError` (engine.py:456 `raise SpecLoadError(f"Entity not found: {entity} ...")`) whenever the entity does not exist in the resolved profile. Every other entity-resolving command in this file wraps that call: `template` (lines 179-184), `convert` (lines 250-254), and `entities` (lines 299-304) all catch `SpecLoadError`, call `echo_error`, and `raise typer.Exit(ExitCode.CONFIG_ERROR)`. As written, `metaseed validate file.yaml -p darwin-core` (or any profile lacking an `investigation` entity) prints a raw Python traceback and exits with code 1 instead of a clean error message. This is reachable in normal use because of the default entity issue below.

**Fix:** Wrap the `validate_data` call in try/except SpecLoadError mirroring the other commands (echo_error(str(e)); raise typer.Exit(ExitCode.CONFIG_ERROR)).

### `services/ontology.py:714` — get_term/_construct_iri only resolves OBO-foundry ontologies; non-OBO terms become false-negative validations
*medium · correctness · group: services-ontology*

_construct_iri always builds an OBO PURL: `f"http://purl.obolibrary.org/obo/{normalized}"`. For ontologies whose canonical IRI is NOT under purl.obolibrary.org/obo (e.g. EFO -> http://www.ebi.ac.uk/efo/EFO_..., ORDO, NCIT with a different base), the constructed URL does not exist in OLS4 and the term lookup returns HTTP 404. get_term then caches a negative result and returns None. validate_term/validate_term_sync only fail-open on OntologyServiceError (network/5xx), NOT on 404 (lines 658-667 / 688-697), so a genuinely-existing non-OBO term is reported as `(False, "Ontology term '<id>' not found in OLS4")`. This is a silent false-negative validation for a whole class of ontologies. Note the same OBO-only assumption is mirrored in agent/mcp/tools/ontology.py (line 149), so it is a system-wide assumption rather than a local divergence, but it still corrupts validation for non-OBO terms.

**Fix:** Resolve the IRI via the OLS4 search/term-by-id endpoint (which accepts obo_id without a hand-built IRI) or branch on known non-OBO ontology bases instead of unconditionally using the obo PURL; alternatively treat a 404 from a hand-constructed IRI as inconclusive for non-OBO prefixes.

## Verified by hand (verifier hit session limit)

### `facade/store.py:368` — to_dict parent links rely on unique_id/alias; _parent_id never persisted (latent reload fragility)
*medium · consistency*

Downgraded from high: ISA/MIAPPE round-trip correctly via the reference-field fallback linker (verified empirically); the primary _parent_unique_id is None for any profile whose identifier field is not unique_id/alias, so structure relies entirely on fallbacks. Fix: also persist _parent_id=parent_node.id in serialize_node.

### `agent/core.py:365` — validate_instance treats a required field explicitly set to None as valid (false-negative)
*medium · correctness*

Confirmed: only checks `field.name not in data`. Fix: `if field.required and (field.name not in data or data[field.name] is None):`.

### `cli/app.py:124` — validate/convert hardcode default entity 'investigation', breaking non-MIAPPE profiles
*medium · consistency*

Confirmed: default to the resolved profile's root_entity when --entity is omitted.

### `ui/routes/dcat.py:136` — Saving DCAT form metadata drops issued/contact/landing_page/themes (round-trip loss)
*medium · correctness*

Confirmed: use dataclasses.replace on the existing CatalogMetadata instead of rebuilding from 5 fields.

### `agent/mcp/manager.py:122` — MCP subprocess started with unread PIPE stdout/stderr can deadlock
*medium · correctness*

Confirmed: redirect long-lived child stdout/stderr to a file/DEVNULL or drain on a thread; keep PIPE only for startup-failure capture.

## Confirmed — LOW

### `facade/helper.py:195` — get_label docstring describes a label algorithm that does not exist (aspirational)
*low · docstring · group: facade-helper-profiles*

EntityHelper.get_label claims it 'Looks for common identifier fields in order of preference: - title (for Investigation, Study) - name (for Person, Factor) - first_name + last_name (for Person) - unique_id / identifier - Falls back to first non-empty string field from spec'. The actual implementation simply delegates to derive_label(self._name, data, spec=self._spec). derive_label (repositories/helpers.py:75) ignores all of that and uses only the FIRST field of the spec by convention ('first_field = spec.fields[0].name', truncated to 50 chars, else 'New {entity_type}'). None of the documented title/name/first_name/unique_id preference logic is implemented anywhere, so the docstring is aspirational and misleads callers about how labels are derived. (Secondary minor inconsistency: the non-model/non-dict fallback here returns f"{self._name}" whereas derive_label's fallback returns f"New {entity_type}".)

**Fix:** Rewrite the docstring to match derive_label's actual behavior ('the first field defined in the entity spec is used as the label, truncated to 50 chars'), or implement the documented preference order in derive_label if that ordering is actually desired.

## Appendix — unverified low-confidence notes
- `specs/loader.py:190` [low] Unreachable except yaml.YAMLError in load()
- `specs/loader.py:221` [low] MIAPPE-specific default version "1.2" hardcoded in generic multi-profile loader
- `specs/builder.py:54` [low] validate_field_name advertises snake_case but permits hyphens
- `specs/builder.py:353` [low] add_field/add_rule raise pydantic ValidationError for bad attrs while update_* raise ValueError
- `models/factory.py:230` [low] EntityBaseModel docstring claims a 'JSON serialization mode' that is not configured
- `models/factory.py:450` [low] entity field without `items` is treated as nested by schema but not by the factory
- `facade/core.py:134` [low] _create_instance resolves the helper via getattr instead of _get_helper, making the unknown-entity error type path-dependent
- `facade/node.py:38` [low] EntityNode.label docstring claims 'first field value' but returns the first non-empty string value
- `facade/node.py:25` [low] EntityNode docstring Attributes section omits the `children` field
- `validators/dataset.py:176` [low] `_detect_entity_type` assumes the loaded document is a dict; list/scalar YAML crashes uncaught
- `repositories/memory.py:286` [low] Unused backwards-compatibility alias AppStateAdapter
- `repositories/file.py:249` [low] get_entity/list_entities return internal mutable EntityData objects, unlike the memory backend
- `facade/graph.py:217` [low] get_identifier called without a helper always returns None, dropping graph edges for embedded dict references
- `repositories/filesystem_dataset.py:78` [low] list() sorts by a `modified` string that mixes ISO timestamps and raw mtime floats, giving wrong order for files lacking a modified field
- `cli/migrate_specs.py:0` [low] Orphaned, already-completed one-off spec migration script
- `cli/output.py:104` [low] CheckOutput prints warnings even in --quiet mode on failure
- `services/ontology.py:231` [low] cache_ttl=0 / rate_limit=0 silently overridden by env/default via `or`
- `services/ontology.py:353` [low] search swallows all HTTP errors to [] while get_term raises OntologyServiceError on non-404
- `dcat/__init__.py:5` [low] Package docstring references a non-existent metaseed.dcat.mapping module
- `agent/mcp/tools/profiles.py:291` [low] get_example_dataset can emit dangling cross-references when a reference targets a non-identifier field
- `agent/mcp/tools/extraction.py:69` [low] parse_source_file catches only ValueError while sibling tools catch broadly
- `forms/__init__.py:227` [low] Duplicate __all__ definition
- `profiles/factory.py:62` [low] get_latest_version assumes lexicographic version order, mis-picks multi-digit versions
