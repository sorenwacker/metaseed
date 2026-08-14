# ISA-MIAPPE Combined

The [ISA framework](isa.md) extended with [MIAPPE 1.2](miappe.md) plant-phenotyping entities, reconciled into a single normalized profile. It exists to be the source of truth for downstream SEEK export: one profile carrying both the ISA study structure and the MIAPPE phenotyping model, without the redundancies that arise from combining them naively.

Root entity: `Investigation`. 27 entities, 55 validation rules. Versions `0.1` (the naive combination, retained) and `0.2` (the reconciliation).

## What 0.2 reconciles away

Version 0.2 removes the redundant and ambiguous modeling that 0.1 inherited from stitching the two standards together:

- **One identifier key.** Every entity is keyed by `unique_id`; the parallel `identifier` fields are gone and every reference points at `*.unique_id`. Two names for one identity was ambiguity, not flexibility.
- **One factor model.** `Factor` + `FactorValue`, with `FactorValue.value` required and `FactorValue.factor_id` referencing `Factor.unique_id`. The overlapping `StudyFactor`, `Factor.values`, and `FactorValue.factor_name` are gone — a factor's values were stateable in three places, which is two too many.
- **Geolocation on `Study`.** The experimental site's coordinates live on the Study; the separate `Location` entity duplicated what MIAPPE puts there.
- **Material source inline.** Germplasm material-source fields live on `BiologicalMaterial`; the separate `MaterialSource` entity restated them.

The net: 27 entities (was 30), 55 validation rules (was 57).

## MIAPPE 1.2 alignment

Entity-complete against MIAPPE 1.2, including the 1.2 trait decomposition on `ObservedVariable` and the expanded material-source fields — see the [MIAPPE page](miappe.md) for what those mean; this page does not restate them.

## Entities

`Investigation`, `Study`, `Assay`, `Person`, `Publication`, `Protocol`, `ProtocolParameter`, `ParameterValue`, `Process`, `Source`, `Sample`, `Extract`, `LabeledExtract`, `OtherMaterial`, `MaterialRef`, `DataFile`, `Comment`, `OntologySource`, `OntologyAnnotation`, `Characteristic` (the ISA half), plus `BiologicalMaterial`, `ObservationUnit`, `ObservedVariable`, `Environment`, `Event`, `Factor`, `FactorValue` (the MIAPPE phenotyping half).

## Provenance

Built with the spec-builder MCP tools: `spec_clone` of 0.1, then targeted `spec_delete_entity` / `spec_delete_field` / `spec_update_field` / `spec_delete_rule` / `spec_update_rule`, `spec_set_metadata`, and a clean `spec_validate` before `spec_save`. The same tools can evolve it further.
