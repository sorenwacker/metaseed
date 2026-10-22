# Editing a Dataset in Excel

A dataset can be exported as an Excel workbook, filled in or extended in Excel or LibreOffice, and imported back. This page describes that workflow; the file format itself is described in [Excel Round-Trip](../architecture/excel-round-trip.md).

## Export

Open the dataset and choose **Export Excel** in the toolbar. The workbook contains:

- **How to add data**: the first sheet, a short version of this page.
- **One sheet per entity type** (Investigation, Study, Sample, ...), one record per row. The first row holds the field names.
- **Hidden sheets** prefixed `metaseed`, which hold the dropdown lists. Leave them unchanged.

## Read what a field holds

Click a column heading: a note appears beside it while the heading is selected, without having to hover over the small red mark in its corner. Hovering over the heading shows the same note. It states whether the field is required, its type, an example value, and its pattern, allowed values and rules. A note longer than Excel's 255-character limit for a selected-cell message is shortened there; the hover note is complete. A column with allowed values has a dropdown. A cell that breaks a rule is coloured.

## Add a row

Type in the first empty row directly below a sheet's table. The table extends to include the new row, and its dropdowns and checks apply to it. Rows typed elsewhere, for example after a gap, are outside the table and get no dropdowns.

## Say where the row belongs

Every sheet whose records sit inside another record has a **Belongs to** column. It names the record that holds the row, as `Type: identifier`:

| Sheet | Belongs to | Meaning |
| --- | --- | --- |
| Sample | `ObservationUnit: OU-2` | The sample was taken from observation unit OU-2. |
| Person | `Study: STU-1` | The person is listed on study STU-1. |
| Person | `Investigation: INV-1` | The person is a contact of investigation INV-1. |

Choose the value from the cell's dropdown. It lists every record that can hold the row, read from the sheets as they currently are: a parent added in the same edit appears in the list once its identifier cell is filled in. When one entity type holds the row in two fields, the entry names the field, for example `Catalog.creator: CAT-1`.

Leave **Belongs to** empty only for the top-level record (for example the Investigation) and for records that are placed by a reference field of their own.

To add a new branch of the tree, add the parent first and then its children: for example a Study row with identifier `STU-2`, then ObservationUnit rows with **Belongs to** `Study: STU-2`.

## Import

Save the workbook and choose **Import** in the dataset toolbar or on the dataset list, then select the `.xlsx` file.

The workbook is read as a whole. If any row cannot be placed, nothing is imported and the message lists every problem with its sheet and row, for example:

- a **Belongs to** value that is not `Type: identifier`;
- a type that cannot hold the row (`Study does not hold Sample`), with the values that are allowed;
- an identifier that matches no record in the workbook.

Correct the listed rows and import again. After a successful import, run **Validate** to see required fields that are still empty.

## Rules

- Do not rename sheets or change the heading row: the import uses them to map each value to its field.
- Every record keeps its identifier column filled in; other rows refer to it by that identifier.
- Workbooks exported before metaseed 0.67.0 have a `_parent` column holding the parent's identifier only. They still import.
