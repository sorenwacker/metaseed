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
leading zeros from identifiers.

Some columns are structural rather than data:

- **`_parent`** carries the parent's identifier. No profile declares a
  `parent_ref` field, so without this column the tree would not survive the
  round trip.
- **`_parent_field`** names the field of the parent that holds the row, written as `Type.field`, for example `Study.persons`. `_parent` and `_parent_field` are written together, on the sheet of every entity type that some field can hold, and on no other sheet. See [Adding a row](#adding-a-row).
- **A containment column per nested field** (`studies` on Investigation,
  `observation_units` on Study) holds *how many* children of that type hang from
  the row. The children themselves are rows on their own sheet, so the column is
  a summary for a human reading the workbook.
- **Sheets prefixed `metaseed `** belong to the export (controlled terms, field
  documentation) rather than to any entity type.

Scalar list fields are joined into one cell, and a cell whose text would make
Excel evaluate a formula is prefixed with a quote.

### Adding a row

A field that can hold an entity type is a *holder*, written `Type.field`. A MIAPPE Study has one holder, `Investigation.studies`. A MIAPPE Person has two, `Investigation.contacts` and `Study.persons`, and a DCAT Agent is held by one catalogue as both `creator` and `publisher`, so an identifier alone cannot say where a row belongs.

The export fills `_parent_field` and `_parent` for every row it writes, from the edge the dataset records. A person adding a row fills both, from dropdowns: `_parent_field` lists the holders of the sheet's entity type, and `_parent` lists the identifier column of the chosen holder's sheet. While `_parent_field` is empty, `_parent` offers nothing. A type with one holder has one entry to choose; the column is still there, so every sheet is filled in the same way and the import reads every sheet by one rule.

Both dropdowns read the sheets as they are, down to row 5000, so a parent row added in the same edit can be chosen for a new child. They warn rather than refuse, as every dropdown in the workbook does; what a typed value may be is decided by the import.

A row leaves both cells empty when it is not contained in anything: the root entity, or a record placed by a reference field it carries, as a Darwin Core Event is by `parentEventID`. The sheet of a type that no field holds has neither column. If a stored entity has a parent but no recorded field, which data saved before ADR 006 can have when its parent holds the type twice, the export writes `_parent`, leaves `_parent_field` empty and marks the cell, and the import refuses the row until a holder is chosen.

### Column headings explain themselves

Hovering over a heading shows a note built from the field's specification, in this order, leaving out any line the field does not define:

- The description.
- Required or optional, the type in words, the unit, and an example, on one line. The type is one of: text, whole number, decimal number, date (YYYY-MM-DD), date and time, web address, ontology term, yes/no, or a list of values separated by commas. A field that holds other entities has no type in the note.
- **Pattern**: the regular expression a value must match.
- **Length**: the minimum and maximum number of characters.
- **Range**: the minimum and maximum value.
- **Number of values**: the minimum and maximum, for list fields.
- **Allowed values**: the first 10, then "and N more, see the dropdown".
- **Ontologies** the term may come from, or **Terms under** the term it must descend from.
- **Must match**: the entity and field a value refers to, for example `Study.unique_id`.
- **Unique**: within the parent, or across the dataset.
- **Rules**: the description of every profile-level validation rule that applies to the entity and names the field, whether as its `field`, in its `condition`, in its `when` or `require`, or as a start, end, latitude or longitude field.

A constraint can be declared on the field or in a profile-level rule; the note shows it once either way. The note grows with its content. It is a comment rather than a row, because the import reads every row below the heading as data.

The note on `start_date` of a MIAPPE 1.2 Study:

```text
Start date/time. Format: ISO 8601.

Optional · Date and time
Pattern: ^[0-9]{4}-[0-9]{2}-[0-9]{2}$
Rules: End date must not be before start date; Dates must be ISO 8601 format (YYYY-MM-DD)
```

## What the import does

`workbook_to_payload` reverses each of those, and the reversal is the part that
must not be reimplemented:

- **A containment column is never imported.** It holds a count, and a count
  written into a field meant to hold children puts the string `'0'` where a list
  belongs. The tree is rebuilt from the sheets and from `_parent`, so the column
  has nothing to contribute on the way back.
- **Scalar lists are split** on the separator the export joined them with.
- **Formula-escaped cells are unescaped**, or a round trip changes the data.
- **`_parent` becomes `_parent_unique_id`**, which the loader resolves.
- **`_parent_field` becomes `_parent_type` and `_parent_field`**: `Study.persons` is read as parent type `Study` and field `persons`. The import states the parent completely or not at all; see [What the import refuses](#what-the-import-refuses).
- **Placeholder rows** — the `<field>` cells a downloaded template carries — are
  not entities and are skipped.
- **A workbook matching no entity type is refused**, because the usual cause is
  a workbook exported from a different profile, and loading it would silently
  produce nothing.

### What the import refuses

A workbook is imported whole or not at all. Each of the following refuses it, with a message naming every sheet and row concerned, because an import that places what it can leaves a dataset the person has to repair by comparing it with the workbook:

- `_parent` filled and `_parent_field` empty, or the reverse.
- A `_parent_field` that is not a holder of the sheet's entity type. The message lists the holders.
- A `_parent` that names no record of the holder's type, or more than one. The records are the rows of the holder's sheet and, when the workbook is added to an existing dataset, the records of that type already in it.
- A sheet of a held type without a `_parent_field` column while any of its rows has a `_parent`. Workbooks exported before 0.54.0 are in this state: re-export the dataset, or add the column.

## Installing the entities

`workbook_to_payload` produces payloads; `import_payload` installs them, the
same call the JSON import uses, so both formats load through one path. The tree
comes from `_parent_unique_id`, which the loader resolves against the entities
it has already created — only among those whose type can hold the child
(`EntityHelper.child_fields`). An identifier value can belong to records of
several types, so a lookup by value alone could attach a child to the wrong
record ([ADR 006](decisions/006-relationships-are-recorded-edges.md)).

When a payload states `_parent_type`, the loader takes the record of that type among those sharing the identifier, and `_parent_field` files the child in that field. A payload from a workbook always states both, so nothing about a workbook row's parent is inferred. Payloads saved before `_parent_type` existed are resolved as ADR 006 describes; that path is not reachable from a workbook.

Installing into an *existing* dataset rather than replacing one is not yet the
library's: the hub still does that itself, in `add_entities_in_order`, together
with the placement rules it needs — a breadth-first containment order so a
parent precedes the types it contains, `_parent` matched against the declared
identifier field only, and a message per row that could not be placed as
written. It reads `_parent_type` and `_parent_field` the same way the loader does. That is a remaining fork, and moving it here is the next step. Until
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
