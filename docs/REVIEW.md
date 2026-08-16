# Codebase review — metaseed, 260816

> **Remediation complete (260817).** All 123 confirmed findings are fixed —
> 12 high, 61 medium, 50 low — across the commits between v0.40.0 and this
> note, each with a test proven red against the unfixed code. Deliberately
> not done: reconciling the two SEEK role lists (data-affecting; the
> discrepancy is documented in `metaseed.seek.roles`), deleting
> `metaseed.dcat.publication` (a documented downstream seam, now gated by
> `tests/test_dcat/test_publication_is_a_supported_seam.py`), and enforcing
> the single-identifier rule at `add_field` (the spec-builder flow is
> add-then-validate by contract). The appendix's 141 unverified notes remain
> leads, not conclusions.

Per-file review of every source file under `src/metaseed` (210 files reviewed across 17 module groups), with an adversarial verification pass on every high and medium finding. Findings below are what survived that pass; 32 were refuted and are listed at the end.

## Baseline gates

Every gate the project defines passes. Nothing in this document is something the gates can see.

| Gate | Command | Result |
| --- | --- | --- |
| Lint | `uv run ruff check src tests` | pass |
| Dead code | `vulture src/ --min-confidence=80` | pass (no hits at the gate threshold) |
| Types | `uv run python -m mypy src/metaseed` | pass, 196 files |
| Tests | `pytest -n auto -m "not network and not selenium"` | 3396 passed, 4 skipped, 1 xpassed |
| File size | 1000 LOC limit | `validators/dataset.py` at 1003 lines, over by 3 |

One test is marked expected-to-fail but passes (`xpassed`). Either the fix landed and the marker was never removed, or the marker was never right; it is not a gate failure, which is why it survives.

## Summary

- 296 raw findings; **123 confirmed**, 32 refuted, 141 unverified (low severity, not put through verification).
- Confirmed by corrected severity: **12 high**, 61 medium, 50 low.
- By category: correctness 63, design 21, consistency 17, dead-code 11, naming 4, docstring 4, typing 3.

### Recurring themes

**Silent data loss on the write and export paths.** The largest cluster among the highs, and the same shape each time: an operation reports success while data goes missing. `delete_entity` removes a node but leaves the embedded child object in the parent, so deleted records reappear in every export; `load_nested` materialises each child twice, embedded and as its own node; a failed load leaves the repository empty and the next mutation writes that emptiness over the file; the FDS exporter drops an entire subtree when it meets an unmapped entity; the ISA-Tab writer drops child Characteristic and FactorValue entities from the study table.

**An outage reported as invalid data.** `services/terms.py` maps an OLS failure to `NOT_FOUND` — a term the user entered correctly is reported as wrong because somebody else's service was down. This is the precise failure the three-outcome term check exists to prevent, and CLAUDE.md names it as a rule.

**Re-discovery where a collaborator should be injected.** `api/validation.py` re-resolves the spec by name, so a client built with `from_spec()` or `from_yaml()` can never validate — the object it was composed with is discarded in favour of a lookup. `forms/__init__.py` re-derives the parent-reference field from a lowercase string heuristic instead of the profile's declared `reference_fields`, and gets multi-word entity types wrong (`ObservationUnit` yields `observationunit_id`, not `observation_unit_id`).

**Divergent second copies of a decision the spec already declares.** Related to ADR 005's argument: where a rule has two homes they drift, and the parent-reference heuristic above is exactly that pattern surviving outside `facade/linking.py`.

**Routes that answer success without doing the work.** `POST /api/dcat/metadata` returns "saved" and persists nothing; the spec-builder rule error path drops `where_keep`/`when_keep` and destroys a nested predicate on the next save.

## High (12)

### `src/metaseed/api/validation.py:89` — validate() re-discovers the spec by name, so from_spec()/from_yaml() clients can never validate

*correctness · api-brapi*

`ValidationMixin.validate()` and `validate_entity()` call `metaseed.validators.validate_entity(data, entity_type=..., profile=self._facade.profile, version=self._facade.version)`. That function does NOT receive the spec the facade already holds; it re-resolves it from disk via `SpecLoader(profile=profile).load_entity(entity_type, version)` (src/metaseed/validators/api.py:257-267). For a client built by `MetaseedClient.from_spec()` or `from_yaml()` — the documented way to use a custom or dynamically-generated schema — no such profile file exists, so every entity is reported as an error.

Proven empirically against this working tree:

    spec = {"version": "1.0", "name": "custom_review_probe",
            "entities": {"Sample": {"fields": [
                {"name": "unique_id", "type": "string", "required": True},
                {"name": "title", "type": "string", "required": True}]}},
            "root_entity": "Sample"}
    c = MetaseedClient.from_spec(spec)
    c.create_entity("Sample", {"unique_id": "S1", "title": "t"})
    c.validate()

yields:

    valid: False
    ValidationIssue(field='Sample',
                    message="Unknown entity type: Sample - Profile not found: custom_review_probe v1.0",
                    rule='error', ...)

A perfectly valid entity is reported invalid, and a genuinely invalid one would be indistinguishable. This is also the CLAUDE.md 'depend on injected interfaces, never on discovered implementations' rule: the validation layer reaches out to a global loader to re-find a collaborator the caller already supplied.

**Fix:** Pass the loaded spec (or an injected validator built from `self._facade`) into the validation call instead of re-resolving by (profile, version) name — e.g. add a spec/entity-spec parameter to `metaseed.validators.validate_entity` and have `ValidationMixin` supply `self._facade.get_helper(node.entity_type).spec`. Add a red-first test that `MetaseedClient.from_spec(...).validate()` returns `valid=True` for a complete entity, and a matching one for `from_yaml`.

### `src/metaseed/facade/documents.py:136` — load_nested duplicates every child: embedded in the parent and again as its own node

*correctness · facade*

`_load_children` calls `self.sink.add_entity(child_type, item, parent_id=parent_id, ...)` but never removes `field_name` from `parent_data`, and `DocumentLoader.load` passes the whole `document` to `add_entity` for the root. The parent instance therefore keeps the full embedded children while the same entities also exist as separate nodes.

```python
f.load_nested({"unique_id": "INV-1", "title": "I",
               "studies": [{"unique_id": "ST-1", "title": "S"}]})
for e in f.to_dict(): print(e)
# Investigation {'unique_id': 'INV-1', 'studies': [{'unique_id': 'ST-1', 'title': 'S'}]}
# Study        {'unique_id': 'ST-1', '_parent_unique_id': 'INV-1'}
```

Every entity below the root is stored twice. This is the load path used by `ProfileFacade.load_yaml` for all shipped examples and by `ui/routes/examples.py`, so any save or export after loading an example emits duplicated data, and it is what makes the delete bug above observable.

**Fix:** Replace the walked containment field on the parent with the child references the linking module produces (or strip it), so the store holds one representation. Add a test asserting `to_dict()` after `load_nested` contains each entity exactly once.

### `src/metaseed/facade/store.py:393` — delete_entity leaves an embedded child object in the parent, so deleted records survive every export

*correctness · facade*

`_remove_reference_from_parent` builds `child_refs` from the child's identifier values and `unlinked_reference_value` filters with `str(v) not in child_refs`. When the parent's nested field holds embedded child OBJECTS (dicts) rather than identifier strings — which is exactly what `load_nested`/`load_yaml` produces for every shipped example — `str(dict)` never matches and nothing is removed.

Reproduced:

```python
f.load_nested({"unique_id": "INV-1", "title": "I",
               "studies": [{"unique_id": "ST-1", "title": "S"}]})
f.delete_entity(<the Study node id>)
f.to_dict()
# Investigation {'unique_id': 'INV-1', 'studies': [{'unique_id': 'ST-1', 'title': 'S'}]}
```

The Study node is gone but the full record remains inside the Investigation and is re-emitted by `to_dict`, by the exporters and by any save. The docstring's premise ("Creation writes it into the parent's nested reference field") is also false for `EntityStore` — `add_entity` never writes it; only the repositories do.

**Fix:** In `unlinked_reference_value` (the ADR 005 owner), match a list member either by its scalar value or, when it is a mapping, by any of its identifier fields. Correct the `_remove_reference_from_parent` docstring to say which component writes the reference. Cover with a delete-after-`load_nested` test.

### `src/metaseed/isatab/__init__.py:189` — Child Characteristic/FactorValue entities are silently dropped from the study table

*correctness · exporters*

`_sample_qualifiers` reads only the sample dict's embedded `characteristics` / `factor_values` lists. The MetaboLights importer creates these as *child nodes* (`metabolights/mapper.py:117-139`, `create_entity("Characteristic", ..., parent_id=sample_entity.id)`), and the parent's list field serializes empty. Reproduced: importing a Sample plus child Characteristic(category=Age) and FactorValue(factor_name=Dose) and calling `to_isatab` yields `Source Name\tSample Name\tCharacteristics[Organism]` only - the serialized Sample dict is `{'name': 'SAMP1', 'organism': ..., 'characteristics': [], 'factor_values': [], ...}`. So an import-then-export round trip loses every characteristic except Organism/Organism part and every factor value. `metabolights/export.py:65-77` handles exactly this embedded-vs-child duality for Metabolites via `_metabolite_children_by_assay`; the sample path was never given the same treatment.

**Fix:** Build a child-entity index the same way `_direct_parent_map` already does in this file, and in `_sample_qualifiers` fall back to child `Characteristic`/`FactorValue` nodes when the embedded lists are empty. Add a test that imports child entities and asserts the columns survive export.

### `src/metaseed/isatab/__init__.py:212` — _sample_qualifiers reads a field name the FactorValue entity does not declare

*correctness · exporters*

The generic loop reads `item.get("category", "")` for both `characteristics` and `factor_values`. The `metabolights` profile declares `Characteristic` with `category`/`value`/`unit` but `FactorValue` with `factor_name`/`value`/`unit` (specs/metabolights/1.0/profile.yaml:441-458). Verified: `_sample_qualifiers({"name":"S1","factor_values":[{"factor_name":"Dose","value":"high"}]})` returns `('Factor Value', '', 'high', '')` - an anonymous `Factor Value[]` column with no factor name. The same loop reads `item.get("term_accession")`, which neither Characteristic nor FactorValue declares, so the accession is always empty for generic qualifiers. The existing test tests/test_metabolights/test_export.py:186 authors `factor_values=[{"category": "Dose", ...}]` with `skip_validation=True`, so it green-lights a shape the profile forbids and cannot catch this.

**Fix:** Read `item.get("factor_name") or item.get("category")` for the Factor Value branch (or drive the key from the declared entity spec), and fix the test fixture to use the profile's `factor_name` so it fails against the current code.

### `src/metaseed/repositories/file.py:149` — A failed load leaves the repository empty and the next mutation overwrites the file with an empty dataset

*correctness · repositories*

`_load` catches `(json.JSONDecodeError, OSError)` and only logs a warning: `except (json.JSONDecodeError, OSError) as e: logger.warning("Failed to load dataset: %s", e)`. `self._entities`/`self._tree` stay empty, and the repository is indistinguishable from one opened on a nonexistent file. The first `create_entity`/`update_entity`/`delete_entity` then calls `_save`, which serializes the empty `_tree` over the existing file. A transient read failure (permission, EINTR, a half-written file) therefore destroys the user's dataset. This is the case the project rule covers explicitly: a read failure must report "not checked", never be treated as "there is no data".

**Fix:** Record the load failure on the instance (e.g. `self._load_failed = True`) and make `_save` refuse to write — raising or logging an error — until an explicit reload succeeds; alternatively let `__init__` propagate the exception so the caller learns the dataset could not be read.

### `src/metaseed/repositories/file.py:293` — Case-insensitively resolved entity type is discarded; the raw caller string is stored and then compared case-sensitively

*correctness · repositories*

`facade.require_helper(entity_type)` deliberately resolves entity types case-insensitively (`core.py:558-569`), but neither repository adopts the canonical name it resolved. The raw caller string is used for the parent-child check (`file.py:310`: `if entity_type not in valid_child_types`), for storage (`file.py:336` `entity_type=entity_type`; `memory.py:144` `add_node(entity_type, ...)`) and, transitively, for every later reference lookup. `valid_child_types` comes from `helper.child_fields.values()`, which holds canonical spec names, and `find_parent_ref_field` / `linking.target_reference_field` both compare with `==`. So `create_entity("study", ...)` under an Investigation is accepted by `require_helper` and then rejected with "Invalid parent: Investigation cannot contain study"; and where the *parent* was created with a non-canonical case, `find_parent_ref_field(helper, parent.entity_type)` and `target_reference_field(parent_helper, child_type)` both miss, so the child's parent reference is never auto-filled and the parent's nested reference field is never updated — a silently mis-linked tree rather than an error. Identical code in `memory.py:108-129`.

**Fix:** Immediately after `helper = facade.require_helper(entity_type)`, rebind `entity_type = helper.name` (the public canonical name) and use that value for validation, storage and all reference lookups, in both `file.py` and `memory.py`.

### `src/metaseed/seek/fairds.py:296` — Descending past an unmapped entity is a no-op: the entire subtree is silently dropped from the FDS export

*correctness · seek*

In `to_fair_data_station_rdf.walk`, the child loop clearly intends to skip an entity with no JERM class and keep exporting its descendants:

    for child in node.children:
        child_seg = segment(child)
        if child_seg is None:
            walk(child, path)   # intended: descend past the unmapped child
            continue

But `walk` itself bails out at the top (lines 250-253):

    mapping = resolve(node.entity_type)
    seg = segment(node)
    if mapping is None or seg is None:
        return

`segment` returns `None` exactly when `resolve` returns `None`, so `walk(child, path)` returns immediately and the recursion never happens. Every descendant of an unmapped entity is dropped without any report — `unmapped_entities` warns only about the unmapped entity itself, not about the content lost beneath it.

Verified on a 3-level profile Investigation -> Treatment (unmapped) -> Sample:

    SEEK export maps no JERM class for Treatment; it will not be exported.
    Sample in output: False

Only `fair:inv_I1` is emitted; the Sample vanishes. `metaseed.seek.sync.walk` does the opposite (it always recurses into children regardless of placement), so the two exporters disagree on the same profile.

**Fix:** Split the guard: keep a `mapping is None` check that skips *emitting* the node but still recurses into `node.children` with the unchanged `parent_path`, or hoist the descent into the caller (e.g. `for grandchild in child.children: walk(grandchild, path)`). Add a regression test asserting a Sample nested under an unmapped intermediate entity still appears in the Turtle, and extend the `unmapped_entities` warning to name how many descendant nodes are affected.

### `src/metaseed/services/terms.py:160` — An OLS outage is reported as NOT_FOUND (invalid data), which is the exact failure this subsystem exists to prevent

*correctness · services*

`OntologyService.get_term_sync` deliberately raises `OntologyServiceError` on transport/5xx failure so callers can "fail open rather than treat an outage as proof of absence" (ontology.py:423-426). `TermRouter.get_term_sync` then erases that distinction:

```python
try:
    term: object | None = source.get_term_sync(term_id)
except Exception:
    logger.warning(...)
    continue
...
return None
```

The protocol has no way to say "could not ask", so an outage and a genuine absence both arrive at `check_term` as `None`. `check_term` (term_check.py:272-288) then tries to compensate by asking `has_ontology_sync(prefix)` — but that is a *different* OLS endpoint (`/ontologies/{id}`) with its own 600 s cache. Concretely: `check_term("TO:0000387", ["to"])` with OLS reachable for `/ontologies/to` (or that answer already cached True from a previous call) but failing on `/ontologies/to/terms/...` returns `Outcome.NOT_FOUND` with the message "'TO:0000387' is not a term in to." — `is_problem` is True, and every ontology value in the dataset is flagged as invalid because of someone else's downtime. Note that `TermRouter._owns` already calls `has_ontology_sync` before the term lookup on the same request, so the True answer is reliably present. tests/test_services/test_terms.py only exercises `_Remote(down=True)`, whose `has_ontology_sync` also returns `None`, so this path is untested.

**Fix:** Give `TermSource.get_term_sync` a third outcome (e.g. raise a shared `TermSourceUnavailable`, or return a sentinel) and let `TermRouter` propagate "could not ask" distinctly from `None`, so `check_term` can return `NOT_CHECKED`. Add a red-first test where a source raises on `get_term_sync` while answering `has_ontology_sync` with `True`, and assert `Outcome.NOT_CHECKED`.

### `src/metaseed/ui/routes/dcat.py:111` — POST /api/dcat/metadata answers "saved" but never persists the metadata

*correctness · ui-routes*

`set_dcat_metadata` assigns `state.catalog_metadata = CatalogMetadata(...)` and returns `JSONResponse({"status": "saved"})`, but it never calls `auto_save` (or any manager save), unlike every other mutating route (crud.py:115, 212, 274 all call `auto_save(state, getattr(request.app.state, "dataset_factory", None))`). `DatasetManager` does round-trip `catalog_metadata` (dataset_manager.py:102/131) and `FilesystemDatasetRepository` stores it, so the data is lost only because nothing triggers a write. Reproduced with TestClient: GET /load-example/miappe/1.1, then POST /api/dcat/metadata with title/description/publisher/keywords returns 200 {"status": "saved"}; the saved dataset file (~/.local/share/metaseed/datasets/miappe-1_1-example.json) contains no `catalog_metadata` key. The title/publisher/license a user types for a Darwin Core dataset - exactly the profiles that cannot derive it - is gone after a reload, while the response claimed success.

**Fix:** Take `request: Request` in the handler and call `auto_save(state, getattr(request.app.state, "dataset_factory", None))` after assigning `state.catalog_metadata`, and only then report "saved". Add a route test that posts metadata and asserts it survives a reload of the dataset.

### `src/metaseed/ui/spec_builder/routes_rules.py:335` — Error path drops where_keep/when_keep and silently destroys a nested predicate on the next save

*correctness · ui-services-and-spec-builder*

`_rule_form_response` renders the read-only "kept as written" branch only when `where_rows`/`when_rows` is `None` (template `validation_rule_form.html:214` / `:100`), and that branch is what emits `<input type="hidden" name="where_keep" value="1">`. On the error path `update_validation_rule` *unconditionally* passes `typed_rows=(where_join, [...])` and `typed_when=(when_join, [...])`:

```python
except ValueError as exc:
    return _rule_form_response(
        ..., typed_rows=(where_join, [ ... zip(where_field, where_op, where_value) ]),
              typed_when=(when_join, [ ... ]),
    )
```

For a rule whose stored `where` nests deeper than rows can express, the POST carried `where_keep=1` and *no* `where_field` inputs, so `typed_rows` becomes `(join, [])` — a non-`None` tuple. `editable` at line 187 is therefore truthy, `where_rows` is rendered as `[]`, the `where_keep` hidden input disappears, and the read-only display is replaced by an empty editable row list. The user fixes the reported error and saves again; now `where_keep` is empty, so line 107-110 runs `predicate_from_rows(join, [], [], [])` which returns `None`, and `rule.where = None`. The nested predicate is destroyed with no message.

Reachable with any error `build_updated_rule` can raise on a rule with a nested predicate — e.g. typing a non-numeric "Min Items" (`int(self.min_items)`, line 101). No test covers this (only `test_spec_builder_predicates.py:206` exercises the success path with `where_keep="1"`).

**Fix:** Only pass `typed_rows` when `where_keep` is falsy, and `typed_when` when `when_keep` is falsy; otherwise leave them `None` so `rows_from_predicate` re-derives `None` and the read-only branch (with its hidden `where_keep`) renders again.

### `src/metaseed/validators/dataset.py:952` — Parent-scope uniqueness keys are shared across files, reporting distinct parents as duplicates

*correctness · validators*

`validate_directory` shares one `uniqueness_seen` set across every file (line 952) so that global-scope rules catch cross-file duplicates. But `_validate_uniqueness` builds the parent-scope key from the *file-relative* path only:

```python
scope_key = "" if rule.scope == "global" else re.sub(r"\[\d+\]$", "", p)
```

Two different investigation files each containing `studies[0]` both produce `scope_key == "studies"`, so two studies under genuinely different parents collide. With MIAPPE's `unique_within: parent` on `unique_id`, validating a directory of per-investigation files reports every repeated child identifier as "Value 'STU001' is not unique for 'unique_id' within parent scope", even though each is unique within its own parent. Single-file validation is unaffected (fresh `set()` at line 860), so the defect only appears on the directory path.

**Fix:** Include the file identity in the scope key for non-global scopes (e.g. pass the file path into `_validate_uniqueness` and prefix `scope_key` with it), keeping the empty/global key shared.

## Medium (61)

### `pyproject.toml:29` — Runtime dependencies are unbounded above, against the project's stated bound-below-next-major rule, with no gate

*consistency · core-top-level*

CLAUDE.md requires "Bound dependencies below the next major version (e.g. `>=1.28,<2`)" and that every adopted rule get an enforcement mechanism. Of the 11 runtime dependencies only `mcp>=1.28,<2` is bounded:

```
"pydantic>=2.0", "pydantic-settings>=2.0", "fastapi>=0.110", "typer>=0.12",
"uvicorn>=0.29", "pyyaml>=6.0", "jinja2>=3.1", "python-multipart>=0.0.9",
"openpyxl>=3.1", "regex>=2024.5.15"
```

The extras are unbounded too (`httpx>=0.27`, `rdflib>=7.0`). This directly affects the modules in this group: `storage/*.py` imports pydantic and pyyaml, `_http.py` imports httpx. `grep -rl pyproject tests/` returns nothing, so no gate test asserts the bounds either.

Failure scenario: pydantic 3 or pyyaml 7 releases; lockfile-based CI stays green while a fresh `pip install metaseed` resolves to the new major and `model_validate`/`yaml.dump` behaviour changes under `storage/json_backend.py` and `storage/yaml_backend.py`.

**Fix:** Add upper bounds (`pydantic>=2.0,<3`, `pyyaml>=6.0,<7`, `httpx>=0.27,<1`, ...) and add a test that parses pyproject and fails when any `project.dependencies` or `project.optional-dependencies` entry lacks an upper bound.

### `pyproject.toml:29` — httpx imported directly by ontology.py but not declared in core dependencies

*correctness · agent-mcp-tools*

`src/metaseed/agent/mcp/tools/ontology.py:16` does a module-level `import httpx`, and that module is imported unconditionally by `server.py` (line 227, reached at import time via `mcp = create_server()` on line 335). `httpx` appears in pyproject only under `[project.optional-dependencies]` — `dev`, `ena`, `brapi`, `pride`, `metabolights` — never in the core `dependencies` list. It currently arrives transitively through `mcp` (verified: `mcp` requires `httpx<1.0.0,>=0.27.1`), which is precisely the arrangement the project rule forbids: "Declare every package the code imports directly in pyproject; never rely on it arriving transitively." If `mcp` ever drops or vendors httpx, a base `metaseed` install stops being able to import its own MCP server.

**Fix:** Add `httpx>=0.27,<1` to the core `dependencies` (the extras can then drop their own copies), and gate it with the clean-environment install smoke test the project already mandates.

### `src/metaseed/agent/mcp/manager.py:42` — MCPServerManager is a process-wide singleton with a hardcoded endpoint, discovered rather than injected

*design · agent-core*

`__new__` enforces a single instance and `get_mcp_manager()` hands it out; the three UI routes reach it with function-body imports (`from metaseed.agent.mcp.manager import get_mcp_manager` at ui/routes/api.py:404, 428, 452). Host, port and transport are baked in as defaults on every method (`127.0.0.1`, `8001`, `"streamable-http"`), repeated across `start`, `is_running`, `_check_port_in_use`, `kill_orphaned`, `status` and `get_connection_url`, and the UI route exposes none of them. `_check_mcp_responding` then probes `http://{host}:{port}/mcp` to decide whether a server exists — the "probing for a running server" hidden dependency the project rules name directly. A host embedding metaseed cannot supply its own manager, its own port, or a manager that does not spawn subprocesses at all, and there is no gate test for this boundary (unlike `tests/test_mcp_tools_have_no_ambient_state.py` for the tool layer).

**Fix:** Make `MCPServerManager` an ordinary class taking host/port/transport in `__init__`, compose one in `create_app` and hang it on `app.state`, and let the routes take it from there. Keep `get_mcp_manager()` only as a CLI-level composition helper if needed.

### `src/metaseed/agent/mcp/manager.py:82` — start() SIGKILLs whatever process holds the port, with no check that it is an MCP server

*correctness · agent-core*

`start()` does:

```python
if self._check_port_in_use(port):
    logger.warning("Port %d is already in use, killing orphaned process", port)
    self.kill_orphaned(port)
```

`_check_port_in_use` returns the PID reported by `lsof -ti :8001` for *any* listener, and `kill_orphaned` then does `os.kill(pid, SIGTERM)` followed by `os.kill(pid, SIGKILL)` if the port is still bound. Nothing verifies the process is a metaseed MCP server — not the command line, not `_check_mcp_responding`. `POST /api/mcp/start` (ui/routes/api.py:428) is a plain unauthenticated local route, so a click in the UI kills any unrelated local process that happens to be listening on 8001 (another dev server, a database tunnel, a colleague's app). `kill_orphaned` also returns True whenever it sent a signal, whether or not the port was actually freed.

**Fix:** Only kill a process the manager itself started, or gate the kill behind `_check_mcp_responding(host, port)` plus a command-line check that the PID is a metaseed process; otherwise report the port as occupied and let the caller choose. Have `kill_orphaned` return True only after re-checking that the port is free.

### `src/metaseed/agent/mcp/manager.py:181` — stop() reports success without stopping an orphaned server it can still see

*correctness · agent-core*

```python
if self._process is None:
    return MCPServerStatus(running=False)
```

`is_running()` deliberately falls back to the port probe (`_check_port_in_use` + `_check_mcp_responding`) precisely so a server started by an earlier process is detected. `stop()` has no such fallback: after the web app restarts, `_process` is None, so `POST /api/mcp/stop` returns `running=False` while `GET /api/mcp/status` keeps returning `running=True` for the still-live server. The manager already has `kill_orphaned` for exactly this case and does not call it here.

**Fix:** In `stop()`, when `_process` is None, probe the port and stop the responding orphan (reusing the ownership check from the `kill_orphaned` fix), or return a status that says the server is still running and was not owned by this manager.

### `src/metaseed/agent/mcp/server.py:335` — Module-level `mcp = create_server()` builds the whole server at import and makes run_server uncomposable

*design · agent-core*

`mcp = create_server()` runs at import time, so importing `metaseed.agent.mcp` (its `__init__` imports `server`) constructs a FastMCP instance, builds a parser registry and registers all seven tool groups — an unconditional side effect for anyone who only wanted `MCPServerManager` or `SPEC_BUILDING_INSTRUCTIONS` (the latter is in the frozen hub contract, tests/hub_contract.py:20). Worse, `run_server` runs *that* global rather than a server the caller composed, so a host that must serve several callers — the case `create_server(resolve_context=...)` exists for, per its own docstring — has no way to run its server through the library's runner and must reimplement uvicorn wiring. The comment "# Server instance for import" is stale: grep across src and tests shows nothing imports `server.mcp`.

**Fix:** Delete the module-level instance and give `run_server` a `server: FastMCP | None = None` (or `resolve_context`) parameter, constructing the default lazily inside the function.

### `src/metaseed/agent/mcp/tools/datasets.py:211` — create_dataset always returns root_entity: null

*correctness · agent-mcp-tools*

The response is built as:

    "root_entity": facade._spec.root_entity if facade._spec else None,

`ProfileFacade.__init__` assigns `self._spec = spec` from the *optional* pre-loaded-spec keyword (`facade/core.py:75`). `create_dataset` constructs the facade positionally as `ProfileFacade(profile, version)`, so `_spec` is always `None` and the guard always takes the `else` branch. Verified by execution:

    ProfileFacade('miappe','1.1')._spec        -> None
    ProfileFacade('miappe','1.1')._root_entity() -> 'Investigation'

So the documented `root_entity` field of this tool's result is unconditionally null on every real call, while the facade knows the correct answer. This matters because the server instructions tell agents to create a dataset and then add entities "root-first".

**Fix:** Use the facade's resolver (`facade._root_entity()`, or better a public accessor added to ProfileFacade) instead of reaching for the private, usually-unset `_spec`. Add a test asserting `create_dataset` reports the profile's actual root entity.

### `src/metaseed/agent/mcp/tools/entities.py:115` — _creation_hints advises creating children the repository will reject (nested_fields vs child_fields)

*correctness · agent-mcp-tools*

`_creation_hints` builds the suggestion from `helper.nested_fields`:

    children = sorted(set(helper.nested_fields.values()))
    ...
    hints["typical_next"] = (
        f"Create {children[0]} entities with parent_id set to this entity"
    )

but the repository validates a parent-child pair against `child_fields` (`repositories/memory.py:124`: `valid_child_types = list(parent_helper.child_fields.values())`). `child_fields` honours the spec's `owns:` markers and is a strict subset of `nested_fields` whenever a profile uses them. ISA 1.0 uses `owns: true` in 33 places, so the two disagree for 13 entity types.

Verified by execution: for ISA 1.0 `Investigation`, `sorted(set(nested_fields.values()))[0] == 'Comment'`, so the hint returned by `create_entity` is literally "Create Comment entities with parent_id set to this entity". Executing that advice fails:

    svc.create_entity("Comment", {...}, investigation_id)
    -> ValueError: Invalid parent: Investigation cannot contain Comment.
       Valid child types: ['OntologySource', 'Publication', 'Person', 'Study']

Same for Assay, Protocol and Process (all yield `typical_next -> Comment`). `expected_children` is likewise wrong for Study (adds `Comment`, `OntologyAnnotation`). The existing test (tests/test_agent/test_mcp.py:367) only exercises MIAPPE, which has no `owns` markers and where the two properties coincide, so it passes on the broken code.

**Fix:** Use `helper.child_fields` (the containment relation the repository enforces) in `_creation_hints`, and add an ISA-based test asserting that every type named in `expected_children` is accepted by `create_entity` as a parent-child pair.

### `src/metaseed/agent/mcp/tools/entities.py:529` — First-match 'which parent field references this child type' rule reimplemented outside facade/linking.py (ADR 005)

*design · agent-mcp-tools*

ADR 005 states facade/linking.py is the single owner of "which parent field references a child of a given type", and `linking.target_reference_field` implements exactly that first-match-over-`nested_fields` rule. Two sites in this module reimplement it verbatim:

    # create_entity, linked_via_field
    for field_name, ref_type in parent_helper.nested_fields.items():
        if ref_type == entity_type:
            result["linked_via_field"] = field_name
            break

    # _find_parent_from_references, lines 282-286
    for fname, ftype in parent_helper.nested_fields.items():
        if ftype == entity_type:
            parent_field = fname
            break

`facade/store.py:380` and `repositories/helpers.py:158,204` all call `target_reference_field`; these two do not. The gate test `tests/test_tree_linking_is_owned_once.py` only scans for the string `single_entity_fields`, so the first-match rule has no gate at all and this duplication is invisible to CI — the project rule requires every adopted rule to have an enforcement mechanism.

**Fix:** Import and call `metaseed.facade.linking.target_reference_field` at both sites, and extend the gate test to also flag modules outside `facade/linking.py` that iterate `nested_fields` to pick a reference field.

### `src/metaseed/agent/mcp/tools/ontology.py:180` — get_ontology_term reports an OLS4 outage as 'Term not found'

*correctness · agent-mcp-tools*

`_make_request` returns `None` for both `httpx.HTTPStatusError` and `httpx.RequestError` (lines 48-53), collapsing a 404, a 503 and a connection timeout into one value. `get_ontology_term` then does:

    data = _make_request(f"/ontologies/{ontology}/terms/{encoded_iri}")
    if data is None:
        return json.dumps({"error": f"Term not found: {term_id}"})

A network failure or an OLS outage is therefore reported to the agent as a positive statement that the term does not exist. The project rule is explicit that an outage must report "not checked", never a failure, and the sibling `validate_ontology_terms` in the same module implements exactly that three-outcome contract (`checked: false` / `valid: null`), so this is also an internal inconsistency.

**Fix:** Have `_make_request` distinguish 404 from transport/5xx failure (e.g. return a small result object or re-raise), and return `{"checked": false, "message": "...service did not answer..."}` rather than "Term not found" when the service could not be reached.

### `src/metaseed/agent/mcp/tools/profiles.py:248` — get_profile_relationships reports child types that create_entity rejects

*correctness · agent-mcp-tools*

`children = sorted(set(helper.nested_fields.values())) if helper else []` — the same `nested_fields`/`child_fields` confusion as entities.py, but on the tool the server's own instructions designate as the authority on the hierarchy (`server.py:102`: "get_profile_schema (and get_profile_relationships) - learn ... the valid parent-child hierarchy for THIS profile"; `server.py:278`: "Use `get_profile_relationships` ... to see valid parents").

For ISA 1.0 the tool reports `Investigation.children` including `Comment`, and `Study.children` including `Comment` and `OntologyAnnotation`, while `MemoryEntityRepository.create_entity` rejects those exact pairs against `child_fields`. The docstring's claim "the child entity types it can contain" is therefore false for any profile using `owns:` markers — an agent following the documented workflow is told to build links the next call refuses.

**Fix:** Read `helper.child_fields.values()` here, matching the repository's validation, and cover it with a test over the ISA profile.

### `src/metaseed/agent/mcp/tools/validation.py:278` — validate_relationships emits false 'no X linked' warnings for non-containment nested fields

*correctness · agent-mcp-tools*

child_types_present = {c.entity_type for c in node.children}
    for child_type in helper.nested_fields.values():
        if child_type not in child_types_present:
            warnings.append({... "issue": f"no {child_type} linked"})

Same `nested_fields`/`child_fields` mismatch. For ISA 1.0 this warns "no Comment linked" on all 13 entity types that carry a non-owned `Comment` list, and "no OntologyAnnotation linked" on Study/Assay/Protocol/LabeledExtract/FactorValue/ParameterValue — links that cannot be created through `create_entity` at all, since the repository rejects those parent-child pairs. The docstring promises "links that the spec makes possible but that are unset"; these are not possible.

**Fix:** Iterate `helper.child_fields.values()` so the warning set matches what `create_entity` will accept.

### `src/metaseed/api/serialization.py:204` — Strict _load_tree() clears the store before validating, so an aborted load leaves the dataset wiped

*correctness · api-brapi*

`load()` goes to visible trouble to avoid a silent wipe on a malformed payload (lines 180-186: 'Falling through to an empty list would clear the store before loading nothing — a silent wipe.'). `_load_tree()` then does the exact thing that guard protects against: `self._facade.clear()` runs first (line 204), and in strict mode (`on_skip is None`) a bad node re-raises from line 225 (`if on_skip is None: raise`) — or `node["entity_type"]` raises `KeyError` for a node with no type — after the caller's existing dataset has already been destroyed. The docstring promises 'a tree node whose entity_type is missing or not defined by the profile aborts the load, so one bad node makes the whole dataset unreadable', but the actual outcome is worse than unreadable: the previously loaded dataset is gone too.

**Fix:** Build the nodes into a scratch store (or pre-scan the payload with `_unloadable_reason` before clearing) and only `clear()` + commit once the whole tree is known loadable. Add a test that a strict `load()` of a tree with one unknown entity type raises AND leaves the previously loaded entities intact.

### `src/metaseed/cli/app.py:165` — Profile-level `validate` actions run against single non-root entity files, producing spurious errors

*correctness · cli*

`validate` unconditionally builds a one-entity client and runs every registered `validate` action for the profile:

    client = MetaseedClient(profile, version)
    client.create_entity(entity, data, skip_validation=True)
    for action in profile_checks:
        errors.extend(action.resolve()(client))

Those actions (`metaseed.pride.validate:validate_submission`, `validate_cv`, `metaseed.metabolights.validate:validate_cv`) are whole-dataset structural checks rooted at the profile's root entity. When the user validates any non-root entity file they fire anyway. Verified:

    $ metaseed validate sample.yaml -e Sample -p pride -v 2.0
    - species: Field 'species' is required
    - ncbi_taxonomy_id: Field 'ncbi_taxonomy_id' is required
    - unique_id: Extra inputs are not permitted
    - submission.px: no submission.px generated (dataset has no Dataset entity)   <-- spurious

The last error is not a defect in the user's Sample file; it is an artefact of running a Dataset-level rule against a Sample. It also drives the exit code, so a scripted caller cannot distinguish it from a genuine failure.

**Fix:** Gate the profile-check block on the validated entity being the profile's root entity (the facade already exposes this - `ProfileFacade._root_entity`), or make the action contract explicit about which entity it applies to and skip actions whose root is absent from the client.

### `src/metaseed/cli/app.py:233` — `template` emits `'# field': null` data keys, not YAML comments; its own output fails `metaseed validate`

*correctness · cli*

The optional-field branch writes `template_data[f"# {field.name}"] = None` and relies on a "comment-key technique" described at lines 209-210 and 232. PyYAML does not emit a `#`-prefixed key as a comment - it quotes it as a scalar key. Verified against the installed venv:

    $ metaseed template investigation
    unique_id: <unique_id>
    title: <title>
    '# description': null
    '# submission_date': null
    ...

These are real mapping keys, not comments. Round-tripping through metaseed's own commands fails:

    $ metaseed template investigation -o t.yaml && metaseed validate t.yaml
    - # description: Extra inputs are not permitted
    - # submission_date: Extra inputs are not permitted
    ... (8 such errors)

So the documented `template` command (docs/api/cli.md:46) produces a file the documented `validate` command rejects. The comment at line 209-210 ("The '# name' comment-key technique is YAML-specific") and at line 232 ("Add commented example for optional fields") both state something the code does not do.

The guarding test cannot catch this: tests/test_cli/test_commands.py:118 `test_template_yaml_keeps_optional_field_comments` asserts only `"# " in result.stdout`, which is satisfied by the broken quoted-key output - it passes on broken code.

**Fix:** Build the YAML text explicitly instead of round-tripping a dict: dump the required fields with `yaml.dump`, then append真 comment lines (`f"# {field.name}:"`) as raw text. Tighten the test to parse the emitted YAML with `yaml.safe_load` and assert that no loaded key starts with `#`, and add a test that `validate` accepts a filled-in template.

### `src/metaseed/dcat/export.py:51` — build_card discovers a fresh SpecLoader instead of using the facade's injected loader/spec

*design · exporters*

`spec = SpecLoader(profile=facade.profile).load_profile(facade.version, facade.profile)` constructs its own loader rather than asking the facade. `ProfileFacade.__init__` accepts both `loader=` and `spec=` (facade/core.py:58-79), and `ProfileFacade._root_entity` (facade/core.py:374-393) carries a docstring recording this exact defect as already fixed there: "Asked of the facade's own injected loader - building a fresh ``SpecLoader`` here silently ignored whatever loader the caller composed, so a facade over a custom source answered this one question from the default filesystem instead." The DCAT card resolver still does it. This is both the injected-vs-discovered-collaborator rule violation and a correctness bug. It is also the sole error-handling divergence: `_root_entity` wraps the load in `except (SpecLoadError, OSError)`, while `build_card` lets `SpecLoadError` escape into the export path, where `ui/routes/import_export.py:158` converts any exception into a 500.

**Fix:** Expose the resolved spec (or the loader) on the facade and read it here, e.g. a `facade.spec` accessor that returns `self._spec` when set and otherwise loads via `self._loader`. Then `build_card` becomes `spec = facade.spec` with no loader construction and no independent failure mode.

### `src/metaseed/dcat/publication.py:0` — The whole publication seam has no caller in the product

*dead-code · exporters*

`PublicationContext`, `build_published_dataset`, `origin_url` and `spdx_license_uri` are re-exported from `metaseed.dcat.__init__` and documented in docs/architecture/dcat.md, but a repo-wide grep finds references only in `tests/test_dcat/test_publication.py` and the docs page - no UI route, CLI command, adapter action, API endpoint or other library module calls any of them. `ui/routes/dcat.py` builds and serializes a card but never publishes one, and `ORIGIN_LANDING_PAGE`/`origin_url` are never consulted by the ENA/PRIDE/MetaboLights importers that would know a dataset was derived from a repository record. Per the project rule, a capability reachable only from a library call is unfinished work, and a rule that only tests exercise erodes.

**Fix:** Either wire it in - e.g. have the importers record `origin_url(profile, accession)` as the card's `source`, and give `/dcat` a publish form that supplies a `PublicationContext` - or delete the module and its docs section until there is a caller.

### `src/metaseed/facade/core.py:613` — __dir__ hides the whole public API from tab completion on a class built for interactive use

*design · facade*

```python
def __dir__(self):
    return list(self._entities.keys()) + ["profile", "version", "entities", "help", "search"]
```

Overriding `__dir__` without chaining to `super().__dir__()` removes every other attribute. Verified: `"add_entity" in dir(f)`, `"to_graph" in dir(f)`, `"load_yaml" in dir(f)`, `"get_helper" in dir(f)` are all `False`. The docstring says "Enable tab completion for entities", but the net effect is that thirty-odd public methods become invisible in Jupyter and the REPL — the stated primary consumer.

**Fix:** Return `[*super().__dir__(), *self._entities]` (deduplicated) so the dynamic entity names are added rather than substituted.

### `src/metaseed/facade/graph.py:250` — Nested-field reference edges are never flagged redundant, contradicting the documented contract

*correctness · facade*

The module docstring states: "A reference edge whose endpoints already share a containment edge ... carries `"redundant": True`". The reference-field loop honours this (line 220), but the nested-field loop at 250-259 appends its edge with no `containment_pairs` check at all — and nested fields ARE the containment fields, so essentially every edge it draws restates a containment edge.

Verified:

```
{'id': 'INV-1->ST-1', 'from': 'INV-1', 'to': 'ST-1'}
{'id': 'INV-1->ST-1:studies', ..., 'label': 'studies'}          # no redundant flag
{'id': 'ST-1->INV-1:investigation_id[0]', ..., 'redundant': True}
```

A consumer that suppresses redundant edges (the documented purpose) still draws a duplicate for every parent-child pair. The two loops also build edge ids differently (`[index]` suffix in one, none in the other), so the nested loop can emit colliding ids when a field names the same target twice.

**Fix:** Apply the same `frozenset((vis_id, target_vis_id)) in containment_pairs` check and the same indexed edge-id scheme in the nested-field loop; better, factor the edge construction into one helper used by both loops.

### `src/metaseed/facade/linking.py:48` — ADR 005's target_reference_field rule is re-implemented in the MCP tools and the gate test does not catch it

*design · facade*

The module docstring claims the gate test `tests/test_tree_linking_is_owned_once.py` fails "when the shape rule grows a second home", but that test only greps for the string `single_entity_fields`. The other decision the module claims to own — "which parent field references a child of a given type" — is re-implemented verbatim twice, unguarded:

```python
# src/metaseed/agent/mcp/tools/entities.py:282
for fname, ftype in parent_helper.nested_fields.items():
    if ftype == entity_type:
        parent_field = fname
        break
# and again at entities.py:529
```

This is the first-match rule `target_reference_field` exists to state once. Per the project rule, a rule enforced only by prose erodes.

**Fix:** Call `target_reference_field` at both MCP sites, and extend the gate test to also fail on a non-allowed module that iterates `nested_fields.items()` comparing against a child type (or, more robustly, assert `target_reference_field` is the only definition of that loop).

### `src/metaseed/facade/store.py:459` — to_dict never emits _parent_id, so a parent without an identifier value loses all child links on round-trip

*correctness · facade*

`to_dict` persists `_node_id` for every node specifically so identity survives a reload, and `_create_node_from_dict` supports a `_parent_id` back-reference (line 562). But `serialize_node` only ever writes `_parent_unique_id`, and only when `node_unique_id` is truthy. A parent with no identifier value — routine for the drafts the UI persists — emits no parent reference at all.

Reproduced with miappe 1.2:

```python
p = f.add_entity("Investigation", {"title": "no id"}, skip_validation=True)
c = f.add_entity("Study", {"unique_id": "ST-1"}, parent_id=p.id, skip_validation=True)
ProfileFacade("miappe", "1.2").load_from_dict(f.to_dict())
# roots: [('Investigation', ...), ('Study', ...)]  -> the child is orphaned
```

**Fix:** Emit `_parent_id = node.parent_id` alongside `_parent_unique_id` (or as the fallback when the parent has no identifier value), and load it via the existing `old_id_to_node` path. Test a draft parent with an unnamed identifier round-tripping.

### `src/metaseed/facade/store.py:688` — Containment direction is inverted on reload for owned single-entity nested fields

*correctness · facade*

`_link_by_nested_arrays` only reads list values:

```python
child_ids = node_data.get(field_name, [])
if not isinstance(child_ids, list):
    continue
```

But `facade/linking.linked_reference_value` deliberately writes a SCALAR for a `type: entity` field (`single_entity_fields`), so the writer's shape is never read back. `_link_by_reference_fields` then runs and, because such a field is usually ALSO a declared `reference`, it links in the opposite direction — treating the owning parent as the child.

Verified against the shipped isa 1.0 spec, where `Process.executes_protocol` is `type: entity`, `owns: true`, `items: Protocol` and simultaneously `reference: Protocol.name`:

```python
f = ProfileFacade("isa", "1.0")
f.load_from_dict([
    {"_type": "Process", "name": "P1", "executes_protocol": "PROTO-1"},
    {"_type": "Protocol", "name": "PROTO-1"},
])
# root Protocol PROTO-1 -> children ['Process']
```

The Protocol becomes the root and the Process its child — the exact reverse of the `owns` declaration. The same fields exist on `FactorValue.factor_name` and `ParameterValue.category`.

**Fix:** Accept a scalar in `_link_by_nested_arrays` (normalise `child_ids` to `[child_ids]` when it is a non-list truthy value), and have `_link_by_reference_fields` skip any field that is also one of the node's own `nested_fields`/`owned_child_fields` — a field the entity owns names its child, never its parent. Add a red-first test using isa Process/Protocol.

### `src/metaseed/forms/__init__.py:129` — exclude_parent_ref uses a name-convention heuristic that fails for most profiles instead of the spec's reference_fields map

*correctness · core-top-level*

`get_field_data(helper, exclude_parent_ref=...)` decides which child field is the auto-filled parent reference with a hand-rolled string heuristic:

```python
parent_lower = exclude_parent_ref.lower()
if field_name.lower() in [
    f"{parent_lower}_id",
    f"{parent_lower}_identifier",
    f"{parent_lower}_unique_id",
]:
    continue
```

This is a second, divergent copy of a decision the profile already declares and that `EntityStore._fill_parent_reference` (src/metaseed/facade/store.py:182) makes from `helper.reference_fields` -- `{field_name: (target_entity_type, target_field)}`, parsed from the spec's `reference: Entity.field`. The two disagree in two concrete ways:

1. `.lower()` is not `to_snake_case()` (which already exists in `metaseed.utils.text`). For a multi-word parent type the key built is wrong: `ObservationUnit` -> `observationunit_id`, but MIAPPE's field is `observation_unit_id`; `BiologicalMaterial` -> `biologicalmaterial_id`, but the field is `biological_material_id` (src/metaseed/specs/miappe/1.2/profile.yaml:196, 202). Only single-word parents (Study, Investigation) ever match.
2. The `_id`/`_identifier`/`_unique_id` suffix list does not cover `_ref`, which is the ENA convention throughout: `Experiment.study_ref`, `Experiment.sample_ref`, `Run.experiment_ref` (src/metaseed/specs/ena/1.0/profile.yaml:215-233).

Failure scenario: in the child-create form (src/metaseed/ui/routes/forms.py:148) for an ENA Experiment under a Study, or a MIAPPE Sample under an ObservationUnit, the parent-reference field is rendered as an editable input even though `_fill_parent_reference` will populate it. The user is shown a field they must not fill; if they do fill it, `_fill_parent_reference` skips (`data.get(ref_field)` is truthy) and the entity silently links to whatever they typed. Nothing catches this: `grep -rn exclude_parent_ref tests` returns no hits, so the parameter has zero test coverage.

This also sits awkwardly against ADR 005: the reference-field decision is meant to be stated once, and this is a third statement of it (parent->child in `facade/linking.target_reference_field`, child->parent in `store._fill_parent_reference`, and this heuristic).

**Fix:** Drop the heuristic and ask the helper, exactly as the store does: skip `field_name` when `helper.reference_fields.get(field_name)` names `exclude_parent_ref` as the target entity type. Add a test with a multi-word parent (ObservationUnit) and an ENA `_ref` field, both of which are red today.

### `src/metaseed/isatab/__init__.py:283` — _assay_file discards DataFile.file_type, emitting every file as a Raw Data File

*correctness · exporters*

`header = ["Sample Name", "Assay Name", "Raw Data File"]` is fixed, and each row writes `str(data_file.get("filename"))` into that one column. `DataFile.file_type` is a *required* field in the metabolights profile with enum `[Raw Data File, Derived Data File, Acquisition Parameter Data File, Free Induction Decay Data File]` (specs/metabolights/1.0/profile.yaml:488-493). Reproduced: an assay with DataFile(raw1.raw, Raw Data File) and DataFile(deriv1.mzml, Derived Data File) exports both under a single `Raw Data File` column. `isatab/reader.py:read_data_files` groups by column header and `metabolights/mapper.py:_file_type_from_column` derives `file_type` from it, so re-importing the export re-labels every derived file as raw - the docstring's claim that this "round-trips with read_data_files" is false for anything but raw files.

**Fix:** Group `data_files` by `file_type`, emit one column per distinct declared type (falling back to `Raw Data File` when unset), and place each file's name under its own column.

### `src/metaseed/metabolights/client.py:92` — _get_text bypasses the shared retry helper, and its failure is swallowed into a silently metadata-only import

*consistency · importers-and-models*

`study()` goes through `metaseed._http.request_json`, which retries connection errors and 429/5xx with backoff. `_get_text` (used by `study_files`) calls `httpx.get`/`self._client.get` directly with no retry, so a single transient 503 on the FTP directory index raises immediately. metabolights/__init__.py:65-68 then swallows it:

```python
try:
    isatab_files = client.study_files(accession)
except (httpx.HTTPError, OSError):
    isatab_files = {}
```

with no logging and no marker on the result. The user receives a dataset with zero Samples, DataFiles and Metabolites and no way to tell an embargoed study (correct behaviour) from a five-second FTP hiccup (data loss). The `metaseed.logging` module exists and is unused by any importer.

**Fix:** Route `_get_text` through a text-returning sibling of `request_json` so it gets the same retry/backoff, and log a warning (or surface a flag on the returned client) when the ISA-Tab fetch is skipped, so an outage reports "not checked" rather than looking like an empty study.

### `src/metaseed/models/factory.py:135` — get_in's loader path mutates the process-global context it exists to bypass

*correctness · importers-and-models*

`get_in` is documented as resolving "under an EXPLICIT profile and version ... never by the mutable current context", which is the fix `__model_key__` binding was introduced for (comments at factory.py:94-97 and 333-337). But on a cache miss it calls `self._loader(name, version, profile)`, and the loader is `get_model` (models/__init__.py:87), whose first statement is `set_model_context(profile.lower(), version)` — so resolving a nested entity for profile A while profile B is ambient silently rebinds the global context to A.

Failure scenario: two facades share a process (MCP + UI). Profile B is active. Validating a profile-A entity whose nested type is not yet cached triggers the loader; afterwards the global context reads (A, versionA). Any subsequent resolution that falls back to `get_registered_model` (factory.py:342, taken whenever a class has no `__model_key__`) now resolves against A — the exact cross-profile hijack the binding was added to prevent.

**Fix:** Have get_in call a context-free generation path (load spec + create_model_from_spec + register under the explicit key), or save and restore the global profile/version around the loader call.

### `src/metaseed/pride/export.py:62` — ADR 005 violation: _dataset_with_children re-implements target_reference_field's first-match rule

*design · importers-and-models*

ADR 005 makes facade/linking.py the single owner of "which parent field references a child of a given type". linking.py states that rule once in `target_reference_field()` (first declared nested field whose target names the child type wins), and facade/store.py and repositories/helpers.py both import it. pride/export.py instead re-derives it inline:

```python
field_for_type: dict[str, str] = {}
for field_name, entity_type in helper.nested_fields.items():
    field_for_type.setdefault(entity_type, field_name)
```

This is the same first-match-over-nested_fields decision with a second home. The existing gate test (tests/test_tree_linking_is_owned_once.py) only scans for the string `single_entity_fields`, so it cannot see this duplication — the ADR's other decision has no gate at all. (ui/helpers/entity_helpers.py:134 has a third, `{v: k for k, v in ...}`, which is last-wins and therefore already disagrees with linking.py — evidence the rule is eroding.)

**Fix:** Import `target_reference_field` from metaseed.facade.linking and call it per child type instead of building `field_for_type`. Extend tests/test_tree_linking_is_owned_once.py to also fail on modules that iterate `nested_fields` to pick a field by child type outside facade/{helper,linking}.py.

### `src/metaseed/pride/export.py:68` — Child-node fold only reattaches to the Dataset, so grandchildren (Sample.custom_attributes) are silently dropped

*correctness · importers-and-models*

`_dataset_with_children` recurses the whole subtree but only ever appends an entity to a field of the *root Dataset*:

```python
def descend(node):
    for child in node.children:
        entity = by_node.get(str(child.id))
        target = field_for_type.get(child.entity_type)   # Dataset fields only
        ...
        descend(child)
```

The pride profile (specs/pride/1.0 and 2.0) declares `Sample.custom_attributes: list[CustomAttribute]`. In the create-under-parent MCP flow a CustomAttribute is a child node of a Sample, and `field_for_type` has no "CustomAttribute" key (Dataset has no such field), so it is dropped — it is never folded onto its own Sample either. Consequences, both contradicting the code's own claims:

* pride/validate.py:33 iterates `sample.get("custom_attributes")`, which is always empty for that flow, so `custom_attributes[].cv_accession` accessions are never checked — exactly the gap the comment at pride/validate.py:60-61 says this fold closes ("so their CV accessions are checked too").
* pride/export.py:175/193 (`_characteristic_columns` / `_sample_characteristic`) produce an SDRF with no custom-attribute columns for the same datasets.

Failure scenario: create Dataset -> Sample ("S1") -> CustomAttribute {name: "cell line", cv_accession: "XX:9999999"}. `validate_cv` returns [] (bogus accession unreported) and `to_pride_sdrf` emits no `characteristics[cell line]` column, while the same dataset authored with inline lists reports the error and emits the column.

**Fix:** Fold each child into its *own parent's* nested field (resolve the parent helper per node, not only the Dataset helper), or state in the docstring that only direct Dataset children are reconstructed and add a test covering a CustomAttribute created under a Sample.

### `src/metaseed/repositories/file.py:329` — FileEntityRepository stores Python objects in EntityData.data while MemoryEntityRepository stores JSON scalars

*consistency · repositories*

`file.py:329` and `file.py:381` use `instance.model_dump(exclude_none=True)`, whereas every dump in `memory.py` (lines 62, 88, 169, 224, 271, 277) uses `model_dump(mode="json", exclude_none=True)`. Profile `date`/`datetime` fields map to `datetime.date`/`datetime.datetime` in the generated models (`models/factory.py:373-374`), so the two implementations of the same `EntityRepository` interface return different value types for the same entity: ISO strings from the memory backend, `datetime.date` objects from the file backend. Any consumer that serializes the result (MCP tool responses, HTTP JSON) raises `TypeError: Object of type date is not JSON serializable` with the file backend only. The internal `_save` masks this because `json.dump(..., default=str)` coerces silently.

**Fix:** Use `model_dump(mode="json", exclude_none=True)` in `create_entity` and `update_entity` in `file.py` so `EntityData.data` is JSON-safe in both backends, and drop the `default=str` crutch in `_save`.

### `src/metaseed/repositories/helpers.py:254` — normalize_reference_fields silently drops reference list items it cannot normalize

*correctness · repositories*

In the list branch, an item that is a dict without a resolvable identifier contributes nothing to `normalized_list`, and an item that is neither `dict` nor `str` (e.g. an int identifier) is skipped entirely. `[{"name": "SRC-1"}, {"description": "no id"}]` therefore becomes `["SRC-1"]` — the second reference is lost with no error and no log. Worse, `if normalized_list:` (line 265) means that when *every* item fails, the field keeps its original embedded objects, so the function's contract ("store IDs instead of embedded objects") holds sometimes and not others, and downstream code sees a mixed shape. The same asymmetry exists in the single-entity branch: `if item_id:` leaves an unresolvable dict in place.

**Fix:** Either raise/propagate a diagnostic for items whose identifier cannot be resolved, or preserve them unchanged in the output list; do not drop references silently. Make the empty-result case behave like the partial case rather than reverting the whole field.

### `src/metaseed/repositories/memory.py:122` — Parent-child admissibility check duplicated verbatim in both repositories

*design · repositories*

`memory.py:122-129` and `file.py:307-315` contain the same block — `valid_child_types = list(parent_helper.child_fields.values())`, membership test, and a near-identical `Invalid parent: ...` message differing only in line wrapping. `repositories/helpers.py` exists precisely to hold logic shared by the two backends, and ADR 005 already centralises the neighbouring decisions (`target_reference_field`, link/unlink shape) in `facade/linking.py`. The duplicate is how the two backends drifted apart before (the create/delete reference asymmetry the ADR was written for), and the existing gate test only scans for `single_entity_fields`, so it cannot catch this copy.

**Fix:** Extract a single `validate_parent_child(parent_helper, parent_type, child_type)` (in `repositories/helpers.py`, or as an admissibility predicate in `facade/linking.py` alongside `target_reference_field`) and call it from both repositories.

### `src/metaseed/seek/templates.py:41` — `_ASSAY_LEVELS["other_material"]` is unreachable; `seek_level_for` documents a variability that cannot occur

*dead-code · seek*

`seek_level_for` reads the assay template level off the plans:

    title_tag = next((p.isa_tag for p in plans if p.is_title), "data_file")
    return _ASSAY_LEVELS.get(title_tag, "assay - data file")

and its docstring says "An assay level is ``assay - data file`` or ``assay - material`` depending on what its title attribute is tagged, so it is read off the plans rather than assumed."

But `isa_types.sample_type_attribute_plans` sets `is_title=True` on exactly one plan (line 121-130), whose `isa_tag` is `title_tag` taken from `_LEVEL_TAGS[level]`, and `_LEVEL_TAGS["assay"]` hardcodes `("data_file", "data_file_comment")`. A profile field's `isa_tag` never reaches the title attribute. So `title_tag` is always `"data_file"` at the assay level, `_ASSAY_LEVELS["other_material"]` can never be selected, and "assay - material" templates are never generated.

This contradicts `isa_types.py:29`, which states "an assay type [needs] exactly one `data_file` or `other_material`" — the second option is unimplemented, but the code and docstring read as if it were supported.

**Fix:** Either wire the choice in (let the profile entity or the SEEK role select `other_material` for a material-producing assay, and thread that into `_LEVEL_TAGS`), or delete the `other_material` entry and the `next(...)` lookup and state plainly that this projection only emits `assay - data file` levels. Do not leave a branch that no input can reach.

### `src/metaseed/services/ontology.py:318` — search_sync names its result cap `rows`, while the TermSource port and every sibling adapter name it `limit`

*consistency · services*

`TermSource.search_sync` (term_check.py:166-168) declares `search_sync(self, query, ontology=None, limit=20)`. `LocalVocabulary.search_sync` and `VocabularyStore.search_sync` both use `limit`. `OntologyService.search_sync` uses `rows`. It works today only because `TermRouter` happens to call positionally (`searches(query, ontology, limit)`, terms.py:327 and 357); any caller using `limit=` — the name the port publishes — raises `TypeError` against the OLS adapter, and `_search_within` would then swallow that as "cannot restrict to a branch". This directly undermines the substitutability the port exists for, which is a stated reusability aim.

**Fix:** Rename the parameter to `limit` in `OntologyService.search_sync` (keeping `rows` as the OLS query parameter name internally), and have `TermRouter` call adapters with keyword arguments so a mismatch fails loudly rather than being absorbed.

### `src/metaseed/specs/builder.py:471` — add_field bypasses the single-identifier invariant that update_field goes out of its way to enforce

*correctness · specs*

`update_field` rebuilds the whole entity through `model_validate` specifically to re-run the entity-level invariant, with a comment saying why: "pydantic does not validate an assignment, so a bad isa_tag or a second is_identifier sat in the spec and surfaced only on load-back" (lines 496-498, 510-515). `add_field` does neither — it constructs one `FieldSpec` and appends it (lines 471-472), so the invariant is never re-run:

    b.add_field('Thing', 'a', 'string', is_identifier=True)
    b.add_field('Thing', 'b', 'string', is_identifier=True)   # accepted
    b.validate() -> ["model build failed: 1 validation error for EntitySpec ... at most one field may set is_identifier; found ['a', 'b'] ..."]

The draft is left in a state that cannot be built, and the only report is an opaque "model build failed:" wrapping a raw pydantic traceback from the catch-all at line 716 — not the actionable message `update_field` would have produced. Since `add_field` is the primary authoring entry point for both the UI and the MCP `spec_add_field` tool, this is the more likely path to hit.

**Fix:** Re-run the entity validator in `add_field` the way `update_field` does (validate the entity with the appended field before committing it), raising the same `ValueError`. A test that `add_field(..., is_identifier=True)` twice raises rather than producing a draft that only fails at build time.

### `src/metaseed/specs/builder.py:858` — _auto_create_back_reference can create a duplicate field name, and nothing rejects duplicate field names

*correctness · specs*

`_auto_create_back_reference` decides whether the target already has a back-reference by looking only at `f.reference.startswith(f"{entity_name}.")` (builder.py:858-861). A target that already declares a plain field literally named `<parent>_id` (no `reference`) fails that test, so a second field with the identical name is inserted:

    b.add_entity('Study'); b.add_entity('Sample')
    b.add_field('Sample', 'study_id', 'string', description='a legacy free-text column')
    b.add_field('Study', 'samples', 'list', items='Sample')
    # Sample.fields -> [('study_id', 'Study.identifier', True), ('study_id', None, False)]
    # b.validate() -> []

`add_field` itself guards duplicates (`if any(f.name == name for f in entity_def.fields)`, line 462) but this internal insertion path does not, and there is no uniqueness check anywhere else: `EntityDefSpec`/`EntitySpec` have no such validator (schema.py:399-416 only checks the singular markers), and `SpecBuilder._field_issues` does not look for it, so `validate()` returns clean. Confirmed the schema accepts it on load too — `ProfileSpec.model_validate` with two fields named `a` on one entity parses without complaint. Downstream the model factory keys fields by name, so one of the two silently disappears and the author's free-text column becomes a required parent reference.

**Fix:** Match on the field *name* as well as the reference in `_auto_create_back_reference` (and pick a non-colliding name, or raise, when the name is taken by an unrelated field). Independently, add a duplicate-name check: a `model_validator` on `EntityDefSpec`/`EntitySpec` next to `_check_single_marked_field`, so a hand-authored profile is rejected at load rather than losing a column silently.

### `src/metaseed/specs/field_form.py:95` — FieldForm.apply_to assigns attributes directly, bypassing FieldSpec's field validators

*correctness · specs*

`apply_to` populates a `FieldSpec` by attribute assignment (lines 101-133). Pydantic v2 does not validate assignment unless `validate_assignment=True`, which `FieldSpec` does not set, so `FieldSpec._isa_tag_must_be_known` never runs on this path:

    FieldForm(name='x', field_type='string', isa_tag='not-a-real-tag').to_field_spec().isa_tag
    -> 'not-a-real-tag'

The tag lands in the draft, is written to YAML by `to_yaml`, and is only rejected when someone loads the saved profile — the exact failure mode `SEEK_ROLES`/`ISA_TAGS` validation was added to prevent (schema.py:249-254: "an unknown one is only rejected once the Sample Type reaches the server"). `SpecBuilder.update_field` treats this as a bug worth restructuring for; the field-form path, which is what the web spec builder actually posts through (`ui/spec_builder/routes_fields.py:199`), does not. The UI's dropdown of `ISA_TAGS` is presentation, not a constraint on the POST body.

**Fix:** Have `to_field_spec` build the spec through `FieldSpec.model_validate(...)` on a dict, and have `apply_to` validate the assembled values before assigning (or set `model_config = ConfigDict(validate_assignment=True)` on `FieldSpec`). Add a test that an unknown `isa_tag` from the form is rejected rather than stored.

### `src/metaseed/specs/loader.py:48` — _rule_target_fields re-implements applies_to matching instead of using the shared normalizer

*consistency · specs*

`_rule_target_fields` open-codes `key.lower().replace("_", "")` for both sides of the entity-name comparison (lines 59-66) and open-codes the `applies == "all"` branch. `metaseed.specs.schema` already exports `comparable_entity_name` and `applies_to_entity` precisely to stop this: `comparable_entity_name`'s docstring says "One normaliser, imported by both, is what keeps the two answers the same", and `validators/engine.py` and `predicates._target_entities` both import it. This copy also drops the `-` handling that `comparable_entity_name` has, so it and the engine disagree on any entity name containing a hyphen. Because this function decides which fields receive a rule's constraints, a divergence means a constraint the engine believes is delegated to Pydantic is never mirrored onto the field, and is therefore enforced by nothing.

**Fix:** Replace the inline normalization with `applies_to_entity(rule.applies_to, entity_name)` over `profile.entities.items()`, mirroring `predicates._target_entities`.

### `src/metaseed/specs/loader.py:74` — _merge_rule_constraints_into_fields makes the same YAML hash two different ways and forces spurious MAJOR bumps

*correctness · specs*

`SpecLoader._load_profile` calls `_merge_rule_constraints_into_fields(loaded_profile)` (loader.py:247), which copies rule-level `pattern`/`enum`/`minimum`/`maximum` onto the matching `FieldSpec.constraints`. `SpecBuilder.from_yaml` / `ProfileSpec.model_validate` do not. So one document has two `content_hash` values depending on which entry point read it, contradicting `versioning.canonical_json`'s documented guarantee that the hash is stable across a YAML round trip.

Reproduced against a minimal profile whose only constraint is on a rule:

    loader hash  : sha256:a27012d1a7b7
    from_yaml    : sha256:4f5cbe5db0da
    compare_specs(from_yaml, loaded) -> ['Thing.code pattern added: ^[A-Z]+$']

`_pattern_change` classifies that as PATTERN_TIGHTENED = BREAKING, so comparing a draft (imported via `spec_import_yaml` -> `from_yaml`) against the released profile (loaded via `SpecLoader`) reports a breaking change and demands a MAJOR bump for an unedited spec. The same mutation also leaks into `persistence.save_spec`, which serializes via `SpecBuilder.from_spec(spec).to_yaml()`: a load-then-save round trip rewrites the file with constraint blocks the author never wrote. The in-function comment at loader.py:113-118 shows the author was already guarding hash stability for the empty-`Constraints` case, but the merge itself is the larger instance of the same problem.

**Fix:** Either apply the merge on every path into a `ProfileSpec` (a model validator on `ProfileSpec`, so `model_validate`, `from_yaml` and `SpecLoader` all agree), or keep the loaded spec pristine and do the merge in `models.factory` when it builds the Pydantic model. Add a test asserting `SpecLoader.load_profile(...).content_hash == SpecBuilder.from_yaml(text).spec.content_hash` for a profile carrying rule-level constraints.

### `src/metaseed/specs/merge/comparator.py:550` — Difference detection filters out None, so 'set in one profile, absent in another' reports as no difference

*correctness · specs-merge*

`_values_differ` computes `unique = {str(v) for v in values.values() if v is not None}` and returns `len(unique) > 1`. With `{'a/1': None, 'b/1': 'MIAPPE:DM-1'}` the set is `{'MIAPPE:DM-1'}`, so the method returns False and `ontology_term_diff` stays False for an entity that carries an ontology term in one profile and none in the other. `_compare_metadata` (line 209) has the identical filter, so a profile-level `ontology`/`display_name` present in one spec and absent in the other is never reported in `metadata_diffs`. This is also inconsistent with the field-attribute path in the same file, which deliberately includes None: `unique_values = {str(v) for v in attr_values.values()}` (line 418) and `_compare_constraints` (line 481). Consequence: the entity keeps `diff_type=UNCHANGED` where it should be MODIFIED, and the Markdown/HTML reports omit a real ontology-annotation divergence.

**Fix:** Drop the `if v is not None` filter in both places so absence participates in the comparison, matching `_analyze_field_diff`. Add a comparator test with two profiles whose entity ontology_term is None vs set and assert `ontology_term_diff is True`.

### `src/metaseed/specs/merge/merger.py:278` — MODIFIED fields bypass the merge strategy entirely and always take the first profile

*correctness · specs-merge*

`_merge_entity_fields` only consults `strategy.resolve_field` for `DiffType.CONFLICT`. For `DiffType.MODIFIED` it does:

    elif field_diff.diff_type in [DiffType.UNCHANGED, DiffType.MODIFIED]:
        # Use first available spec
        for profile_id in profile_order:
            spec = field_diff.profiles.get(profile_id)
            if spec is not None:
                merged_fields.append(spec)
                break

The comparator marks a field CONFLICT only when `type`, `required`, `items` or `constraints` differ (comparator.py:423,441). Every other differing attribute (`codename`, `description`, `ontology_term`, `ontologies`, `example`, `tier`, `label`, `unit`, `dcat`, `isa_tag`, `owns`, `is_identifier`, ...) yields MODIFIED, so the chosen strategy is never consulted and the first profile silently wins. Verified against shipped data: `compare([('miappe','1.2'),('miappe','1.1')])` reports 149 MODIFIED fields with changed attributes, and `merge([('miappe','1.1'),('miappe','1.2')], strategy='last_wins')` yields `BiologicalMaterial.accession_number.codename = None` (the 1.1 value) instead of `'accessionNumber'`. `prefer_<profile>` is likewise ignored, which makes `PreferProfileStrategy`'s docstring "Always prefer values from a specific profile" aspirational. It also defeats the stated purpose of `FIELD_ATTRIBUTES_TO_COMPARE` (comparator.py:30-36), whose comment claims a new attribute "cannot silently compare as UNCHANGED and be dropped by the merger" — it is not dropped by the comparator, but it is dropped by the merger. Unlike ADDED/REMOVED/CONFLICT, this branch emits no MergeWarning either, so the loss is invisible in the result.

**Fix:** Route MODIFIED fields through `strategy.resolve_field` as well (strategies already fall back to first-available when only one profile has the field), or, if first-wins for non-conflicting attributes is intentional, emit a MergeWarning naming the dropped attributes and say so in the strategy docstrings and docs/guides/spec-merge.md.

### `src/metaseed/specs/merge/merger.py:372` — Manual resolution of a constraint conflict crashes the whole merge

*correctness · specs-merge*

`_apply_manual_resolution` writes the resolution attribute straight into the dumped field dict:

    data = base_spec.model_dump()
    for resolution in resolutions:
        data[resolution.attribute] = resolution.resolved_value
    return FieldSpec.model_validate(data)

`FieldSpec` declares `model_config = ConfigDict(extra="forbid")` (schema.py:219), and the comparator now reports constraint conflicts with dotted attribute names — `changed_attrs.append(f"constraints.{constraint_attr}")` (comparator.py:435-436). Comparing the shipped `miappe/1.2` and `isa/1.0` profiles emits 5 such attributes (`constraints.min_length`, `constraints.max_length`, ...). A caller that reads `attributes_changed` off a reported conflict and builds `ConflictResolution(attribute='constraints.min_length', ...)` — exactly the flow docs/guides/spec-merge.md describes — makes `FieldSpec.model_validate` raise `ValidationError: constraints.min_length Extra inputs are not permitted` (confirmed by direct execution). The exception is uncaught inside `SpecMerger.merge`, so one bad resolution aborts the entire merge rather than being reported as an unresolved conflict. The same happens for any mistyped attribute name.

**Fix:** Handle dotted `constraints.<attr>` paths explicitly (apply into `data['constraints']`), and wrap the `model_validate` call so an unusable resolution appends to `unresolved`/`warnings` instead of propagating a ValidationError out of the merge.

### `src/metaseed/specs/merge/reports.py:277` — HTMLReportGenerator interpolates spec content into HTML without escaping

*correctness · specs-merge*

Every value written by `HTMLReportGenerator` comes from profile YAML and is inserted raw: `lines.append(f"<td>{ed.entity_name}</td>")` (line 431), `f"<strong>{fd.field_name}</strong>"` (462), `f"<td>{val}</td>"` (476) where `val` is an arbitrary attribute value (`description`, `pattern`, `example`, `label`, ...), and `f"<th>{profile_id}</th>"`. The output is returned to the browser with `media_type="text/html"` from `GET /explore/report/...` (ui/routes/explore.py:190-196). Profile specs are not all first-party — a user specs directory or hub-authored profile can contain `<script>`. The sibling HTML-emitting module `ui/routes/dcat.py` escapes every interpolation with `html.escape`, so this file also diverges from the established pattern.

**Fix:** Escape all interpolated values with `html.escape(str(value))` (a small `_esc` helper used by every f-string in this class), and add a test that a field description containing `<script>` appears escaped in the generated HTML.

### `src/metaseed/specs/predicates.py:325` — _applicable_entities matches entity names exact-case while _target_entities in the same module normalizes, so when/require rules are silently unchecked

*consistency · specs*

`_target_entities` (line 407) resolves `applies_to` through the shared normalizer `applies_to_entity`, and its docstring states the reason explicitly: "matching exact-case here while the engine normalises is how a rule gets checked under one reading and run under another." `_applicable_entities` (line 325), which feeds the `when`/`require` checks, does the opposite — a raw `profile.entities[name]` lookup keyed on exact spelling.

Reproduced on a profile with entity `SampleType` and two identical rules differing only in the spelling of `applies_to`:

    applies_to: sample_type -> no issues reported
    applies_to: SampleType  -> "predicate names field 'nope', which the entity does not declare; the rule would never fire"
                               "requires field 'also_nope', which SampleType does not declare"

So the load-time guard that `profile_predicate_issues` exists to provide ("a predicate naming a field that does not exist is a rule that never fires") is skipped for any `when`/`require` rule written with a snake_case or differently-cased entity name, which is exactly the spelling variation `comparable_entity_name` was introduced to absorb.

**Fix:** Resolve the names in `_applicable_entities` through `applies_to_entity` / `comparable_entity_name`, the same way `_target_entities` does, keeping the deliberate `applies_to: all` -> `[]` behaviour. Add a test that a `when`/`require` rule scoped as `sample_type` against entity `SampleType` reports the same issues as the PascalCase spelling.

### `src/metaseed/ui/dataset_manager.py:141` — import_data's docstring contradicts _restore_state_from_data, which preserves the previous current-dataset pointer

*correctness · ui-core*

`import_data` documents: "Unlike load_dataset, the data does not originate from the repository and is not marked as the current saved dataset." It is true that `self._current` is left alone — but it delegates to `_restore_state_from_data`, which deliberately *carries the old pointer across the reset*:

```python
current = self._state._current_dataset
self._state.reset()
self._state._current_dataset = current
```

The comment justifies that for restore-in-place polling (`/api/graph`, `/api/validate`), which is a genuine need — but for an *upload of a different dataset* it means `state._current_dataset` still names the previously open dataset. `auto_save` reads that pointer (datasets.py:321), so the next edit after an upload writes the uploaded content into the previously open dataset file. The route (`/import`) does not clear it either.

**Fix:** Split the two behaviours: give `_restore_state_from_data` a `keep_current: bool` parameter (True for `load_dataset` and the polling restores, False for `import_data`), or have `import_data` explicitly `self._state._current_dataset = None` after restoring. Then make the docstring match.

### `src/metaseed/ui/dataset_manager.py:251` — DatasetManager reaches for the global notifier while EntityService gets one injected

*consistency · ui-core*

`DatasetManager.auto_save` does `from metaseed.ui.websocket import notify_state_changed` inside the method and calls the module-level singleton, whereas `create_app` composes `EntityService(..., notifier=notify_state_changed)` (app.py:80-83) — i.e. the same collaborator is injected in one place and discovered in the other. A host that wants a different notification transport (SSE, a message bus, none at all) can substitute it for the entity service but not for the dataset manager, and a test cannot observe auto-save notifications without patching the module.

**Fix:** Give `DatasetManager.__init__` a `notifier: Callable[..., None] | None = None` parameter and have `DatasetManagerFactory` pass through whatever it was composed with, defaulting to `notify_state_changed`.

### `src/metaseed/ui/dataset_manager.py:258` — auto_save swallows ValueError and OSError with a bare pass

*correctness · ui-core*

```python
try:
    result = self.save_dataset(name)
    ...
except (ValueError, OSError):
    pass
```

This is the path every UI edit takes (crud.py calls `auto_save` after create/update/delete). A disk-full, permission, or invalid-derived-name failure means the user's edit is never persisted and neither the log nor the UI says so — the WebSocket notification is also skipped, so the page keeps showing the in-memory state as if it had been saved. This is exactly the class of silent failure the project rules target ("swallowed exceptions"; a failed save must not look like a successful one).

**Fix:** At minimum `logger.warning("Auto-save of %r failed: %s", name, exc)`. Better: let the caller decide — return a success flag or re-raise a typed `AutoSaveError` so the route can surface a notification.

### `src/metaseed/ui/dataset_manager.py:336` — Private members reached across module boundaries (_resolve_factory, facade._spec/_loader, state._current_dataset)

*design · ui-core*

Several cross-module private accesses in this group, all of which make the real interface invisible in the signatures:

- dataset_manager.py:336 — `from .datasets import _resolve_factory` imports another module's underscore-private function.
- dataset_manager.py:120-137 — `self._state._current_dataset`, `self._state._invalidate_cache()` reach into AppState privates; datasets.py:297/302 do the same via `getattr(state, "_current_dataset", None)` / direct assignment, which is why the accessor pair `get_current_dataset_name`/`set_current_dataset_name` exists as free functions rather than as AppState properties.
- state.py:236-246 — `facade._spec` and `facade._loader.load_profile(...)` reach into ProfileFacade privates to find the root entity.
- state.py:163 — `facade._instances` in `_rebuild_cache`.

These are the seams a host would need to substitute, and none of them is a supported interface.

**Fix:** Promote the ones that are genuinely interface: a `current_dataset` property on `AppState`; a public `root_entity`/`spec` accessor on `ProfileFacade`; a public `resolve_factory()` in datasets.py (the docstring already treats it as the module's contract). Keep an import-scanning gate test for underscore-imports across `metaseed.ui` modules.

### `src/metaseed/ui/helpers/entity_helpers.py:134` — extract_nested_from_tree re-decides which parent field references a child type, with last-match instead of linking.py's first-match

*design · ui-core*

```python
type_to_field = {v: k for k, v in helper.nested_fields.items()}
```

ADR 005 states that `facade/linking.py` owns "which parent field references a child of a given type", and `linking.target_reference_field` states the rule explicitly: "the *first* declared nested field whose target names the child's type carries the reference." Inverting the dict takes the **last** such field instead.

So for a parent declaring two nested fields of the same child type (`Study.samples` and `Study.control_samples` both `items: Sample`), the facade writes the reference into the first field while the edit form groups the child rows under the second. The inline table for the linked field renders empty and the child appears in the wrong table.

The existing gate test (tests/test_tree_linking_is_owned_once.py) only greps for `single_entity_fields`, so it does not catch a second home for the *field-selection* half of the rule — a rule that exists as prose in linking.py's module docstring but has no gate.

**Fix:** Call `metaseed.facade.linking.target_reference_field(helper, child.entity_type)` per child instead of inverting the map, and widen the gate test to also fail on `nested_fields.items()` inversions outside `facade/`.

### `src/metaseed/ui/helpers/navigation_helpers.py:146` — build_breadcrumb hardcodes root-relative URLs, ignoring base_url

*design · ui-core*

The breadcrumb builds absolute paths with no prefix:

```python
"url": f"/form/{node.entity_type}/{node.id}",
...
url = f"/nested/{ctx.parent_entity_type}/{ctx.field_name}/{ctx.row_idx}"
```

`create_app` takes `base_url` precisely so a host can mount the UI under a prefix (`"/hub"`), and every template renders links as `{{ base_url }}/form/...` (templates/index.html:34, base.html:20). But `components/breadcrumb.html` emits `hx-get="{{ item.url }}"` verbatim, so under a mounted deployment every breadcrumb link 404s. The function has no access to `base_url` at all — it only takes `state`.

This is the "hardcoded endpoints / entry points a host cannot reach" case: the component is usable only from metaseed's own root-mounted page.

**Fix:** Pass `base_url` into `build_breadcrumb(state, base_url="")` (the routes already have it via `create_app`'s closure) and prefix both URLs, or prefix in the template as every other template does. Add a test that creates the app with `base_url="/hub"` and asserts the breadcrumb URLs are prefixed.

### `src/metaseed/ui/helpers/table_helpers.py:149` — build_inline_tables re-loads the profile spec from disk per nested field instead of using the facade's spec

*design · ui-core*

```python
ref_fields = get_reference_fields(
    profile=state.profile,
    version=facade.version,
    entity_type=nested_type,
)
```

`get_reference_fields` constructs a fresh `SpecLoader` and reads the YAML off disk on every call, and this call sits inside a loop over every nested field of the entity being rendered — so opening one form re-parses the whole profile spec N times.

More importantly it is a *discovered* dependency rather than the injected one: `ProfileFacade` may have been constructed with an injected spec (`facade._spec`, the path `AppState.get_root_entity_types` checks for), e.g. a draft spec or a hub-supplied one. In that case the inline tables are built from a different spec than the entities were validated against. `EntityHelper.reference_fields` already exposes the same information off the facade the caller is holding.

**Fix:** Resolve reference fields through the facade: `getattr(facade, nested_type).reference_fields` returns `{field: (target_entity, target_field)}`. If the validation-rule fallback is still needed, get it from the facade's spec rather than reloading from disk.

### `src/metaseed/ui/helpers/validation.py:198` — Child parent-reference is filled with a guessed value, discarding the declared target field

*correctness · ui-core*

`process_reference_linked_children` picks the child's back-reference field but throws away the field it is declared to point at:

```python
for ref_field, (target_type, _) in child_helper.reference_fields.items():
    if target_type == entity_type:
        parent_ref_field = ref_field
```

`EntityHelper.reference_fields` is `{field_name: (target_entity, target_field)}` (facade/helper.py:207) — the discarded `_` *is* the field whose value must be copied. `_clean_item_for_child_entity` then writes `cleaned[parent_ref_field] = parent_identifier`, where `parent_identifier` is computed by the caller as `parent_data.get("alias") or parent_data.get("unique_id")` (ui/routes/crud.py:188) — two hardcoded field names.

So for a profile declaring e.g. `Sample.study_ref -> Study.identifier` on a parent that carries both `identifier` and `unique_id`, the child is saved pointing at the wrong value, and the facade's reference linking (`_link_by_reference_fields`) will then fail to match it to its parent.

facade/store.py:_fill_parent_reference makes the same decision correctly — it reads `target_field` off the parent instance and refuses to guess ("rather than a name convention, so it works for any reference field regardless of naming"). This module is a second, divergent home for that decision, which is what ADR 005 exists to prevent.

**Fix:** Keep the declared target: `for ref_field, (target_type, target_field) in child_helper.reference_fields.items()` and pass `(parent_ref_field, target_field)` down so `_clean_item_for_child_entity` writes `getattr(parent_instance, target_field)`. Better: expose store.py's `_fill_parent_reference` decision from facade/linking.py and call it from both places, then extend the ADR-005 gate test to cover it.

### `src/metaseed/ui/routes/api.py:30` — Profile-spec parsing duplicated with divergent split rules and error contracts across api.py and explore.py

*consistency · ui-routes*

`api.py::_parse_profile_strings` splits on "/" and rejects anything without exactly two parts; `explore.py::_parse_profile_specs` (line 21) splits with `maxsplit=1` and accepts a version containing "/". The same input therefore validates differently depending on which route receives it. The error contracts diverge too: `/api/compare` (api.py:306) maps `ValueError` and `SpecLoadError` to 500, `/api/merge` (api.py:382-391) maps `ValueError` to 400 and `SpecLoadError` to 500, and all three explore handlers map both to 400 with comments claiming "Same contract as /api/merge" - which is only half true. This is one behaviour implemented twice.

**Fix:** Move one parser into a shared module (e.g. `metaseed.specs.merge` or a small `routes/_profiles.py`), use it from both route modules, and settle on a single status for a caller-supplied profile that fails to load (400, per the explore comments).

### `src/metaseed/ui/routes/crud.py:316` — MIAPPE-specific miappe_version autofill hardcoded four times in generic route code

*design · ui-routes*

`if "miappe_version" in helper.all_fields: values["miappe_version"] = facade.version` appears at crud.py:316-318 and three times in forms.py (97-98, 153-155, 215-217). A profile-specific field name is baked into the generic form layer of a library whose stated aim is reuse across MIAPPE, ISA, Darwin Core, ENA, PRIDE and DiSSCo, and it is copy-pasted rather than shared, so any change (e.g. a second profile wanting the same behaviour, or a rename) must land in four places. Related profile-specific hardcoding: `root_entity or "Investigation"` at examples.py:88 and the `"root_entity": "Investigation"` fallback at core.py:91 - "Investigation" is not a universal root entity (Darwin Core and PRIDE have others), so the fallback silently mislabels a profile whose spec fails to load.

**Fix:** Express "this field is auto-filled with the profile version" as a marker in the profile spec (or a single helper such as `auto_filled_values(helper, facade)`) and call it from one place; drop the "Investigation" defaults in favour of surfacing the load failure.

### `src/metaseed/ui/services/sheet_style.py:186` — max() on an empty sequence crashes the whole Excel export for a whitespace-only cell value

*correctness · ui-services-and-spec-builder*

`_width` guards with `if value:` and then calls:

```python
widest = max(
    widest, min(len(str(value)), max(len(w) for w in str(value).split()))
)
```

A whitespace-only string (`" "`, a tab, a non-breaking-space-free indent) is truthy, but `" ".split()` is `[]`, so the inner `max()` raises `ValueError: max() iterable argument is empty` (verified). `_width` is called from `style_sheet`, which is called for every entity sheet in `build_workbook_from_facade`, so one such value in any field of any entity aborts the entire export with a 500 rather than producing a workbook.

Whitespace-only values are reachable: `build_workbook_from_facade` writes `str(value)` for whatever the entity data holds, and nothing strips field values on entry.

**Fix:** Guard the split: `words = str(value).split()` then `if words: widest = max(widest, min(len(str(value)), max(len(w) for w in words)))`.

### `src/metaseed/ui/spec_builder/predicate_form.py:107` — list_field_options names and documents "list-of-entity fields" but also returns single-entity fields

*naming · ui-services-and-spec-builder*

```python
def list_field_options(spec: ProfileSpec) -> list[dict[str, Any]]:
    """Every list-of-entity field in the profile, with the fields of its items."""
    for entity_name, entity in spec.entities.items():
        for field in entity.fields:
            item = spec.entities.get(field.items) if field.items else None
            if item is None:
                continue
            options.append({...})
```

The filter is "`items` names an entity", not "`type` is LIST". `FieldType.ENTITY` fields carry `items` too — e.g. `src/metaseed/specs/seek/1.0/profile.yaml:221` (`type: entity` / `items: Person`), `:290`, `:300`. The result feeds the *cardinality* field picker (`validation_rule_form.html:189`, the datalist for `name="field"` beside Min Items / Max Items), so the editor offers single-entity references as things a cardinality rule can count, which is meaningless — a min/max-items rule on a non-list field can never be satisfied meaningfully.

**Fix:** Filter on `field.type == FieldType.LIST` (or `field.is_nested() and field.type == FieldType.LIST`) so the name, the docstring and the behaviour agree; if entity-typed fields are wanted for the predicate-field selector but not the cardinality selector, return them under a separate key.

### `src/metaseed/ui/spec_builder/routes_main.py:115` — Clone route bypasses the injected SpecPersistence port; load_template is a dead abstract method

*design · ui-services-and-spec-builder*

`register_main_routes` takes an injected `persistence: SpecPersistence` and uses it for `list_templates()` / `list_user_specs()`, but the clone route goes straight to the filesystem:

```python
spec = clone_spec(profile, version)          # -> SpecBuilder.from_template -> SpecLoader (filesystem)
...
loader = SpecLoader()
spec_path = loader.find_profile_file(version, profile)
if spec_path:
    notes_path = spec_path.parent / "notes.md"
    if notes_path.exists():
        builder.notes = notes_path.read_text(encoding="utf-8")
```

Three consequences:

1. `SpecPersistence.load_template` (spec_persistence.py:98) is declared abstract and implemented in `spec_filesystem.py:112`, but grepping the whole tree shows **no caller** in src or tests. It is a port method nothing reaches — dead code by the project's "never implement something without connecting it" rule.
2. `start.html:74` links every *user* spec to `/spec-builder/clone/{name}/{version}`, which resolves through `SpecLoader`. A host injecting a non-filesystem `SpecPersistence` can list its user specs but cannot open any of them — the component is only usable inside metaseed's own filesystem layout, which the project rules call out as a defect.
3. Notes are written *through* the port (`persistence.save(spec, notes=...)`, routes_export.py:154, with a comment explaining exactly why the direct-path write was removed) but read back by direct disk access here. Under a non-filesystem backend, notes are saved and never seen again. The port has no notes-read method at all.

**Fix:** Load through the port: `spec = await persistence.load_template(profile, version)`, and add a notes-read counterpart to `SpecPersistence` (or have `load_template` return spec+notes) so both directions go through the same abstraction. Add an import-scanning gate test forbidding `SpecLoader` / `find_profile_file` inside `ui/spec_builder/`.

### `src/metaseed/ui/spec_builder/routes_main.py:203` — root_entity set from raw form text without checking the entity exists

*correctness · ui-services-and-spec-builder*

```python
spec.root_entity = cast("str", form_data.get("root_entity", "")).strip()
```

The library provides `SpecBuilder.set_root_entity` (builder.py:346) whose entire purpose is the guard this route skips:

```python
def set_root_entity(self, entity: str) -> None:
    """Set the root entity. The entity must already exist."""
    self._require_entity(entity)
    self._spec.root_entity = entity
```

Typing any string into the metadata form makes the profile's root point at a non-existent entity. Since a profile is a tree rooted at `root_entity`, the resulting spec builds datasets that can never reach any entity, and the mistake surfaces only much later at load time. `spec.version` on the line above has the same shape of problem: assignment bypasses the `_version_must_be_major_minor` field validator (no `validate_assignment` on `ProfileSpec`), so a non-`MAJOR.MINOR` version is accepted here despite the validator's docstring claiming every entry point agrees.

**Fix:** Call `SpecBuilder.from_spec(spec).set_root_entity(value)` inside a `try/except ValueError` and re-render the metadata form with the error; validate `version` by re-running `ProfileSpec.model_validate` on the mutated spec (or route metadata through `SpecBuilder.set_metadata` once that method itself revalidates).

### `src/metaseed/ui/spec_builder/routes_rules.py:235` — Rule CRUD bypasses SpecBuilder, so the UI permits duplicate rule names the library rejects

*consistency · ui-services-and-spec-builder*

`add_validation_rule` builds and appends a `ValidationRuleSpec` by hand:

```python
new_rule = ValidationRuleSpec(name=name, description="", applies_to="all")
builder.spec.validation_rules.append(new_rule)
```

and `delete_validation_rule` does `del builder.spec.validation_rules[idx]`. Meanwhile `SpecBuilder.add_rule` (builder.py:608) exists and enforces uniqueness:

```python
if any(r.name == name for r in self._spec.validation_rules):
    raise ValueError(f"Validation rule '{name}' already exists")
```

So the web UI creates duplicate-named rules that the MCP `spec_add_rule` path refuses. Once two rules share a name, `SpecBuilder.update_rule` / `delete_rule` — which key on name — can no longer address either one, and `_require_rule` resolves to the first silently.

The same file's `build_updated_rule` also assigns attribute-by-attribute onto a `model_copy`, whereas `SpecBuilder.update_rule` deliberately rebuilds via `ValidationRuleSpec.model_validate(merged)` with the comment "pydantic does not validate an assignment" — `ProfileSpec`/`ValidationRuleSpec` have no `validate_assignment`, so the UI path stores unvalidated values the library path would reject.

This is inconsistent with sibling routes: `routes_entities.py` and `add_field` in `routes_fields.py` do go through `SpecBuilder`.

**Fix:** Route rule create/update/delete through `SpecBuilder.add_rule` / `update_rule` / `delete_rule` (adding an index-addressed variant if the UI needs one), and surface the raised `ValueError` in `_rules_list_response` the way `add_entity` already does.

### `src/metaseed/validators/engine.py:198` — Malformed rules of a valid type are silently dropped, the failure mode _VALID_RULE_TYPES exists to prevent

*correctness · validators*

The module states at line 152 that an unknown `type:` is "rejected loudly rather than being silently dropped, which would let the rule never run and invalid data pass". `_create_rule_by_type` then does exactly the silent drop for well-typed but incomplete rules:

- `type: conditional` with neither `condition` nor a `when`/`require` pair → `return None` (line 199)
- `type: cardinality` with no `field` → `return None` (line 239)
- `type: date_range` whose operands cannot be resolved from `start_field`/`end_field` or the condition → `return None` (line 215)

None of these are caught at load time either: `profile_predicate_issues` only inspects rules carrying a `where` or a `when`. A profile with `type: cardinality` and a typo'd `field:` key therefore loads clean, runs clean, and enforces nothing.

**Fix:** Raise a `ValueError`/`SpecLoadError` naming the rule for each of these branches, consistent with the unknown-type branch, and cover them with load-time checks in `profile_predicate_issues`.

### `src/metaseed/validators/engine.py:250` — Rule-level `reference:` declarations are enforced nowhere, despite the comment claiming DatasetValidator reads them

*correctness · validators*

`_create_rule_by_type` returns None for `reference` rules, justified by:

```python
# Both are enforced over the whole tree by DatasetValidator (_validate_uniqueness, _validate_
# references), which reads the rule spec directly. Building an engine rule
# here would produce one that can never fire.
```

This is true for uniqueness (`DatasetValidator._load_uniqueness_rules` does read `profile_spec.validation_rules`), but false for references: `_load_reference_fields` (dataset.py:289) reads only entity **field** specs (`f.reference`) and never looks at `profile_spec.validation_rules[].reference`. Nor does `loader._merge_rule_constraints_into_fields` mirror `reference` onto fields — it copies only pattern/enum/minimum/maximum. So a profile that declares a reference at the rule level and not on the field (a shape the schema explicitly supports, `ValidationRuleSpec.reference`, and which ena/1.0 and isa-miappe-combined/0.1 both use) has that constraint silently unenforced on every path. The shipped profiles happen to also declare it on the field, which is what hides the gap.

**Fix:** Either mirror rule-level `reference` onto the target field at load time (as pattern/enum already are), or make `DatasetValidator._load_reference_fields` also read `profile_spec.validation_rules`; then correct the comment. Add a test with a rule-level-only reference to gate it.

### `src/metaseed/validators/engine.py:719` — create_engine_for_entity constructs its own SpecLoader, so the profile YAML is re-parsed for every entity node

*design · validators*

```python
def create_engine_for_entity(entity, version="1.2", profile="miappe") -> ValidationEngine:
    loader = SpecLoader()
```

`SpecLoader`'s profile cache is per-instance (`self._profile_cache = {}`, loader.py:143), so a fresh loader means a fresh read + `yaml.safe_load` + `ProfileSpec.model_validate` + `profile_predicate_issues` of the whole profile. `DatasetValidator._validate_entity.validate_node` calls this once per node of the tree, and then builds *another* `SpecLoader(profile=self.profile)` at line 731 instead of reusing `self._loader`; `api._validate_nested` does the same per nested record. Validating a dataset with N entities parses and re-validates the profile roughly 2N times.

Beyond cost, this is the discovered-collaborator pattern the project rules forbid: the engine reaches out to build its own loader rather than accepting one, so a host application cannot substitute a cached or differently-rooted loader.

Secondary: the constructed loader is `SpecLoader()` (default profile `miappe`) while `profile` is passed explicitly to every call on it — harmless today, but it diverges from the `SpecLoader(profile=profile)` idiom used in api.py and dataset.py.

**Fix:** Add an optional `loader: SpecLoader | None = None` parameter to `create_engine_for_entity` (defaulting to a module-level or caller-supplied instance), and pass `self._loader` from `DatasetValidator` and the loader already built in `api._validate_nested`.

## Low (50)

### `src/metaseed/agent/core.py:382` — Values that fail conversion on non-required fields are dropped without any issue reported

*correctness · agent-core*

```python
converted = self._convert_value(value, field_spec)
if converted is not None:
    instance[field_spec.name] = converted
elif field_spec.required and value:
    errors.append(ValidationIssue(... f"Row {row_idx}: Failed to convert value '{value}'" ...))
```

An optional integer field carrying `"n/a"`, or an optional boolean carrying `"unknown"`, converts to None and is silently omitted from the instance: no key, no `ValidationIssue`, nothing in `ExtractionResult.errors`. The user sees a successful extraction with data missing. This contradicts the surrounding design, where `_to_boolean`'s comment insists that "'N/A' silently stored as False is data corruption" — the value is instead silently discarded. The required-field branch is also gated on `value` being truthy, so a required field whose raw value is `0`/`""` reports nothing either.

**Fix:** Emit a `ValidationIssue` (kind="value") for every failed conversion, independent of `field_spec.required`, and let the caller decide what blocks.

### `src/metaseed/agent/mcp/manager.py:62` — start(transport="stdio") promises a server no client can ever reach

*naming · agent-core*

`start()` advertises `transport: Transport type ("stdio" or "streamable-http")`, but for stdio it spawns `metaseed mcp --transport stdio --host ... --port ...` as a detached `Popen` with `stdout=log_file, stderr=log_file`. A stdio MCP server communicates over its own stdin/stdout; redirected to a log file and detached, it can never be spoken to. `is_running()` then reports it alive off `_process.poll()`, and `get_connection_url()` returns None with no explanation. No caller in src or tests passes "stdio", so this is an aspirational parameter documenting a capability the code cannot deliver.

**Fix:** Reject `transport="stdio"` with a clear error (a manager that spawns detached background processes can only manage HTTP transports), or delete the parameter branch.

### `src/metaseed/agent/mcp/manager.py:130` — self._log_path is written and never read

*dead-code · agent-core*

`self._log_path = log_path` is assigned inside `start()`. Grep across src, tests and docs finds exactly one occurrence — this assignment. It is not declared in `__init__` (so it does not exist on a manager that has never started a server), is not on `MCPServerStatus`, and the fail-fast branch reads the local `log_path` instead. Dead state that also breaks the class's own invariant that all instance attributes are initialised in `__init__`.

**Fix:** Delete the assignment, or expose the log path (initialise it to None in `__init__` and surface it on `MCPServerStatus`) so the UI can point users at the server log.

### `src/metaseed/agent/mcp/manager.py:359` — get_connection_url returns None for a server started with transport="http"

*correctness · agent-core*

`start()` accepts both spellings and normalises only the child's CLI argument:

```python
"http" if transport == "streamable-http" else transport
...
self._transport = transport
```

so `start(transport="http")` stores `_transport = "http"`. `get_connection_url` then tests `if transport == "streamable-http"` and falls through to `return None`, while `status()` reports `running=True`. A caller that used the "http" spelling — as metaseed's own test does at tests/test_agent/test_mcp_manager_pipes.py:51 — gets a running HTTP server with no connection URL and no error.

**Fix:** Normalise the transport once on entry to `start()` (store the canonical `"streamable-http"`), or accept both spellings in `get_connection_url`.

### `src/metaseed/agent/mcp/tools/entities.py:662` — bulk_update_entities aborts the whole batch on a non-ValueError, unlike batch_create

*consistency · agent-mcp-tools*

The per-item handler in `bulk_update_entities` is:

    try:
        result = service.update_entity(node_id, data)
        ...
    except ValueError as e:
        results.append({"id": node_id, "status": "error", "message": str(e)})

while the structurally identical loop in `batch_create` (line 760) catches `Exception` per item and keeps going. Any item raising something outside the `ValueError` hierarchy — e.g. an `AttributeError` because one array element is a bare string rather than an object, so `item.get("id")` explodes — escapes to the outer handler, discards every per-item result already accumulated, skips the auto-save, and returns a single opaque `{"error": ...}`. The caller cannot tell which updates succeeded. The two batch tools should fail the same way.

**Fix:** Catch `Exception` per item in `bulk_update_entities` (routing through `_handle_validation_error` as `batch_create` does), and validate the item shape before calling `.get`.

### `src/metaseed/agent/parsers/excel.py:51` — Workbook handle leaks when sheet parsing raises

*correctness · agent-core*

```python
workbook = load_workbook(filename=str(path), read_only=True, data_only=True)
...
for sheet_name in sheet_names:
    table = self._parse_sheet(sheet, sheet_name)
...
workbook.close()
```

`close()` is not protected. A read-only workbook holds the backing zip file open, and openpyxl raises on malformed sheets and on cell values it cannot coerce, so any failure inside `_parse_sheet` leaks the file descriptor. The module already reasons carefully about the read-only workbook's file lifetime (the `sheet_names` comment two lines above), which makes the missing guard an oversight rather than a deliberate choice. The sibling CSV and JSON parsers both use `with open(...)`.

**Fix:** Wrap the loop in `try: ... finally: workbook.close()`.

### `src/metaseed/api/__init__.py:49` — __all__ promises a name 'app' that does not exist, breaking star-import of the public API package

*dead-code · api-brapi*

`metaseed/api/__init__.py` lists `"app"` in `__all__` but nothing named `app` is imported or defined in the module. Verified:

    $ python -c "import metaseed.api as a; print([n for n in a.__all__ if not hasattr(a, n)])"
    ['app']

so `from metaseed.api import *` raises `AttributeError: module 'metaseed.api' has no attribute 'app'`. `tests/test_public_api.py` guards this exact class of bug (`test_...` asserting every name in `__all__` resolves) but only for the top-level `metaseed.__all__`, so the sub-package's broken promise is ungated. This is a rule with no gate, in the module that defines the project's public surface.

**Fix:** Remove `"app"` from `__all__`. Extend the existing resolvability test in tests/test_public_api.py to iterate over every metaseed sub-package that defines `__all__` (at minimum `metaseed.api` and `metaseed.brapi`), so a stale name fails CI.

### `src/metaseed/cli/commands/example.py:290` — "Latest version" of an example is chosen by lexicographic sort instead of the project's `version_sort_key`

*correctness · cli*

`example_key = sorted(matching)[-1]  # Latest version` sorts version strings as text. The codebase already owns the fix for exactly this: `metaseed.specs.versioning.version_sort_key`, whose docstring says "Both 'latest version' answers sorted version strings as text, so releasing 1.10 after 1.9 made *latest* step backwards to 1.9", and which is used by `specs/loader.py:465` and `ui/spec_filesystem.py:188`. This module reimplements the broken form. With today's shipped examples (miappe 1.1/1.2, pride 1.0/2.0) the answers happen to coincide, so nothing fails yet; adding an example under `miappe/1.10` makes `metaseed example miappe` silently resolve to 1.9/1.2 instead.

**Fix:** `example_key = max(matching, key=lambda k: version_sort_key(k.split("/", 1)[1]))` using `from metaseed.specs.versioning import version_sort_key`, and add a regression test with a 1.9/1.10 example pair.

### `src/metaseed/dcat/serialize.py:202` — A publisher identified only by URI or email is dropped from the graph

*correctness · exporters*

`if dataset.publisher and dataset.publisher.name:` (and the identical guard at line 220 for the catalog) gates emission on `name` alone. `_add_agent` was written precisely to honour `agent.uri` (its docstring: "the catalog previously always minted a blank node, discarding a publisher URI the dataset would have honoured"), and `DcatAgent` allows any of name/email/uri. A host supplying `PublicationContext(publisher=DcatAgent(uri="https://ror.org/XXXX"))` - the machine-readable form a DCAT-AP consumer wants - gets no `dct:publisher` triple at all, with no error.

**Fix:** Change both guards to `if dataset.publisher and (dataset.publisher.name or dataset.publisher.uri or dataset.publisher.email):`, or push the emptiness test into `_add_agent` and have it return `None` for a wholly empty agent.

### `src/metaseed/facade/helper.py:327` — get_label documents an algorithm derive_label does not implement

*docstring · facade*

The docstring promises a preference order:

```
- title (for Investigation, Study)
- name (for Person, Factor)
- first_name + last_name (for Person)
- unique_id / identifier
- Falls back to first non-empty string field from spec
```

The body delegates entirely to `metaseed.repositories.helpers.derive_label`, which does none of that: it picks the field marked `is_label`, else the FIRST spec field, and falls back to `"New {entity_type}"` — never to "first non-empty string field". The two fallbacks also differ: `get_label` returns `f"{self._name}"` for a non-model/non-dict input while `derive_label` returns `f"New {entity_type}"`.

**Fix:** Replace the invented list with a one-line statement that the rule is owned by `derive_label` and a cross-reference, and align the non-model fallback with `derive_label`'s.

### `src/metaseed/facade/store.py:80` — add_entity raises KeyError or AttributeError for an unknown entity type depending on skip_validation

*correctness · facade*

`EntityStore._create_instance` takes two different routes: `skip_validation=True` goes through `self._get_helper` (raises `KeyError`), otherwise through the injected creator, which is `ProfileFacade._create_instance` using `getattr` (raises `AttributeError`). Both `ProfileFacade.add_entity` and `EntityStore.add_entity` document only `Raises: AttributeError`.

Verified:

```
skip_validation=False -> AttributeError: Entity 'Banana' not found in miappe v1.2. Available: ...
skip_validation=True  -> KeyError: "Entity type 'Banana' not found"
```

A caller catching the documented `AttributeError` leaks `KeyError` on the draft path. The facade already has `require_helper`, whose whole purpose is a corrective, vocabulary-listing error, and neither path uses it.

**Fix:** Route both branches through one resolution point — `require_helper` — so an unknown type always raises the same `ValueError` with the profile's supported types, and update the `Raises:` sections. Gate with a test asserting identical behaviour for both values of `skip_validation`.

### `src/metaseed/logging.py:84` — get_logger is a no-op wrapper that contradicts the module's own documented guidance and splits the codebase into two idioms

*dead-code · core-top-level*

`get_logger(name)` is `return logging.getLogger(name)` and nothing else. The module docstring three lines above it states the opposite policy:

```
All modules should use the standard logging pattern:

    import logging
    logger = logging.getLogger(__name__)
```

The tree has followed both: `grep -c 'logging.getLogger(__name__)' src/metaseed` = 17, `grep -c 'get_logger(__name__)' src/metaseed` = 4 (seek/fairds.py, facade/store.py, agent/mcp/tools/entities.py, validators/engine.py). A wrapper that adds no behaviour but creates a second way to do the same thing is the kind of divergence the consistency rule exists to prevent, and `configure_logging` works identically for both since it configures the `"metaseed"` parent logger.

**Fix:** Delete `get_logger`, convert the four call sites to `logging.getLogger(__name__)`, and drop it from `tests/test_logging.py`. If it is kept for API stability, mark it with `@deprecated` (which is what deprecation.py is for) rather than leaving two live idioms.

### `src/metaseed/models/factory.py:491` — _create_field_definition's ENTITY branch is byte-identical to the fallthrough it precedes

*dead-code · importers-and-models*

```python
if field.type == FieldType.ENTITY:
    annotated_type = (
        Annotated[python_type, Field(**constraints)] if constraints else python_type
    )
    return (annotated_type | None, None)

annotated_type = (
    Annotated[python_type, Field(**constraints)] if constraints else python_type
)
return (annotated_type | None, None)
```

The two blocks compute and return exactly the same thing, so the ENTITY test changes nothing. It reads as if entity fields were handled specially, which is misleading for anyone extending the factory.

**Fix:** Delete the `if field.type == FieldType.ENTITY:` block.

### `src/metaseed/models/factory.py:504` — create_model_from_spec is annotated -> type instead of -> type[BaseModel], forcing a cast at the call site

*typing · importers-and-models*

`def create_model_from_spec(spec: EntitySpec) -> type:` returns a class built with `create_model(..., __base__=EntityBaseModel)`, i.e. always a `type[BaseModel]`. The weak annotation is why models/__init__.py:83 has to write `return cast("type[BaseModel]", create_model_from_spec(spec))`, and why every other caller (facade/core.py:177, validators/api.py:43/349) gets an untyped class back. This is public API of the module.

**Fix:** Annotate `-> type[BaseModel]` and delete the `cast` (and the now-unused `cast` import) in models/__init__.py.

### `src/metaseed/models/registry.py:11` — ModelNotFoundError is never raised anywhere; the suppress that names it can never fire and get_model's Raises section is wrong

*dead-code · importers-and-models*

A grep over the whole repo finds no `raise ModelNotFoundError`. Its only three references are: the class definition (registry.py:11), `contextlib.suppress(SpecLoadError, ModelNotFoundError)` in factory.py:142, and the re-export plus a docstring claim in models/__init__.py:25/52 ("Raises: ... ModelNotFoundError: If the model cannot be generated."). The comment at factory.py:137-138 asserts "The loader (get_model) signals an unresolvable entity with SpecLoadError / ModelNotFoundError" — get_model signals only SpecLoadError. registry.py therefore exists solely to hold an exception nothing can produce, and get_model's Raises section documents behaviour that cannot occur.

**Fix:** Delete ModelNotFoundError and registry.py, drop it from the suppress tuple and from models/__init__.py's __all__ and docstring — or raise it where a model genuinely cannot be generated. Either way, one of the two must happen; today it is a rule that can never fire.

### `src/metaseed/repositories/dataset_repository.py:83` — validate_dataset_name accepts a trailing newline, weakening the path-traversal choke point

*correctness · repositories*

`re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", name)` — in Python `$` also matches immediately before a trailing newline, so `"mydata\n"` validates. `FilesystemDatasetRepository._get_path` documents itself as "the single choke point shared by save/load/delete/exists" and relies entirely on this function, so the guarantee it states (only safe names reach the filesystem) is not the guarantee the regex gives. The result is a dataset file literally named `mydata\n.json`, which `list()` then reports under a name that no longer round-trips through `_get_path`.

**Fix:** Use `re.fullmatch(...)` or anchor with `\Z` instead of `$`.

### `src/metaseed/repositories/file.py:31` — DEFAULT_DATASETS_DIR in file.py is unused and duplicates the constant in filesystem_dataset.py

*dead-code · repositories*

`DEFAULT_DATASETS_DIR = user_data_base() / "datasets"` plus its six-line docstring has no reference anywhere in `src` or `tests` (grep: only `filesystem_dataset.DEFAULT_DATASETS_DIR` is used and patched). The module's own `from_dataset_name` correctly calls `default_datasets_dir()` from `filesystem_dataset`, exactly so the `METASEED_DATASETS_DIR` override applies. Leaving a second identically-named constant here is a live trap: an import of `metaseed.repositories.file.DEFAULT_DATASETS_DIR` bypasses the env override. The docstring is also changelog prose ("It was hardcoded to ``~/.local/share`` in two places") rather than a description of the value.

**Fix:** Delete the constant from `file.py`; `filesystem_dataset.DEFAULT_DATASETS_DIR` / `default_datasets_dir()` is the single source.

### `src/metaseed/repositories/file.py:122` — _get_facade ignores a changed version, so reload() can leave a facade pinned to the old profile version

*correctness · repositories*

`if self._facade is None or self._facade.profile != self._profile:` compares only the profile. `_load` reassigns `self._version = data.get("version", self._version)` (line 136) and is reachable after facade creation via `reload()` (line 475). Loading a file recorded against version "1.1" into a repository whose facade was built for the latest version keeps the stale facade, so validation, label derivation and reference resolution run against the wrong spec version while `_version` reports the new one.

**Fix:** Include the version in the guard: `if self._facade is None or self._facade.profile != self._profile or self._facade.version != self._version:` — or set `self._facade = None` at the end of `_load`.

### `src/metaseed/repositories/file.py:183` — FileEntityRepository reaches into the private helper._spec instead of using EntityHelper.get_label

*design · repositories*

Three sites access a private attribute of another module's class: `spec = helper._spec` (line 183), `derive_label(entity_type, validated_data, spec=helper._spec)` (line 335) and the same at line 386. `EntityHelper` exposes no public `spec` property, but it does expose `get_label(instance)` (`facade/helper.py:330-350`), which accepts a dict and delegates to this very `derive_label` with its own spec. `MemoryEntityRepository` does not reach into `_spec` at all, so the label path is inconsistent between the two backends as well as encapsulation-breaking.

**Fix:** Replace all three with `helper.get_label(data)`; if a spec is genuinely needed elsewhere, add a public `spec` property to `EntityHelper` rather than reading `_spec`.

### `src/metaseed/repositories/file.py:475` — reload() has no caller in src; the cross-process synchronization it documents never happens

*dead-code · repositories*

`reload()` documents "Call this to sync with external changes (e.g., from MCP)" and the class docstring promises "Multiple processes can share the same file for state synchronization", but grep over `src/` finds no call — the only callers are `tests/test_repositories/test_file_repository.py:197,483`. `FileEntityRepository` itself is never constructed anywhere in `src/` either (only re-exported from `repositories/__init__.py`); the UI and MCP server both build `MemoryEntityRepository`. As written, the advertised UI↔MCP file-sharing mode is a capability nothing reaches, which the project rules classify as dead code however correct it is.

**Fix:** Either wire the file backend into a real entry point (a host/composition-root option that selects it, with `reload()` called on the read paths that need freshness), or drop `reload()` and soften the class docstring to describe what the class actually does.

### `src/metaseed/repositories/spec_draft_store.py:111` — MemorySpecDraftStore.load and create hand out the stored object, so callers mutate the store without save()

*correctness · repositories*

`load` returns `self._drafts[draft_id]` and `create` returns the object it just stored; `SpecDraftData.spec_data` is the same dict the store holds. A caller that loads a draft, mutates `spec_data`, then abandons the edit has already changed the store — and a database-backed implementation of the same `AsyncSpecDraftStore` port cannot behave that way, so behaviour diverges across adapters of one contract. `FileEntityRepository` goes to the opposite extreme (`copy.deepcopy` on every read path, lines 273, 281, 360, 392, 459), which shows the intended semantics for a repository read.

**Fix:** Return `copy.deepcopy(draft)` from `load`, `create` and `save`, and deep-copy `spec_data` on the way in, so the in-memory adapter matches the value semantics any out-of-process adapter necessarily has.

### `src/metaseed/seek/__init__.py:24` — Eager `import_from_seek` import makes the whole package require httpx, defeating the lazy `__getattr__` machinery

*correctness · seek*

The module docstring promises: "The pure JSON:API payload builders (:mod:`metaseed.seek.payloads`, re-exported here) import without the ``metaseed[seek]`` extra", and `__getattr__` (lines 66-76) exists solely to defer `SeekClient`/`fairds` until httpx/rdflib are needed. But line 24 is an unconditional top-level import:

    from metaseed.seek.importer import import_from_seek

and `importer.py:22` does `from metaseed.seek.client import SeekApiError` at module level, which imports `client.py`, which raises `ModuleNotFoundError` at line 22-24 when httpx is absent. So `from metaseed.seek import assay_payload` fails without the extra.

Verified by executing with httpx blocked:

    FAIL: ModuleNotFoundError No module named httpx

The whole lazy-import design in this file is therefore inert.

**Fix:** Move `import_from_seek` into the `TYPE_CHECKING` block and the `__getattr__` dispatch alongside `SeekClient`/`client_from_settings` (add a branch for `name == "import_from_seek"` importing `metaseed.seek.importer`). Add a gate test that imports `metaseed.seek.payloads` symbols with `httpx` and `rdflib` masked out of `sys.modules`, so this contract has an enforcement mechanism rather than only a docstring.

### `src/metaseed/seek/client.py:406` — `SeekClient.create_assay` has no caller anywhere in src or tests

*dead-code · seek*

Grepped the whole tree for `create_assay\b` (excluding `create_isa_assay`): the only hit is the definition at `client.py:406`. The sync path uses `create_isa_assay` exclusively (`placement.py:256`, `placement.py:281`) because, as `create_isa_assay`'s own docstring explains, "``POST /assays`` cannot do this: ``assay_stream_id`` is absent from its permitted params... so it answers 200 and discards the link, leaving an assay that belongs to no stream."

So `create_assay` is not merely unused — it is the method the codebase documents as unusable for this adapter's purpose, and it is not exposed through `IsaWriter` either. `payloads.assay_payload` remains reachable (it is in `__init__.__all__` and directly tested), so only the client method is dead.

Compare `create_study` (line 393), which at least has a test caller; `create_assay` has none.

**Fix:** Delete `SeekClient.create_assay`. If a plain non-ISA assay is a capability worth keeping, connect it to something and say in the docstring when it is correct to use instead of `create_isa_assay`.

### `src/metaseed/seek/isa_types.py:49` — Two different `AttributePlan` dataclasses with the same name in the same package

*naming · seek*

`provision.AttributePlan` (provision.py:63) and `isa_types.AttributePlan` (isa_types.py:49) are distinct, non-interchangeable types with overlapping-but-different fields:

- provision: `title, attribute_type_title, required, is_title, pos, pid, cv_title, allow_cv_free_text`
- isa_types: `title, attribute_type_title, isa_tag, required, is_title, pos, field_name, enum`

Both are consumed inside `metaseed.seek` — `placement.py` imports `sample_type_attribute_plans` (isa_types plans) while also importing `cv_ids_for_entity` from provision, and `templates.py` imports `AttributePlan` from `isa_types` under `TYPE_CHECKING`. Nothing in either name says which projection it belongs to, so a reader (or a future import) can silently pick the wrong one; a mypy error is the only thing standing between the two.

**Fix:** Rename to reflect the destination each plans for, e.g. `provision.SampleTypeAttributePlan` (the PID/FDS route) and `isa_types.IsaAttributePlan` (the ISA-tagged route), matching the two routes the module docstrings already distinguish.

### `src/metaseed/seek/provision.py:143` — `build_provisioning_plan` is documented "pure, deterministic" but performs network I/O when a term source is given

*docstring · seek*

The summary line reads:

    """Project ``profile`` onto SEEK CVs + Sample Types (pure, deterministic).

and the module docstring repeats ":func:`build_provisioning_plan` — pure, deterministic projection". With `term_source` supplied (which the UI does — `ui/routes/seek.py:236` passes `get_term_source()`), `_cv_terms` calls `term_source.search_sync(...)` once per enum value per CV field, i.e. an unbounded number of OLS round-trips, and the result depends on what the remote service returns at that moment. Neither pure nor deterministic.

The outage behaviour happens to be safe today only because `TermRouter.search_sync` swallows per-source exceptions (`services/terms.py:327-334`) and returns `[]`. That safety is not stated in `_cv_terms`, and the type annotation is the bare `TermSource` protocol — any adapter injected directly (which the docstring explicitly invites: "the application's router, or any adapter") that raises on a network failure will abort the entire plan build rather than degrading to label-only CV terms.

**Fix:** Correct the summary to say the projection is deterministic given the term source's answers, and note the I/O. Then make the degradation the caller was promised ("a deployment with no network still provisions (label-only)") actually hold for any adapter: wrap the `search_sync` call in `_cv_terms` in a try/except that logs and falls through to `iri=None`, so an outside service's downtime cannot fail the provisioning plan.

### `src/metaseed/seek/provision.py:233` — `provision` binds to the concrete `SeekClient` while its sibling `sync` depends on the `IsaWriter` port

*design · seek*

`ports.py` states the rationale clearly: ":mod:`metaseed.seek.sync` depends on this protocol rather than on :class:`metaseed.seek.client.SeekClient`, so a test can substitute a double that the type checker holds to the same surface." `sync.py:63` and `placement.placeholder_sample_type_id` both honour that.

`provision.py` does not: `resolve_cv_ids(client: SeekClient, ...)` (line 233) and `execute_provisioning_plan(client: SeekClient, ...)` (line 273) annotate the concrete class. Between them they use only `find_controlled_vocab_id_by_title`, `create_controlled_vocab`, `sample_attribute_type_id`, `find_sample_type_id_by_title` and `create_sample_type` — three of which are already on `IsaWriter`. A host application (or a test double) that satisfies the port is rejected by the type checker for the provisioning half of the same adapter.

**Fix:** Add a `VocabularyWriter` (or extend `IsaWriter`) protocol in `ports.py` covering `find_controlled_vocab_id_by_title` and `create_controlled_vocab`, and annotate both provision entry points against the protocol. This is the same one-line-per-method change that already exists for the sync side.

### `src/metaseed/seek/sync.py:78` — `cv_ids` documented as keyed by field name, but its only producer emits `Entity.field` keys

*docstring · seek*

`sync_dataset_to_seek`'s docstring says:

    cv_ids: ``field name -> Controlled Vocabulary id`` for the dataset's enum
        fields, from a provisioning run.

The producer, `provision.resolve_cv_ids`, deliberately does the opposite (provision.py:249-252): "Keyed \"Entity.field\", keeping the namespacing _cv_title built: a bare field name reused across entities collapsed two distinct SEEK CVs into whichever entity iterated last." `cv_ids_for_entity` exists precisely to narrow those namespaced keys per entity.

A caller following the docstring literally — passing bare field names — lands in the `elif "." not in key` legacy branch of `cv_ids_for_entity` and silently reintroduces the cross-entity CV collision the namespacing was added to fix. The docstring documents the bug, not the fix.

**Fix:** Change the parameter description to `"<EntityType>.<field name>" -> Controlled Vocabulary id, as produced by metaseed.seek.provision.resolve_cv_ids`, and state that bare field-name keys are accepted only as a deprecated fallback (or drop that fallback branch in `cv_ids_for_entity` if nothing relies on it — grep shows only `resolve_cv_ids` and tests feed it).

### `src/metaseed/seek/values.py:141` — `profile_of` reaches through two layers of private state instead of using an injected interface

*design · seek*

in_memory = getattr(client._facade, "_spec", None)
    return in_memory or SpecLoader().load_profile(client.version, client.profile)

This reads `MetaseedClient._facade` (private) and then `ProfileFacade._spec` (private), and falls back to constructing its own `SpecLoader` — a discovered implementation, not an injected one. Both `sync.sync_dataset_to_seek` (line 91) and `fairds._profile_index` (line 147) go through it, so the SEEK adapter is coupled to the internal layout of two other layers. Any rename inside `ProfileFacade` silently degrades this to "load from disk", which for an imported/derived dataset (the `importer.py` case this exists for) means loading the wrong profile or raising.

The project rule is explicit: "Depend on injected interfaces, never on discovered implementations... a component that reaches out to find its collaborator... has a hidden dependency that no boundary test can express". This also blocks the reusability aim: a host application holding a profile some other way cannot supply it.

**Fix:** Expose the spec as public API on `MetaseedClient` (e.g. a `spec` / `profile_spec` property that returns the in-memory `ProfileSpec` or loads it), and have `profile_of` read that single public accessor — or accept an optional `profile: ProfileSpec` parameter on `sync_dataset_to_seek` / `to_fair_data_station_rdf` so a caller can inject it. Back it with an import-scanning gate test that fails on `_facade`/`_spec` access from `metaseed.seek`.

### `src/metaseed/services/ontology.py:167` — RateLimiter.acquire (async) has no production caller

*dead-code · services*

The module docstring states the async twins were removed: "This adapter is synchronous; async access goes through TermRouter". Every call site in `src/` uses `acquire_sync` (ontology.py:353, 446, 549, 619). Grepping the whole source tree for `acquire` outside this file returns nothing; the only caller of `await limiter.acquire()` is tests/test_services/test_ontology.py:93-95. Per the project rule, code that no interface reaches is dead code however correct it looks, and a test exercising it does not connect it. It also carries an `asyncio.Lock()` created in `__init__` (line 165) that is unused by the sync path and binds the limiter to an event loop it may never see.

**Fix:** Delete `RateLimiter.acquire` and `self._lock`, and drop the corresponding test; or connect it by making an async entry point actually use it.

### `src/metaseed/services/terms.py:305` — Sources dropped from a search for failing or for not supporting `within` are never reported to the caller

*consistency · services*

`docs/architecture/term-sources.md:121` and this module's own docstring ("a shorter list of results is indistinguishable from there being less to find") make reporting a skip a stated rule. `search_sync` drops a source in three ways: not interactive (line 309), cannot honour a branch (line 317-325), and raised an exception (line 328-335). Only the first is reportable — `not_interactive()` (line 186) is derived purely from declared capabilities, and `ui/routes/api.py:608` sends exactly that as `not_asked`. Because neither `LocalVocabulary` nor `VocabularyStore` implements a `within` parameter, *every* branch-scoped picker query (`/api/ontology/search?within=...`) silently excludes all local vocabularies — the precise case the local-first design exists for — and the dialog reports nothing. The same applies to a source that raised: the UI shows a short list with `not_asked: []`.

**Fix:** Have `search_sync` accumulate the names of sources it actually skipped (with the reason) and expose them, e.g. return them alongside the hits or record them on the router, and have `/api/ontology/search` report that set as `not_asked` rather than the static `not_interactive()` list.

### `src/metaseed/services/terms.py:346` — _search_within misreads any TypeError from inside an adapter as "cannot restrict to a branch"

*correctness · services*

```python
try:
    return list(searches(query, ontology, limit, within=within))
except TypeError:
    return None
```

The `TypeError` is intended to mean "this adapter has no `within` parameter", but it also catches a `TypeError` raised anywhere inside a supporting adapter's implementation, and inside `list()` consuming its result. `OntologyService.search_sync` parses untyped JSON from OLS (`doc.get("description") or [""])[0]`, ontology.py:397) — a shape change there raises `TypeError`, and the caller then logs "cannot restrict to a branch; skipped" and silently drops OLS from the results instead of surfacing a failure.

**Fix:** Detect support with `inspect.signature` (or a declared capability on the protocol) instead of catching the call's exception, or narrow the guard by inspecting the signature first and letting exceptions from the call propagate to the surrounding handler.

### `src/metaseed/specs/loader.py:230` — A profile.yaml whose top level is not a mapping raises TypeError instead of SpecLoadError

*correctness · specs*

`_load_profile` guards only `data is None` (line 225) before doing `if "spec_version" not in data: data["spec_version"] = "0.1"` (lines 230-231). A `profile.yaml` holding a list or a bare scalar passes the None check and then fails with a raw TypeError that escapes the module's error contract:

    profile.yaml = "- just\n- a list\n"  -> TypeError: list indices must be integers or slices, not str
    profile.yaml = "just a string\n"     -> TypeError: 'str' object does not support item assignment

Every documented failure of this method is `SpecLoadError` (docstring lines 206-208), and callers catch that: `persistence._list_specs` catches `SpecLoadError` to fall back to a placeholder listing, so one malformed user spec takes down the whole profile listing instead of degrading. `load_from_string` handles the same case correctly because it hands the value straight to `model_validate`.

**Fix:** After the None check, add `if not isinstance(data, dict): raise SpecLoadError(f"Invalid profile {profile_path}: top level must be a mapping, got {type(data).__name__}")`, with a test that a list-valued profile.yaml raises SpecLoadError.

### `src/metaseed/specs/merge/merger.py:158` — Merged profile drops spec_version and ontologies, mis-declaring the spec format

*correctness · specs-merge*

The merged `ProfileSpec` is constructed with only `version, name, display_name, description, ontology, root_entity, validation_rules, entities`. `ProfileSpec.spec_version` therefore falls back to its default "0.1" and `ProfileSpec.ontologies` (the prefix -> OntologyDefinition map, spec_version 0.2+) is silently discarded. Verified: `merge([('miappe','1.2'),('isa','1.0')])` produces `spec_version='0.1'` although the sources declare 0.5 and 0.6, while the merged entities still carry spec_version 0.6+ markers (`owns`, `is_identifier`, `isa_tag`). The CLI writes this straight to disk (`cli/commands/merge.py:161`), so the emitted YAML claims a format version older than the constructs it uses, which is precisely what `_version_hint` in loader.py:523-538 and `SUPPORTED_SPEC_VERSION` exist to reason about.

**Fix:** Carry the highest `spec_version` among the source profiles onto the merged spec, and merge (or at least union) the source `ontologies` maps; add a test asserting the merged spec_version is >= max(source spec_versions).

### `src/metaseed/ui/app.py:74` — create_app hardcodes DatasetManagerFactory(), so a host cannot inject its own repository

*design · ui-core*

```python
dataset_factory = DatasetManagerFactory()
```

`create_app(state=None, base_url="")` has no parameter for the dataset factory or repository, yet dataset_manager.py's module docstring advertises exactly that capability: "allows repository implementation to be swapped (e.g., for metaseed-hub database backend)". `DatasetManagerFactory.__init__` already accepts `sync_repo`; there is simply no way to get one in through `create_app`. A host embedding the UI must either monkeypatch `app.state.dataset_factory` after construction or accept the filesystem repository.

The same applies to `run_ui`, which serves the module-level `app = create_app()` singleton, so it cannot serve a caller-supplied state or repository either.

Given "reusability by other applications is a MAJOR AIM" and "depend on injected interfaces", the composition root should take the collaborator rather than construct it.

**Fix:** Add `dataset_factory: DatasetManagerFactory | None = None` to `create_app` (defaulting to `DatasetManagerFactory()`), and give `run_ui` an `app: FastAPI | None = None` parameter. Add a boundary test constructing the app with an in-memory/temp-dir repository and asserting saves land there.

### `src/metaseed/ui/helpers/validation.py:158` — process_reference_linked_children handles all nested fields, not only reference-linked children

*naming · ui-core*

The function's own docstring says: "This covers both spec-defined nested fields (`Run.files`) and reference-linked children, since both resolve to a child entity type for the field." It iterates every key in `state.current_nested_items`, resolves the child type via `infer_entity_type_from_field` (which reads `nested_fields`), and creates/updates a node for each — the reference field is optional (`parent_ref_field` may be None and the code proceeds anyway).

The name promises a narrow reference-linking pass; the code is the general "materialize nested rows as child nodes" pass. The module docstring repeats the wrong scope ("helper functions for processing reference-linked children"). Callers in crud.py have a comment explaining the real behaviour, which is the tell that the name is not carrying it.

**Fix:** Rename to something honest — `materialize_nested_children` or `persist_nested_items_as_children` — and update the module docstring, `__all__`, helpers/__init__.py and the crud.py call sites.

### `src/metaseed/ui/routes/api.py:236` — /api/compare and /api/merge have no UI surface and no tests while a UI-facing twin exists

*design · ui-routes*

`/api/compare` and `/api/merge` (api.py:236, 312) duplicate what `/explore/compare` and `/explore/graph` already serve. Grep over templates, static JS, tests and docs finds no reference to either endpoint (`grep -rn "api/compare\|api/merge" src tests docs` matches only their definitions and two comments in explore.py). No test exercises them - a `merge()` regression, a change to `MergeResult.to_dict()`/`to_yaml()`, or the `hasattr(c, "entity_name")` probe at line 362 would fail only in production. Per the project rule, a capability reachable only from an API and covered by no test is unfinished work.

**Fix:** Either wire them into the explore page (and delete the duplicate compare implementation), or add route tests covering the success path, the <2-profile rejection and the unknown-profile path; if merge is genuinely not a shipped feature yet, remove the endpoint rather than leave it untested.

### `src/metaseed/ui/routes/api.py:393` — Section comment claims MCP is mounted in-process; it is not, and the endpoints drive a subprocess

*docstring · ui-routes*

The banner reads `# MCP Server Status (MCP is mounted in-process, always running)`, yet `create_app` (ui/app.py:44-167) mounts no MCP server - it only installs a shared `MCPContext` in the lifespan - and the three handlers below the banner call `get_mcp_manager().status()/.start()/.stop()`, which manage a spawned `subprocess` listening on port 8001 (agent/mcp/manager.py:62-205). If the comment were true, `/api/mcp/start` and `/api/mcp/stop` would be meaningless and `/api/mcp/status` would always report running; in fact static/js/mcp.js toggles a subprocess on and off. The comment misdescribes both the deployment model and what the buttons do.

**Fix:** Delete or rewrite the banner to state what these endpoints actually do (manage an out-of-process MCP server on port 8001), and note that entities created against that separate process do not share the UI's in-memory state.

### `src/metaseed/ui/routes/forms.py:100` — Two different definitions of "an example exists", plus three copies of the examples directory constant

*consistency · ui-routes*

forms.py decides whether to offer the example with `example_exists = (EXAMPLES_DIR / state.profile / facade.version).exists()`, while core.py's `_example_versions` (lines 33-44) requires `version_dir.is_dir() and any(version_dir.glob("*.yaml"))` and `load_example` (examples.py:65-69) 404s when the directory holds no YAML. A version directory that exists without a YAML file therefore renders a "Load Example" affordance that 404s - the exact failure core.py's docstring says it exists to prevent. The directory itself is defined three times: core.py:30 (`_EXAMPLES_DIR`), examples.py:28-29 and forms.py:33-34 (`UI_DIR`/`EXAMPLES_DIR`, byte-identical), each with its own `parent` chain to keep in step.

**Fix:** Export one `EXAMPLES_DIR` and one `has_example(profile, version) -> bool` from a single module (examples.py) and use it from core.py and forms.py.

### `src/metaseed/ui/routes/seek.py:57` — _facade_client bypasses the public MetaseedClient.from_facade and writes a private field

*design · ui-routes*

```python
def _facade_client(state: AppState) -> Any:
    client = MetaseedClient.__new__(MetaseedClient)
    client._facade = state.get_or_create_facade()
    return client
```
The sibling routes do exactly this through the public factory - import_export.py:121-124 even carries the comment "from_facade exists for exactly this: wrapping a facade the app already composed. __new__ plus a private attribute skipped the constructor and would silently break with it", and dcat.py:47 uses `MetaseedClient.from_facade(facade)`. seek.py is the one module still reaching into `_facade` from another layer; it is used on three code paths (`_context`, `seek_sync`, `seek_isa_rdf`), so any future state added to `from_facade` breaks all three silently.

**Fix:** Replace the body with `return MetaseedClient.from_facade(state.get_or_create_facade())`, and give the function a real return type (`MetaseedClient`) instead of `Any`.

### `src/metaseed/ui/spec_builder/predicate_form.py:32` — Operator vocabulary duplicated instead of derived from metaseed.specs.predicates

*consistency · ui-services-and-spec-builder*

```python
SET_OPERATORS = ("is_set", "is_not_set")
OPERATORS = ("==", "!=", "in", "not_in", ">", ">=", "<", "<=", *SET_OPERATORS)
```

`metaseed/specs/predicates.py` already owns both: `Operator` is the `Literal[...]` of exactly these ten strings (line 36) and `SET_OPERATORS: frozenset[str]` is defined at line 48 — this module even imports `Comparison`/`parse_predicate` from there but re-declares the vocabulary. The two agree today, so nothing is broken; the defect is that they can diverge silently. Adding an operator to the spec format leaves the editor's dropdown short and makes `predicate_from_rows` reject it with "Unknown operator" (line 90), while the same predicate loads fine from YAML. Per the project rule, this is a duplicated rule with no gate.

**Fix:** Derive both: `from metaseed.specs.predicates import SET_OPERATORS, Operator` and `OPERATORS = get_args(Operator)`; drop the local tuples. Order for the dropdown can be imposed on the derived set if presentation order matters.

### `src/metaseed/ui/spec_builder/routes_export.py:113` — Unescaped spec name interpolated into the Content-Disposition header

*correctness · ui-services-and-spec-builder*

```python
filename = f"{builder.spec.name or 'profile'}.yaml"
return StreamingResponse(..., headers={"Content-Disposition": f'attachment; filename="{filename}"'})
```

`ProfileSpec.name` is an unconstrained `str` (schema.py:527) written from raw form input by `update_profile_metadata` (routes_main.py:196) and by `apply_yaml_edit`/`import_yaml`. A name containing `"`, `;`, `/`, CR or LF breaks or injects into the response header. The sibling exporter already recognises the problem — `services/export.py:300` sanitises the entity id with `.replace("/", "-").replace(":", "-")[:30]` before putting it in a filename.

**Fix:** Sanitise to a safe slug (allow `[A-Za-z0-9._-]`, bound the length) before interpolating, or use Starlette's `FileResponse`-style quoting / `filename*=UTF-8''<percent-encoded>` form.

### `src/metaseed/ui/spec_builder/routes_fields.py:234` — delete_field and move_field bypass SpecBuilder while add_field goes through it

*consistency · ui-services-and-spec-builder*

`add_field` correctly delegates (`SpecBuilder.from_spec(builder.spec).add_field(...)`, line 81, with a comment about the parent identifier and back-reference the builder creates), but the three sibling routes mutate the model directly:

```python
del entity.fields[idx]                                   # delete_field, line 234
entity.fields[idx], entity.fields[idx - 1] = ...          # move_field_up, line 252
entity.fields[idx], entity.fields[idx + 1] = ...          # move_field_down, line 272
```

`SpecBuilder.delete_field` (builder.py:573) and `SpecBuilder.move_field` (builder.py:585) exist and are what the MCP `spec_delete_field` / `spec_move_field` tools use. Two code paths for the same operation means any future improvement to deletion (e.g. cleaning up the auto-created back-reference on the target entity, which `add_field` creates but nothing removes) lands only on the library side and the web UI silently keeps the old behaviour. Same for `update_entity` in `routes_entities.py:130-131`, which sets `entity.description` / `entity.ontology_term` directly instead of calling `SpecBuilder.update_entity`.

**Fix:** Delegate to `SpecBuilder.delete_field(entity_name, field.name)` and `SpecBuilder.move_field(entity_name, field.name, "up"|"down")` (resolving the name from `idx` first), and to `SpecBuilder.update_entity` for entity metadata. Extend the existing `tests/test_ui_does_not_reimplement_the_library.py` gate to cover these builder operations.

### `src/metaseed/ui/spec_builder/routes_main.py:196` — cast("str", form_data.get(...)) lies about the type and raises AttributeError on a file part

*typing · ui-services-and-spec-builder*

```python
spec.name = cast("str", form_data.get("name", "")).strip()
```

Starlette's `FormData.get` returns `str | UploadFile`. `cast` silences the type checker without any runtime check, so a multipart request carrying a file part named `name` / `version` / `description` / `root_entity` / `ontology` / `notes` reaches `.strip()` on an `UploadFile` and 500s. The same pattern repeats on lines 197-203 and 227.

The sibling route in the same package already solved this properly (`routes_export.py:125`):

```python
def _form_text(key: str) -> str | None:
    value = form_data.get(key)
    return value if isinstance(value, str) else None
```

**Fix:** Use the `_form_text` idiom from `routes_export.py` (ideally hoisted into `access.py` so both files share one copy) instead of `cast`.

### `src/metaseed/ui/spec_filesystem.py:229` — get_display_name picks the latest version with a text sort, the bug list_versions in the same class already fixed

*correctness · ui-core*

`FilesystemSpecProvider.get_display_name` selects the newest version with `latest_version = sorted(versions)[-1]`. Sixty lines above, `list_versions` in the same class explicitly rejects that approach:

```python
# Newest first, numerically: a text sort put "1.9" above "1.10".
from metaseed.specs.versioning import version_sort_key
return sorted(versions, key=version_sort_key, reverse=True)
```

A profile with versions `["1.9", "1.10"]` therefore reports the display name of 1.9 as the latest. Any profile that reaches a double-digit minor version gets the wrong display name, silently.

**Fix:** Use the same key: `latest_version = max(versions, key=version_sort_key)` (or `sorted(versions, key=version_sort_key)[-1]`), and add a regression test with `["1.9", "1.10"]`.

### `src/metaseed/validators/api.py:90` — validate() raises SpecLoadError for an unknown entity where validate_entity() returns a ValidationError

*consistency · validators*

`_validate_nested` calls `create_engine_for_entity(entity, version, profile=profile)` outside any handler, and that function raises `SpecLoadError(f"Entity not found: ...")` when the entity is in neither the entity specs nor the profile. The same is true of the `cascade=False` branch at line 209. Every other spec-load failure in the same function is deliberately swallowed (lines 109-112, 147-149), and the sibling public function `validate_entity` reports the identical condition as data:

```python
errors.append(ValidationError(field=entity_type, message=f"Unknown entity type: ...", rule="error"))
```

So two functions in the same module, both documented as "Returns: List of validation errors", disagree on whether an unknown entity is an exception or an error. Callers written against one break against the other.

**Fix:** Pick one contract for the module — returning a `ValidationError` is the one the rest of the package uses (`DatasetValidator` also swallows `SpecLoadError`) — and make `validate()` follow it, or document the raise in its docstring's Raises section.

### `src/metaseed/validators/cv.py:50` — validate_cv_terms resolves the term source itself, bypassing check_term's not-checked guard

*correctness · validators*

```python
if service is None:
    from metaseed.services.terms import get_term_source
    service = get_term_source()
```

`check_term` already handles `source is None`, and does so inside a `try/except` that converts a source which cannot be built (e.g. a malformed local vocabulary file) into `Outcome.NOT_CHECKED` with the explicit rationale "a configuration problem, not a verdict on this value. Crashing here buried the cause deep in a validator" (services/term_check.py:246-260). Resolving it here, unguarded, reinstates exactly that crash: a broken vocabulary configuration raises out of `validate_cv_terms` and therefore out of `metaseed.pride.validate_cv` / `metaseed.metabolights.validate_cv`, which are declared to return `list[ValidationError]`. The duplication also means the two resolution paths can drift.

**Fix:** Delete the local fallback and pass `service` straight through to `check_term`, which already treats `None` as "ask the configured router" and degrades safely.

### `src/metaseed/validators/dataset.py:204` — DatasetValidator.term_source is annotated Any on a public constructor

*typing · validators*

```python
def __init__(self, profile: str | None = None, version: str | None = None, term_source: Any = None) -> None:
```

The parameter is the injection point the docstring advertises ("a caller that must not do I/O ... supplies its own"), and it is passed straight to `check_entity_terms(..., self._term_source)`, whose parameter is `TermSource | None`. Annotating it `Any` means a caller supplying a wrong object gets no type error at the boundary, and the protocol a host must implement is undiscoverable from the signature.

**Fix:** Annotate it `TermSource | None` (importing `metaseed.services.term_check.TermSource` under `TYPE_CHECKING`, as cv.py already does), and store `self._term_source: TermSource | None`.

### `src/metaseed/validators/dataset.py:752` — Ontology NOT_CHECKED verdicts are discarded while unchecked references are reported as warnings

*consistency · validators*

In `_validate_entity.validate_node`:

```python
if not verdict.is_problem or not verdict.message:
    # NOT_CHECKED is not a fault in the data...
    continue
```

Not being a fault is right, but the verdict is then dropped entirely, so a dataset whose every ontology term went unverified (OLS down, or an ontology no configured source carries — the Crop Ontology case `term_check` documents at line 273) validates identically to one whose terms all resolved. The same class of information for references *is* reported, on the same result object: `_unchecked_references` emits one `reference_not_checked` warning per field precisely so "how much of a dataset went unverified" is not hidden. `DatasetValidationResult.warnings` is already the right channel; `_validate_entity` just cannot reach it because it returns a bare error list.

**Fix:** Have `_validate_entity` return (or accumulate) warnings too, and emit one aggregated `ontology_term_not_checked` warning per field, mirroring `_unchecked_references`.

### `src/metaseed/validators/engine.py:303` — Range rules discard the profile's declared rule name

*consistency · validators*

Every other rule built from a spec is given `rule_name=rule_spec.name` (`ConditionalRule`, `CoordinatePairRule`, `ListCardinalityRule`, `ConditionalRequirementRule`). `_range_rule` does not:

```python
return DateRangeRule(start_field=lower, end_field=upper, message=message)
...
return NumericRangeRule(lower_field=lower, upper_field=upper, message=message)
```

`DateRangeRule.name` and `NumericRangeRule.name` are hardcoded constants, so a MIAPPE rule declared as `name: study_date_order` surfaces as `rule="date_range"` in every `ValidationError` and `ValidationCheck`. `_range_rule` even accepts a `rule_name` parameter, but uses it only for the warning log at line 310. A consumer cannot map an error back to the profile rule that produced it, and two range rules on the same entity are indistinguishable.

**Fix:** Give `DateRangeRule` and `NumericRangeRule` the same `rule_name` constructor parameter the other rules have (defaulting to the current constant), and pass `rule_spec.name` through `_range_rule` from both call sites.

### `src/metaseed/validators/engine.py:592` — _child_collection_fields matches entity names on case alone, defeating its own purpose

*correctness · validators*

`_child_collection_fields` resolves the entity with `entity_lower = entity.lower()` and `n.lower()`, while its sibling `_profile_rules_for_entity` (same file, line 514) uses `comparable_entity_name`, which is imported at line 17 and documented in specs/schema.py as the one normaliser that exists because "comparing on case alone matched the root and missed every nested entity, silently disabling 54 shipped rules".

```python
entity_lower = entity.lower()
entity_def = next(
    (e for n, e in profile_spec.entities.items() if n.lower() == entity_lower),
    None,
)
if entity_def is None:
    return set()
```

The entity name reaching `create_engine_for_extracted_record` comes from `ExtractionContext.validate_instance`, which is fed the `entity` argument of the `validate_extracted` MCP tool (src/metaseed/agent/mcp/tools/validation.py:63) — i.e. arbitrary caller spelling. For `entity="observation_unit"` against a profile declaring `ObservationUnit`, `_profile_rules_for_entity` still finds the rules (it normalises) but `_child_collection_fields` returns an empty set, so the `ListCardinalityRule` exclusion at line 641 never fires and every extracted record is reported as "'samples' must have at least 1 item(s), but has 0" — precisely the failure the function's docstring says it prevents.

**Fix:** Use `comparable_entity_name` for both the entity lookup and the `f.items` membership test, exactly as `_profile_rules_for_entity` does.

## Appendix — unverified lower-confidence notes

Low-severity findings, reported by a reviewer but not put through the adversarial pass. Treat as leads, not conclusions.

- `pyproject.toml:66` — The dcat and ena extras declare unbounded dependencies
- `src/metaseed/adapters.py:141` — Two spellings of an empty-tuple dataclass default in the same class
- `src/metaseed/agent/core.py:158` — ValidationIssue.kind is an unconstrained str where validators.base.Kind is the authority
- `src/metaseed/agent/mapping.py:240` — mapping_to_dict / mapping_from_dict round-trip is lossy and asymmetric
- `src/metaseed/agent/mcp/caller.py:30` — Return annotation `Any | None` collapses to `Any`
- `src/metaseed/agent/mcp/server.py:13` — Module docstring lists validate_extracted under the extraction tool group
- `src/metaseed/agent/mcp/tools/__init__.py:10` — Package __init__ omits register_spec_builder_tools
- `src/metaseed/agent/mcp/tools/datasets.py:96` — Duplicate except branches with identical bodies
- `src/metaseed/agent/mcp/tools/entities.py:191` — Helper uses stdlib logging with f-strings and Any-typed service parameter, unlike its sibling
- `src/metaseed/agent/mcp/tools/extraction.py:69` — Some tools let exceptions escape as MCP protocol errors while every sibling returns a JSON error
- `src/metaseed/agent/mcp/tools/profiles.py:104` — _identifier_info re-implements identifying_field, annotates entity_def as Any, and its docstring omits the is_identifier rule
- `src/metaseed/agent/mcp/tools/spec_builder.py:37` — Module helpers lack docstrings and the field-tool docstrings omit three accepted markers
- `src/metaseed/agent/mcp/tools/validation.py:138` — The checks/errors serialization block is duplicated verbatim in validate_entity and _validate_node_recursive
- `src/metaseed/agent/parsers/excel.py:85` — Falsy-but-real header cells are replaced by synthetic column names
- `src/metaseed/agent/parsers/registry.py:16` — ParsedContent mixes mutable-literal defaults with Field(default_factory) in one model
- `src/metaseed/api/base.py:19` — InstanceDataMixin declares a _facade attribute it never uses
- `src/metaseed/api/client.py:449` — Public accessors facade and get_model are annotated Any despite the concrete types being known
- `src/metaseed/api/entities.py:33` — Entity.label uses a first-string heuristic while the rest of the API uses the profile's label rule
- `src/metaseed/api/errors.py:7` — Module docstring's exception hierarchy omits InvalidSpecError
- `src/metaseed/api/serialization.py:104` — serialize() silently falls back to flat format for any unrecognised format value
- `src/metaseed/brapi/__init__.py:63` — study_db_id filter trusts the requested id instead of the server's answer
- `src/metaseed/brapi/export.py:143` — builders map is typed tuple[str, Any] instead of the concrete callable type
- `src/metaseed/brapi/mapper.py:238` — DataFile unique_id derived from the URL basename collides across studies
- `src/metaseed/cli/app.py:126` — `validate` and `convert` default `--entity` to "investigation", a MIAPPE/ISA-specific root
- `src/metaseed/cli/app.py:150` — Redundant function-local re-import of `SpecLoadError` shadowing the module-level import
- `src/metaseed/cli/app.py:211` — Unrecognized `--format` / `--transport` values fall through silently instead of erroring like sibling commands
- `src/metaseed/cli/app.py:485` — `migrate-specs` suppresses the failure exit code in dry-run mode while its sibling `migrate` does not
- `src/metaseed/cli/commands/example.py:48` — `flatten_entity`'s `parent_fields` parameter is never supplied by any caller
- `src/metaseed/cli/commands/example.py:266` — Example selection takes an arbitrary file when a version directory holds more than one YAML
- `src/metaseed/cli/commands/example.py:345` — Unreachable `ImportError` handler advising `pip install openpyxl`, which is a hard dependency
- `src/metaseed/cli/migrate.py:16` — `is_node_id` annotated `value: str` but designed and tested for arbitrary values
- `src/metaseed/cli/migrate.py:166` — Migration reports use bare `print()`, sending `[ERROR]` lines to stdout unlike every other CLI output path
- `src/metaseed/cli/migrate.py:199` — `__main__` block duplicates the wired `metaseed migrate` command with weaker behaviour
- `src/metaseed/cli/migrate_specs.py:446` — A failed directory rename is reported as "could not write the spec" while the write already succeeded
- `src/metaseed/dcat/export.py:61` — Undocumented fallback stamps the profile name as the dataset identifier
- `src/metaseed/dcat/export.py:68` — to_dcat weakens catalog_metadata to Any and omits both host parameters from its docstring
- `src/metaseed/dcat/model.py:53` — DcatDistribution.description is modelled but never serialized
- `src/metaseed/deprecation.py:55` — The @deprecated decorator has no call site in src/, so the deprecation policy it exists to enforce is unenforced
- `src/metaseed/facade/core.py:163` — _load_entities mutates a process-global model context instead of passing it
- `src/metaseed/facade/core.py:317` — EntityStore exposes no public accessor for all instances, so three call sites reach into _instances
- `src/metaseed/facade/core.py:391` — Unreachable None check on load_profile's result
- `src/metaseed/facade/core.py:442` — from_yaml re-implements read_yaml instead of using it
- `src/metaseed/facade/helper.py:28` — validate_ontology_term is annotated str but None is a supported and tested input
- `src/metaseed/facade/helper.py:198` — child_fields duplicates the body of owned_child_fields
- `src/metaseed/facade/node.py:44` — EntityNode.label is a third, divergent label rule
- `src/metaseed/facade/store.py:17` — store.py uses metaseed.logging.get_logger while the documented project convention and its sibling use logging.getLogger
- `src/metaseed/facade/store.py:51` — The injected instance_creator is bypassed for drafts because its type cannot carry skip_validation
- `src/metaseed/facade/store.py:309` — update_entity re-indexes but never re-resolves parentage or fixes references naming the old identifier
- `src/metaseed/forms/__init__.py:20` — __all__ omits two public functions that downstream code re-exports
- `src/metaseed/forms/__init__.py:41` — The forms module's central contract -- the entity helper -- is typed Any despite the codebase using Protocol for exactly this
- `src/metaseed/forms/__init__.py:197` — collect_form_values calls .lower() on an unconverted value for boolean fields
- `src/metaseed/isatab/__init__.py:0` — to_isatab has no adapter entry, so ISA-Tab export is unreachable for ISA-shaped profiles other than metabolights
- `src/metaseed/isatab/__init__.py:262` — Term Accession Number is emitted with an always-blank Term Source REF and no declared ontology source
- `src/metaseed/isatab/__init__.py:303` — Three near-identical tree descents, two of them in this file
- `src/metaseed/isatab/__init__.py:376` — Study and assay documents collide silently on duplicate names
- `src/metaseed/metabolights/client.py:30` — USER_AGENT constant is copied into five client modules while _http is the shared home
- `src/metaseed/metabolights/export.py:42` — _maf_filename can collide, silently dropping one assay's MAF from the returned mapping
- `src/metaseed/metabolights/export.py:80` — _metabolite_children_by_assay keys by the Metabolite's parent, whatever its type, not by Assay
- `src/metaseed/models/factory.py:258` — EntityBaseModel docstring claims a "JSON serialization mode" the model_config does not set
- `src/metaseed/models/factory.py:377` — TYPE_MAP entries for LIST and ENTITY are unreachable
- `src/metaseed/models/types.py:1` — Module docstring scopes the type to MIAPPE although every profile uses it
- `src/metaseed/paths.py:60` — get_user_config_path creates the data directory as a side effect of resolving a path
- `src/metaseed/pride/export.py:13` — Module docstring enumerates the line types but omits FMH, which the module emits
- `src/metaseed/pride/export.py:236` — SDRF instrument column renders the literal string "None" when the instrument has no name
- `src/metaseed/pride/mapper.py:26` — _taxon_id returns the raw string when the accession carries no prefix, despite promising a numeric tax id
- `src/metaseed/pride/validate.py:58` — Validators reach into their sibling exporter's private helpers via function-local imports
- `src/metaseed/profiles/factory.py:49` — list_versions builds a throwaway SpecLoader per call, bypassing the instance's own loader and its cache
- `src/metaseed/repositories/__init__.py:0` — Package exports omit CatalogMetadata and the tree protocols while exporting their siblings
- `src/metaseed/repositories/dataset_repository.py:168` — Changelog commentary in source and an incomplete module docstring
- `src/metaseed/repositories/file.py:322` — create_entity mutates the caller's data dict before copying it
- `src/metaseed/repositories/filesystem_dataset.py:58` — Inconsistent annotations: __init__ lacks a return type and Self, find_parent_ref_field takes Any where siblings take EntityHelper
- `src/metaseed/repositories/filesystem_dataset.py:111` — list() mixes ISO timestamps and raw epoch floats in DatasetInfo.modified, breaking the documented ordering
- `src/metaseed/repositories/filesystem_dataset.py:133` — save() validates the name twice
- `src/metaseed/seek/context.py:113` — `placeholder_type_id` comment references a private name that does not exist
- `src/metaseed/seek/payloads.py:19` — The `DEFAULT_ASSAY_TYPE_URI` comment sits above `SHARING_LEVELS` and reads as documentation for it
- `src/metaseed/seek/placement.py:180` — A missing ISA Template is reported once per Study/Assay instead of once per level
- `src/metaseed/seek/preview.py:67` — `_field_is_cv` duplicates `attribute_types.is_cv_field`
- `src/metaseed/seek/provision.py:57` — `CvPlan.description`, `CvPlan.ols_root_term_uris` and `AttributePlan.allow_cv_free_text` are never set by their only producer
- `src/metaseed/seek/sync.py:123` — `assay_role_entities` unions a set with its own superset
- `src/metaseed/seek/values.py:61` — Docstring points at `metaseed.seek.provision._LIST_FALLBACK_TITLE`, which does not exist
- `src/metaseed/seek/values.py:98` — Function-local imports diverge from the module-level / TYPE_CHECKING convention used across the package
- `src/metaseed/seek/values.py:127` — Missing docstrings on `values.title_of` and `placement.collect_file`
- `src/metaseed/services/__init__.py:0` — The package exports only the OLS adapter, not the composition API a reusing application needs
- `src/metaseed/services/local_terms.py:138` — VocabularyStore carries a duplicated @dataclass decorator
- `src/metaseed/services/ontology.py:98` — Every method annotates `self: Self`, an idiom used nowhere else in the package
- `src/metaseed/services/ontology.py:307` — get_cache_stats reimplements expiry with a different comparison than CacheEntry.is_expired
- `src/metaseed/services/ontology.py:570` — is_within_sync never caches a negative or unknown outcome, so an ontology OLS does not host is re-fetched once per value
- `src/metaseed/services/ontology.py:616` — has_ontology_sync has a cached-None branch that can never be taken
- `src/metaseed/services/terms.py:26` — A module-private constant is imported across module boundaries
- `src/metaseed/services/terms.py:59` — TermHit.iri is undocumented and silently dropped by to_dict
- `src/metaseed/services/terms.py:142` — TermRouter.sources is typed list[Any], erasing the port it is built around
- `src/metaseed/services/terms.py:280` — "nearest first" claims a relevance ordering that neither the router nor the local store implements
- `src/metaseed/settings.py:100` — get_adapter_config declares dict[str, str] but returns whatever JSON held
- `src/metaseed/specs/field_form.py:22` — The tier vocabulary is declared a third time in field_form instead of being owned by schema.py
- `src/metaseed/specs/field_form.py:119` — An unrecognized reference_scope is silently downgraded to dataset scope
- `src/metaseed/specs/loader.py:266` — SpecLoader.load / load_from_string have no production caller and no shipped input format
- `src/metaseed/specs/loader.py:347` — Profile-agnostic loader methods default to version "1.2", which only MIAPPE has
- `src/metaseed/specs/loader.py:463` — version_sort_key is imported inside the function while the module already imports from versioning at the top
- `src/metaseed/specs/merge/comparator.py:389` — Unreachable 'field absent from every profile' branches in comparator and merger
- `src/metaseed/specs/merge/merger.py:210` — _merge_entity_fields takes an unused _profile_specs parameter that its docstring still documents
- `src/metaseed/specs/merge/models.py:47` — FieldDiff.get_profile_value, EntityDiff.common_fields and EntityDiff.modified_fields have no callers
- `src/metaseed/specs/merge/strategies.py:273` — _all_or_none types its callable argument as Any
- `src/metaseed/specs/merge/visualizer.py:38` — build_diff_graph's show_unchanged parameter has no caller and no test
- `src/metaseed/specs/merge/visualizer.py:198` — Visualizer re-implements the nested-entity rule instead of using FieldSpec.is_nested()
- `src/metaseed/specs/merge/visualizer.py:217` — is_reference is a constant False where it is used, and a dual-purpose field yields two overlapping edges
- `src/metaseed/specs/merge/visualizer.py:288` — The 'Conflict' entity legend, colour and status icon can never be produced
- `src/metaseed/specs/persistence.py:46` — get_custom_specs_dir is a second name for get_user_specs_dir
- `src/metaseed/specs/versioning.py:70` — SUPPORTED_SPEC_VERSION names a gate that does not exist
- `src/metaseed/ui/__init__.py:38` — get_templates_dir has no caller and no test
- `src/metaseed/ui/app.py:77` — get_entity_service and MCPContext close over the local state while get_state reads app.state.ui_state
- `src/metaseed/ui/datasets.py:100` — list_datasets, delete_dataset and validate_dataset_name have no production caller
- `src/metaseed/ui/helpers/__init__.py:6` — Module docstring names submodules that do not exist and omits one that does
- `src/metaseed/ui/helpers/entity_helpers.py:152` — Comment describes a pluralization scheme the code does not use
- `src/metaseed/ui/helpers/navigation_helpers.py:62` — A spec that fails to load is reported as "this entity has no reference fields"
- `src/metaseed/ui/helpers/spec_builder_helpers.py:20` — Compatibility shim re-exports three names nothing imports from it
- `src/metaseed/ui/helpers/table_helpers.py:210` — __all__ omits infer_entity_type_from_field although it is a public cross-module import
- `src/metaseed/ui/helpers/validation.py:68` — _format_validation_error's first parameter is unused and documented as "reserved for future use"
- `src/metaseed/ui/helpers/validation.py:118` — _find_existing_child_node assumes every node instance is a Pydantic model
- `src/metaseed/ui/routes/api.py:61` — WebSocket handler only deregisters the connection on WebSocketDisconnect
- `src/metaseed/ui/routes/api.py:156` — Local `manager` shadows the module-level WebSocket manager import in nine handlers
- `src/metaseed/ui/routes/crud.py:348` — render_entity_form's docstring is inaccurate and its parameters undocumented, unlike its siblings
- `src/metaseed/ui/routes/dcat.py:82` — DCAT handlers are sync def while every sibling route module uses async def; `license` shadows a builtin
- `src/metaseed/ui/routes/explore.py:1` — explore.py, settings.py and seek.py import framework types at runtime instead of under TYPE_CHECKING
- `src/metaseed/ui/routes/forms.py:71` — An unknown ?profile= is silently ignored here but rejected with 400 in core.switch_profile
- `src/metaseed/ui/routes/validation.py:271` — _separate_field_values computes and returns simple_values that no caller uses
- `src/metaseed/ui/services/entities.py:136` — A failing notifier aborts the request after the repository has already been mutated
- `src/metaseed/ui/services/export.py:39` — Formula escape/unescape are asymmetric: a value already starting with an apostrophe loses it
- `src/metaseed/ui/services/export.py:62` — Scalar lists joined with ", " and split on "," — an element containing a comma does not survive the round trip
- `src/metaseed/ui/services/export.py:257` — Bare `except Exception` around spec loading, inconsistent with the importer's unguarded call
- `src/metaseed/ui/services/graph.py:6` — Module docstring calls itself a backward-compatibility shim when it is the only production path and adds behaviour
- `src/metaseed/ui/spec_builder/routes_entities.py:46` — Pointless `_require_entity = require_entity` rebinding in two route modules
- `src/metaseed/ui/spec_builder/routes_export.py:39` — register_export_routes docstring omits base_url, which the function uses
- `src/metaseed/ui/state.py:152` — Two live names for one operation: invalidate_cache and _invalidate_cache
- `src/metaseed/validators/__init__.py:32` — Package __all__ exports half the rule classes and omits Kind, which is part of ValidationError's public surface
- `src/metaseed/validators/api.py:20` — _pydantic_constraint_errors annotates entity_spec as Any
- `src/metaseed/validators/dataset.py:162` — _referenced_ids ignores non-string reference values that _collect_ids registers as strings
- `src/metaseed/validators/engine.py:124` — _get_rule_fields duck-types over rule attributes and reads another class's private _fields
- `src/metaseed/validators/predicates.py:32` — Local Predicate alias duplicates metaseed.specs.predicates.Predicate
- `src/metaseed/validators/rules.py:694` — ListCardinalityRule passes silently when the field holds a non-list
- `src/metaseed/validators/rules.py:871` — __all__ omits ConditionalRequirementRule
- `tests/test_brapi/test_conformance.py:36` — Conformance test passes vacuously when the live server returns nothing

## Appendix — refuted

Findings a verifier successfully refuted. Recorded so the same claim is not re-raised next review.

- src/metaseed/adapters.py:297 The seek adapter declares no actions and instead exposes a hardcoded UI route, defeating the registry's data-driven placement
- src/metaseed/adapters.py:393 importable_profiles does not honour the "*" wildcard that applies_to defines, so the two disagree
- src/metaseed/agent/mcp/server.py:75 set_mcp_state duplicates _build_default_context and re-inlines the binding context.py documents as a defect
- src/metaseed/agent/mcp/context.py:136 Lazy default-context build never binds the session's dataset factory to the UI
- src/metaseed/agent/mcp/context.py:157 on_change drops the session's dataset factory and lets auto_save resolve one ambiently
- src/metaseed/agent/mcp/tools/entities.py:233 _find_parent_from_references duplicates repository logic that already runs, and half its return value is discarded
- src/metaseed/agent/mcp/tools/profiles.py:78 Two divergent placeholder generators for the same concept in one file
- src/metaseed/api/validation.py:54 ADR 005 violation: _data_with_children re-decides the target reference field and the LIST-vs-ENTITY shape
- src/metaseed/brapi/__init__.py:85 Observation de-duplication compares the raw observationDbId but stores str(key), so non-string ids never dedupe
- src/metaseed/brapi/client.py:46 A server outage is reported as 'this URL is not a BrAPI endpoint'
- src/metaseed/cli/migrate_specs.py:212 `_value_token` misses tab-preceded YAML comments, so `--apply` deletes the comment it promises to keep
- src/metaseed/ena/client.py:79 read_run silently converts a non-list ENA response into an empty result
- src/metaseed/dcat/resolver.py:77 The `modified` parameter is never supplied, so dct:modified is never emitted
- src/metaseed/facade/core.py:89 list_versions is called without the profile, so an injected loader resolves versions for its own default profile
- src/metaseed/metabolights/mapper.py:331 Study-level Person/Publication entities are created under a Study the profile gives no field for, making them invisible in the UI
- pyproject.toml:29 httpx and anyio are imported directly by services but are not declared runtime dependencies
- src/metaseed/services/terms.py:270 TermRouter.has_ontology_sync returns False when no source was actually asked
- src/metaseed/services/ontology.py:378 The adapter's two lookup methods have opposite error contracts: get_term_sync raises on an outage, search_sync returns []
- src/metaseed/specs/schema.py:611 ProfileSpec.get_entity's fallback normalizer diverges from comparable_entity_name in the same module
- src/metaseed/specs/merge/facade.py:46 The merge path cannot be given an injected SpecLoader; it discovers a filesystem one
- src/metaseed/specs/merge/facade.py:51 Manual conflict resolution is reachable only as a library call
- src/metaseed/ui/helpers/navigation_helpers.py:92 applies_to == "all" silently drops the rule instead of matching every entity
- src/metaseed/ui/datasets.py:262 import_from_source leaves the previous dataset pointer and nested-edit state, so the next auto-save overwrites a different dataset
- src/metaseed/ui/websocket.py:74 broadcast_sync's asyncio.run fallback sends on WebSockets owned by another event loop, and the failure is swallowed
- src/metaseed/ui/state.py:314 add_node mutates the TreeNode caches without invalidating them; a node whose parent is not cached lands in no tree
- src/metaseed/ui/routes/examples.py:124 Example loading saves through the ambient factory, not the factory the app was composed with
- src/metaseed/ui/routes/seek.py:138 An unreachable SEEK is rendered as "no projects", indistinguishable from a SEEK with no projects
- src/metaseed/ui/routes/table.py:128 HTMX endpoints mix HTTPException (raw JSON) and error_response (HTML partial) for the same class of failure
- src/metaseed/ui/services/import_excel.py:72 read_only workbook is never closed
- src/metaseed/ui/services/export.py:176 Public facade-taking functions annotated `Any` while the sibling importer types ProfileFacade
- src/metaseed/validators/cv.py:44 An ontology-service outage makes a CV compliance check indistinguishable from full compliance
- src/metaseed/validators/dataset.py:22 DatasetValidator imports the private _pydantic_constraint_errors from api
