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
it has already created.

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
