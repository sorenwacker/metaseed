# Excel Round-Trip

A dataset leaves as a workbook and comes back as the same dataset. Export and
import are one seam. Both halves of the file format itself — what the export
writes and what the import reads back — live in the library, so every
application offering an Excel import reads a workbook identically.

```python
from metaseed.ui.datasets import import_payload
from metaseed.ui.services.export import export_to_bytes
from metaseed.ui.services.import_excel import workbook_to_payload

raw = export_to_bytes(state).getvalue()
payload = workbook_to_payload(raw, profile="miappe", version="1.1", facade=facade)
import_payload(state, payload)
```

## What the export writes

One sheet per entity type, a header row of field names, and every data cell
written as text — Excel otherwise reinterprets gene names as dates and strips
leading zeros from identifiers. `_format_cell_value` in `ui/services/export.py` produces that text for every value, numbers and booleans included, and the write loop stores what it returns with a text number format; the guarantee has that one home and a unit test (`tests/test_ui/test_export_service.py`).

Some columns are structural rather than data:

- **`Belongs to`** names the record that holds the row, as `Type: identifier`, for example `Study: STU-1`. No profile declares a `parent_ref` field, so without this column the tree would not survive the round trip. It is written on the sheet of every entity type that some field can hold, and on no other sheet. See [Adding a row](#adding-a-row).
- **A containment column per nested field** (`studies` on Investigation,
  `observation_units` on Study) holds *how many* children of that type hang from
  the row. The children themselves are rows on their own sheet, so the column is
  a summary for a human reading the workbook.
- **The first sheet, `How to add data`**, explains filling in the workbook: extending a sheet's table, choosing **Belongs to**, reading a heading's note, and importing.
- **Sheets prefixed `metaseed `** belong to the export (controlled terms, field
  documentation) rather than to any entity type.

Every entity is written once. A record can also be present as a copy embedded in its parent's data, from a nested document or from a dataset saved before its children were stored as records of their own. The export writes an embedded copy only when the parent has no stored child of that type: a dataset carrying stale copies next to its stored records would otherwise write every child twice, and the copies, which may predate edits, come back as extra records.

Scalar list fields are joined into one cell, and a cell whose text would make
Excel evaluate a formula is prefixed with a quote.

The dropdowns, heading notes and rules come from the dataset's specification. A facade built from a supplied specification (`ProfileFacade(..., spec=...)`, `MetaseedClient.from_spec`) carries it in memory, and the export and the import read that one; only a facade that loads by name asks a `SpecLoader`. A specification stored by the hub has no profile file, so it reaches the workbook this way.

### Adding a row

A row is added by typing in the first empty row below a sheet's table: Excel and LibreOffice extend the table to it, and its dropdowns and checks apply to the new row.

**Belongs to** says where the row goes. Its dropdown lists every record that can hold the sheet's entity type, as `Type: identifier`: on the MIAPPE Sample sheet, every observation unit; on the Person sheet, every investigation and every study, because both hold persons. The list is read from the sheets as they are, so a parent added in the same edit can be chosen for a new child. When one type holds the entity in two fields, as a DCAT catalogue holds an agent as `creator` and as `publisher`, the entry names the field: `Catalog.creator: CAT-1`. The dropdown warns rather than refuses, as every dropdown in the workbook does; what a value may be is decided by the import.

A row leaves **Belongs to** empty when it is not contained in anything: the root entity, or a record placed by a reference field it carries, as a Darwin Core Event is by `parentEventID`.

Workbooks exported before 0.67.0 carry a `_parent` column with the parent's identifier alone. The import still reads it, choosing among the records with that identifier one whose type holds the row.

## What the import does

`workbook_to_payload` reverses each of those, and the reversal is the part that
must not be reimplemented:

- **A containment column is never imported.** It holds a count, and a count
  written into a field meant to hold children puts the string `'0'` where a list
  belongs. The tree is rebuilt from the sheets and from `_parent`, so the column
  has nothing to contribute on the way back.
- **Scalar lists are split** on the separator the export joined them with.
- **Formula-escaped cells are unescaped**, or a round trip changes the data.
- **`Belongs to` becomes `_parent_unique_id` and `_parent_field`**: `Study: STU-1` is read as identifier `STU-1` and the one field of Study that holds the row, `persons` on the Person sheet; `Catalog.creator: CAT-1` names the field itself. A legacy `_parent` cell becomes `_parent_unique_id` alone.
- **Placeholder rows** — the `<field>` cells a downloaded template carries — are
  not entities and are skipped.
- **A workbook matching no entity type is refused**, because the usual cause is
  a workbook exported from a different profile, and loading it would silently
  produce nothing.

### What the import refuses

A workbook is imported whole or not at all. Each of the following refuses it, with a message naming every sheet and row concerned, because an import that places what it can leaves a dataset the person has to repair by comparing it with the workbook:

- A **Belongs to** value that is not `Type: identifier` or `Type.field: identifier`.
- A type that does not hold the sheet's entity type, or a type holding it in more than one field when the value names none. The message lists what may be written.
- An identifier that names no record of that type in the workbook.

## Installing the entities

`workbook_to_payload` produces payloads; `import_payload` installs them, the
same call the JSON import uses, so both formats load through one path. The tree
comes from `_parent_unique_id`, which the loader resolves against the entities
it has already created — only among those whose type can hold the child
(`EntityHelper.child_fields`). An identifier value can belong to records of
several types, so a lookup by value alone could attach a child to the wrong
record ([ADR 006](decisions/006-relationships-are-recorded-edges.md)).

When a payload states `_parent_field`, the loader takes, among the records sharing the identifier, the one whose type holds the child in that field, and files the child there. A payload from a workbook states it for every row with a **Belongs to**, so nothing about such a row's parent is inferred. A payload without it, from a legacy `_parent` column or saved before ADR 006, is resolved as ADR 006 describes.

Installing into an *existing* dataset rather than replacing one is not yet the
library's: the hub still does that itself, in `add_entities_in_order`, together
with the placement rules it needs — a breadth-first containment order so a
parent precedes the types it contains, `_parent` matched against the declared
identifier field only, and a message per row that could not be placed as
written. It reads `_parent_field` the same way the loader does. That is a remaining fork, and moving it here is the next step. Until
then it is named rather than left to be discovered.

## Why the parsing is the library's

The hub reimplemented this path, and the copy was not merely duplicated — it
was behind, and it corrupted data. It never unescaped formula cells, so a study
titled `=cmd|calc` came back as `'=cmd|calc`, keeping the export's quote
forever. It never split scalar lists, so `["block", "plot"]` came back as the
string `"block, plot"` — the same `list[any]` defect that was found and fixed
for containment columns, in a second field where no test looked.

That is the cost the anti-fork rule names. `tests/test_hub_contract.py` freezes
what the hub imports, so this surface cannot be renamed out from under it, and
the hub's `tests/test_no_forked_code.py` fails if a second parser reappears.

## Testing

`tests/test_ui/test_excel_roundtrip.py` exports a dataset and reimports it,
asserting the same entities, the same tree and the same values — including the
ones Excel mangles and the scalar lists the export joins. A template's
placeholder rows are covered directly, since a template is the one workbook a
user is most likely to import unedited.

`tests/test_ui/test_excel_uses_the_facades_own_spec.py` exports and reimports a dataset whose specification exists only in memory, and fails if a UI module looks a facade's specification up by name without asking the facade first.
