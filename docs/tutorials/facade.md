# Tutorial: ProfileFacade

This tutorial explores profiles interactively with `ProfileFacade`: it lists the entity types of MIAPPE 1.2, reads field documentation, generates example code, creates entities, searches fields, and repeats the steps for the ISA and MetaboLights profiles. The method reference is [Facade API](../api/facade.md).

The facade is designed for Jupyter and IPython, where `m.<Tab>` completes entity names. For scripts and applications, see the [MetaseedClient tutorial](client.md).

Every code block on this page runs in order, in one session; a test executes them, so the page matches the installed version.

## 1. Create a facade

The [profile shortcuts](../api/facade.md#profile-shortcuts) such as `miappe()`, `isa()` and `metabolights()` return a facade for their profile. `ProfileFacade` takes any profile by name.

```python
from metaseed import ProfileFacade, miappe

m = miappe(version="1.2")
m = ProfileFacade(profile="miappe", version="1.2")
print(m)
```

## 2. Discover entity types

`entities` lists the entity types; `help()` prints a profile overview.

```python
print(m.entities)
m.help()
```

## 3. Read field documentation

An entity type is an attribute of the facade, matched case-insensitively. Its helper documents the fields.

```python
inv = m.Investigation
assert m.investigation is not None

inv.help()
print("required:", inv.required_fields)
print("optional:", inv.optional_fields)
print(inv.field_info("unique_id"))
print("nested:", inv.nested_fields)
```

## 4. Generate example code

`example()` prints a code template that fills every required field.

```python
m.Investigation.example()
m.Study.example()
```

## 5. Create entities

`create()` builds a validated model instance; calling the helper is shorthand for it. In MIAPPE 1.2 a Study refers to its Investigation through `investigation_id`.

```python
import datetime

investigation = m.Investigation.create(
    unique_id="INV-001",
    title="Drought Stress Study in Wheat",
    description="Drought response in wheat varieties",
    submission_date=datetime.date(2024, 1, 15),
)

studies = [
    m.Study(
        unique_id="STU-001",
        investigation_id="INV-001",
        title="Greenhouse Trial",
        description="Controlled environment study",
    ),
    m.Study(
        unique_id="STU-002",
        investigation_id="INV-001",
        title="Field Trial",
        description="Multi-location field experiment",
    ),
]
print(investigation.title, [s.investigation_id for s in studies])
```

## 6. Search fields

`search()` returns the entity types and fields whose names contain a keyword.

```python
for hit in m.search("date"):
    print(hit)
```

## 7. Other profiles

The same calls work for every profile. ISA identifies an Investigation by `identifier`:

```python
from metaseed import isa

i = isa()
print(i.entities)
isa_inv = i.Investigation(
    identifier="INV-ISA-001",
    title="Metabolomics Study",
    description="LC-MS metabolite profiling",
)
print(isa_inv.title)
```

MetaboLights describes NMR, LC-MS and GC-MS experiments with one Assay entity type, distinguished by its technology fields:

```python
from metaseed import metabolights

mtbls = metabolights()
mtbls.Assay.help()

assay = mtbls.Assay(
    identifier="ASSAY-001",
    filename="a_MTBLS001_metabolite_profiling.txt",
    technology_type="mass spectrometry",
    measurement_type="metabolite profiling",
    technology_platform="Thermo Q Exactive Plus",
    samples=["Sample1", "Sample2", "Sample3"],
)
print(assay.technology_type, assay.samples)
```

## Facade or client

| | ProfileFacade | MetaseedClient |
|---|---|---|
| Intended use | Interactive sessions (Jupyter, IPython) | Scripts and applications |
| Tab completion | Yes | No |
| Creating an entity | `m.Investigation(...)` | `client.create_entity("Investigation", {...})` |
| Field documentation | `help()`, `example()`, `field_info()` | `get_entity_fields()`, `get_entity_schema()` |
| Entity storage | `add_entity()` | Built in, with an entity tree |
| Validation | On model construction | `validate()`, `validate_entity()` |
| Serialization | `to_dict()`, `load_from_dict()` | `serialize()`, `load()` |
