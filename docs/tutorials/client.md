# Tutorial: MetaseedClient

This tutorial builds a small MIAPPE 1.2 dataset with `MetaseedClient`: it inspects the schema, creates an Investigation with a Study and three biological materials, navigates the entity tree, validates the dataset, and writes it to YAML and reads it back. The method reference is [MetaseedClient API](../api/client.md).

`MetaseedClient` is the programmatic entry point, suited to scripts and applications. For interactive exploration in Jupyter or IPython, see the [ProfileFacade tutorial](facade.md).

Every code block on this page runs in order, in one session; a test executes them, so the page matches the installed version.

## 1. Create a client

A client is bound to one profile and one version. Name both explicitly.

```python
from metaseed import MetaseedClient

client = MetaseedClient(profile="miappe", version="1.2")
print(client.profile, client.version)
```

## 2. Inspect the schema

List the entity types the profile defines, the fields of one type, and the schema summary of another.

```python
entity_types = client.list_entity_types()
print(f"MIAPPE 1.2 defines {len(entity_types)} entity types")

for field in client.get_entity_fields("Investigation"):
    marker = "(required)" if field.required else ""
    print(f"  {field.name}: {field.type} {marker}")

schema = client.get_entity_schema("Study")
print(schema.name, schema.ontology_term, schema.required_fields)
```

## 3. Create entities

`create_entity()` takes the entity type and its field values. In MIAPPE 1.2 a child names its parent through a reference field (`investigation_id`, `study_id`); `parent_id` places the entity in the client's entity tree.

```python
inv = client.create_entity(
    "Investigation",
    {
        "unique_id": "INV-WHEAT-2024",
        "title": "Wheat Drought Tolerance Study",
        "description": "Multi-environment drought stress assessment",
        "miappe_version": "1.2",
    },
)

study = client.create_entity(
    "Study",
    {
        "unique_id": "STU-FIELD-2024",
        "investigation_id": "INV-WHEAT-2024",
        "title": "Field Trial 2024",
        "description": "Randomized block design with 3 replicates",
        "latitude": 52.52,
        "longitude": 13.405,
        "growth_facility_type": "field",
    },
    parent_id=inv.id,
)

materials = [
    client.create_entity(
        "BiologicalMaterial",
        {
            "unique_id": f"BM-{i:03d}",
            "study_id": "STU-FIELD-2024",
            "organism": "Triticum aestivum",
            "genus": "Triticum",
            "species": "aestivum",
            "infraspecific_name": f"cv. {cultivar}",
        },
        parent_id=study.id,
    )
    for i, cultivar in enumerate(["Apache", "Soissons", "Bologna"], start=1)
]
print(inv.id, study.parent_id, len(materials))
```

## 4. Navigate the entity tree

`get_tree()` returns the root nodes with their descendants; `get_roots()` and `get_children()` return one level.

```python
for root in client.get_tree():
    print(f"{root.entity_type}: {root.label}")
    for child in root.children:
        print(f"  {child.entity_type}: {child.label}")
        for grandchild in child.children:
            print(f"    {grandchild.entity_type}: {grandchild.label}")

print(len(client.get_roots()), "root entity")
print([c.label for c in client.get_children(study.id)])
```

## 5. Read, update and delete

`update_entity()` replaces the entity's data with the values given. `delete_entity()` removes the entity and its descendants.

```python
print(client.get_entity(inv.id).data["title"])

updated = client.update_entity(
    inv.id,
    {
        "unique_id": "INV-WHEAT-2024",
        "title": "Wheat Drought Tolerance Study, revised",
        "description": "Multi-environment drought stress assessment",
        "miappe_version": "1.2",
    },
)
print(updated.data["title"])

client.delete_entity(materials[2].id)
print([c.label for c in client.get_children(study.id)])
```

## 6. Validate

`validate()` checks every entity; `validate_entity()` checks one. Each issue names the field and the rule it failed.

```python
result = client.validate()
print(f"valid: {result.valid}, issues: {len(result.issues)}")
for issue in result.issues:
    print(f"  {issue.field}: {issue.message}")

print(client.validate_entity(study.id).valid)
```

## 7. Serialize, save and load

`serialize()` returns the dataset as a dictionary, either `flat` (a list of entities, each with its `_type`) or `tree` (nested by parent). `load()` reads the flat form back into a client.

```python
import tempfile
from pathlib import Path

import yaml

flat = client.serialize(format="flat")
print([(e["_type"], e.get("unique_id")) for e in flat["entities"]])

tree = client.serialize(format="tree")
print(len(tree["tree"]), "root in the tree form")

output_path = Path(tempfile.mkdtemp()) / "dataset.yaml"
output_path.write_text(yaml.safe_dump(flat, sort_keys=False))

reloaded = MetaseedClient(profile="miappe", version="1.2")
reloaded.load(yaml.safe_load(output_path.read_text()))
print([root.label for root in reloaded.get_tree()])
```

## 8. Use the Pydantic models

Each entity type is a generated Pydantic model. `get_model()` returns the class, which can build instances directly and export a JSON Schema.

```python
InvestigationModel = client.get_model("Investigation")

direct = InvestigationModel(unique_id="INV-DIRECT", title="Built from the model class")
print(direct.title)

json_schema = InvestigationModel.model_json_schema()
print(json_schema["required"])
```
