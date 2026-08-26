# Capability parity

Metaseed offers the same work through three surfaces: a command line, an MCP server for agents, and a web interface. A capability that reaches only one of them is a capability most users cannot get at — a script cannot open a browser, and a person at a terminal should not have to.

The rule is therefore: **everything the MCP server or the web interface can do, the CLI can do too.** This page is the record of that, and `tests/test_capability_parity.py` is its gate — the table below is read by the test, so a row naming a command, tool or route that does not exist fails the suite, and so does a tool or a state-changing route that no row names.

## What the gate checks

1. Every tool the MCP server registers appears in the table with a CLI command.
2. Every CLI command named in the table exists in the Typer application.
3. Every command the Typer application registers appears in the table.
4. Every route that changes state (`POST`, `PUT`, `DELETE`) appears in the table or in the exemptions below.

Read-only `GET` routes are views of a capability rather than capabilities of their own — a form fragment, a rendered page, a progress poll — so they are not enumerated. The capabilities they display are in the table through their MCP tool or their CLI command.

## The table

| Capability | CLI | MCP tool | UI |
|---|---|---|---|
| **Datasets** | | | |
| List saved datasets | `dataset list` | `list_datasets` | `GET /api/datasets` |
| Show a dataset's contents | `dataset show` | `load_dataset` | `GET /dataset/{name}/edit` |
| Show a dataset's profile and counts | `dataset info` | `get_dataset_info` | — |
| Create an empty dataset | `dataset create` | `create_dataset` | `POST /api/datasets/save` |
| Write entities into a dataset | `dataset import` | `save_dataset` | `POST /import` |
| Delete a dataset | `dataset delete` | `delete_dataset` | `DELETE /api/datasets/{name}` |
| Validate a dataset | `dataset validate` | `validate_dataset` | `GET /api/validate` |
| Check that links between entities are complete | `dataset validate-links` | `validate_relationships` | — |
| Export a dataset (Excel or an adapter format) | `dataset export` | — | `GET /export`, `GET /export/adapter/{fmt}` |
| Import a public record by accession | `dataset import-record` | `import_from_database` | `POST /import/source` |
| **Entities** | | | |
| List a dataset's entities | `entity list` | `list_entities` | — |
| Show one entity | `entity show` | `get_entity` | — |
| Show the entity tree | `entity tree` | `get_entity_tree` | `GET /api/graph` |
| Create an entity | `entity create` | `create_entity` | `POST /entity`, `POST /table/{parent_entity_type}/{field_name}/row` |
| Update an entity | `entity update` | `update_entity` | `PUT /entity/{node_id}`, `POST /nested/{parent_type}/{field_name}/{idx}`, `POST /table/{parent_entity_type}/{field_name}/row/{idx}/cell` |
| Delete an entity | `entity delete` | `delete_entity` | `DELETE /entity/{node_id}`, `DELETE /table/{parent_entity_type}/{field_name}/row/{idx}` |
| Update many entities at once | `entity bulk-update` | `bulk_update_entities` | `POST /table/{parent_entity_type}/{field_name}/bulk`, `POST /table/{parent_entity_type}/{field_name}/paste` |
| Create many entities at once | `entity batch-create` | `batch_create` | — |
| Validate one entity | `validate` | `validate_entity` | `POST /validate` |
| **Profiles** | | | |
| List profiles and versions | `profiles` | `list_profiles` | — |
| List a profile's entity types | `entities` | — | — |
| Show a profile's schema | `profile schema` | `get_profile_schema` | — |
| Show a profile's hierarchy | `profile relationships` | `get_profile_relationships` | — |
| Show an entity's fields | `profile fields` | `get_entity_fields` | — |
| Show an entity's required fields | `profile required` | `get_required_fields` | — |
| Show one field's specification | `profile field` | `get_field_spec` | — |
| Emit a skeleton for an entity | `template` | `get_entity_template` | — |
| Load an example dataset | `example` | `get_example_dataset` | `GET /load-example/{profile_name}/{version}` |
| Validate a file against a profile | `check` | — | — |
| Convert a file between YAML and JSON | `convert` | — | — |
| Compare profiles | `compare` | `spec_compare` | `POST /explore/compare`, `GET /explore/report/{format_type}/{profiles:path}` |
| Merge profiles | `merge` | — | — |
| **Ontology terms** | | | |
| Search for a term | `ontology search` | `search_ontology` | `GET /api/ontology/search` |
| Look up one term | `ontology term` | `get_ontology_term` | — |
| Suggest a term for a value | `ontology suggest` | `suggest_ontology_term` | — |
| List available ontologies | `ontology list` | `list_ontologies` | — |
| Check a dataset's terms resolve | `ontology validate` | `validate_ontology_terms` | — |
| **Extraction from source files** | | | |
| Parse a source file | `extract parse` | `parse_source_file` | — |
| Suggest a field mapping | `extract analyze` | `analyze_mapping` | — |
| Extract entities through a mapping | `extract run` | `extract_entities` | — |
| Validate extracted records | `extract validate` | `validate_extracted` | — |
| Write extracted records to a file | `extract export` | `export_metadata` | — |
| **Specification authoring** | | | |
| Start a draft | `spec create` | `spec_create` | `GET /spec-builder/new` |
| Start a draft from a profile | `spec clone` | `spec_clone` | `GET /spec-builder/clone/{profile}/{version}` |
| Start a draft from a YAML document | `spec import` | `spec_import_yaml` | `POST /spec-builder/import`, `POST /spec-builder/apply-yaml` |
| Summarise a draft | `spec status` | `spec_status` | `GET /spec-builder` |
| Show a draft as YAML | `spec preview` | `spec_preview_yaml` | `GET /spec-builder/preview`, `GET /spec-builder/export` |
| Check a draft | `spec validate` | `spec_validate` | — |
| Save a draft as a profile | `spec save` | `spec_save` | `POST /spec-builder/save` |
| Delete a saved profile | `spec delete` | — | `DELETE /spec-builder/user-spec/{name}/{version}` |
| Set profile-level metadata | `spec set-metadata` | `spec_set_metadata` | `POST /spec-builder/profile-metadata` |
| Set the root entity | `spec set-root` | `spec_set_root_entity` | — |
| Add an entity type | `spec add-entity` | `spec_add_entity` | `POST /spec-builder/entity` |
| Change an entity type | `spec update-entity` | `spec_update_entity` | `PUT /spec-builder/entity/{name}` |
| Rename an entity type | `spec rename-entity` | `spec_rename_entity` | — |
| Remove an entity type | `spec delete-entity` | `spec_delete_entity` | `DELETE /spec-builder/entity/{name}` |
| Add a field | `spec add-field` | `spec_add_field` | `POST /spec-builder/entity/{entity_name}/field` |
| Change a field | `spec update-field` | `spec_update_field` | `PUT /spec-builder/entity/{entity_name}/field/{idx}` |
| Remove a field | `spec delete-field` | `spec_delete_field` | `DELETE /spec-builder/entity/{entity_name}/field/{idx}` |
| Move a field | `spec move-field` | `spec_move_field` | `POST /spec-builder/entity/{entity_name}/field/{idx}/move-up`, `POST /spec-builder/entity/{entity_name}/field/{idx}/move-down` |
| Add a validation rule | `spec add-rule` | `spec_add_rule` | `POST /spec-builder/validation-rule` |
| Change a validation rule | `spec update-rule` | `spec_update_rule` | `PUT /spec-builder/validation-rule/{idx}` |
| Remove a validation rule | `spec delete-rule` | `spec_delete_rule` | `DELETE /spec-builder/validation-rule/{idx}` |
| Keep notes on a draft | `spec notes` | — | `POST /spec-builder/notes` |
| **Catalogue records (DCAT)** | | | |
| Show a dataset's catalogue card | `dcat show` | — | `GET /dcat`, `GET /api/dcat` |
| Set the catalogue fields | `dcat set` | — | `POST /api/dcat/metadata` |
| **FAIRDOM-SEEK** | | | |
| Check the connection | `seek check` | — | `POST /settings/adapters/{key}/check` |
| Preview what would be created | `seek preview` | — | `GET /seek/preview` |
| Create Sample Types and vocabularies | `seek provision` | — | `POST /seek/provision` |
| Push a dataset as ISA content | `seek sync` | — | `POST /seek/sync` |
| Export ISA RDF | `seek isa-rdf` | — | `GET /seek/isa-rdf` |
| Download ISA Templates | `seek isa-templates` | — | `GET /seek/isa-templates` |
| Download the model as Turtle | `seek model-ttl` | — | `GET /seek/model-ttl` |
| Derive a profile from installed templates | `seek import-templates`, `seek-import-templates` | — | — |
| **Metaseed Hub** | | | |
| Check the connection | `hub check` | — | — |
| List datasets on the hub | `hub list` | — | `GET /hub/datasets/pull` |
| Push a dataset | `hub push-dataset` | — | `GET /hub/datasets/{name}/push`, `POST /hub/datasets/{name}/push` |
| Pull a dataset | `hub pull-dataset` | — | `POST /hub/datasets/pull/{dataset_id}` |
| List profiles on both sides | `hub profiles` | — | `GET /hub/profiles` |
| Publish a profile | `hub push-profile` | — | `POST /hub/profiles/{name}/{version}/push` |
| Fetch a published profile | `hub pull-profile` | — | `POST /hub/profiles/{name}/{version}/pull` |
| **Plugins** | | | |
| List the adapters | `plugin list` | — | `GET /settings` |
| Enable or disable an adapter | `plugin enable`, `plugin disable` | — | `POST /settings/adapters/{key}/toggle` |
| Check an adapter's connection | `plugin check` | — | `POST /settings/adapters/{key}/check` |
| Configure an adapter | `plugin config` | — | `POST /settings/adapters/{key}/config` |
| **Running metaseed** | | | |
| Print the version | `version` | — | — |
| Start the web interface | `ui` | — | — |
| Start the MCP server | `mcp` | — | — |
| Migrate stored datasets | `migrate` | — | — |
| Migrate profile versions | `migrate-specs` | — | — |

## Exemptions

| Route | Why it has no CLI command |
|---|---|
| `POST /reset` | Clears the browser session's in-memory state. The CLI holds no session: each command names the dataset it acts on. |
| `POST /api/datasets/load` | Loads a dataset into the browser session, for the same reason. `dataset show` reads a dataset out without one. |
| `GET /docs`, `GET /docs/oauth2-redirect`, `GET /redoc`, `GET /openapi.json` | FastAPI's own API documentation, not a metaseed capability. |

An exemption is a decision on the record: to add one, write the reason here, or the gate fails.

## Surfaces are thin

A CLI command, an MCP tool and a route for the same capability call the same library function; none of the three holds logic the others lack. That is what makes parity maintainable rather than three implementations kept in step by hand.
