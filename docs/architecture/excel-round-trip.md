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

Three columns are structural rather than data:

- **`_parent`** carries the parent's identifier. No profile declares a
  `parent_ref` field, so without this column the tree would not survive the
  round trip.
- **A containment column per nested field** (`studies` on Investigation,
  `observation_units` on Study) holds *how many* children of that type hang from
  the row. The children themselves are rows on their own sheet, so the column is
  a summary for a human reading the workbook.
- **Sheets prefixed `metaseed `** belong to the export (controlled terms, field
  documentation) rather than to any entity type.

Scalar list fields are joined into one cell, and a cell whose text would make
Excel evaluate a formula is prefixed with a quote.

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
- **Placeholder rows** — the `<field>` cells a downloaded template carries — are
  not entities and are skipped.
- **A workbook matching no entity type is refused**, because the usual cause is
  a workbook exported from a different profile, and loading it would silently
  produce nothing.

## Installing the entities

`workbook_to_payload` produces payloads; `import_payload` installs them, the
same call the JSON import uses, so both formats load through one path. The tree
comes from `_parent_unique_id`, which the loader resolves against the entities
it has already created — only among those whose type can hold the child
(`EntityHelper.child_fields`). An identifier value can belong to records of
several types, so a lookup by value alone could attach a child to the wrong
record ([ADR 006](decisions/006-relationships-are-recorded-edges.md)).

Installing into an *existing* dataset rather than replacing one is not yet the
library's: the hub still does that itself, in `add_entities_in_order`, together
with the placement rules it needs — a breadth-first containment order so a
parent precedes the types it contains, `_parent` matched against the declared
identifier field only, and a message per row that could not be placed as
written. That is a remaining fork, and moving it here is the next step. Until
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
