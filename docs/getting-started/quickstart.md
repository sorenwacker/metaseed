# Quick Start

## CLI

The command-line interface provides tools for working with metadata files. You can list available entity types, generate empty templates, validate existing files, and convert between YAML and JSON formats.

```bash
metaseed entities
metaseed template investigation
metaseed validate data.yaml
metaseed convert data.yaml data.json
```

## Python API

### MetaseedClient (Recommended)

The `MetaseedClient` provides a clean programmatic API for working with metadata:

```python
from metaseed import MetaseedClient

client = MetaseedClient("miappe", "1.2")

# Create entities
inv = client.create_entity("Investigation", {
    "unique_id": "INV001",
    "title": "Drought study"
})

study = client.create_entity("Study", {
    "unique_id": "STU001",
    "title": "Field trial",
    "investigation_id": "INV001"
}, parent_id=inv.id)

# Validate
result = client.validate()
if not result.valid:
    for issue in result.issues:
        print(f"{issue.field}: {issue.message}")

# Serialize/load
data = client.serialize()
client.load(data)
```

!!! warning "Cardinality rules and flat storage"
    `MetaseedClient` stores children as a flat sibling list keyed by parent id; it
    does not populate the parent's nested list field. Profiles with list
    **cardinality** rules (e.g. "Investigation must have ≥1 study") therefore
    report the parent as invalid even after a child is created with
    `parent_id=...`, because `serialize()` emits an empty list on the parent.
    Validate the serialized nested tree if you rely on such rules. Tracked as a
    separate issue.

See [MetaseedClient API](../api/client.md) for complete documentation.

### Interactive Facade (Jupyter/Notebooks)

For interactive use with tab completion:

```python
from metaseed import miappe

m = miappe()
m.Investigation.help()  # Show fields
inv = m.Investigation(unique_id="INV001", title="Drought study")
```

See [Profiles](../profiles/isa.md) for ISA and other available profiles.

## Web UI

The web interface provides a visual editor for creating and editing metadata. Forms are generated dynamically from the schema specifications and validate input in real-time.

```bash
metaseed ui
```

This opens a browser at `http://127.0.0.1:8080`.
