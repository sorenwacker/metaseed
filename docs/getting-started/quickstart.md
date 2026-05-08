# Quick Start

## CLI

The command-line interface provides tools for working with metadata files. You can list available entity types, generate empty templates, validate existing files, and convert between YAML and JSON formats.

```bash
metaseed entities
metaseed template investigation
metaseed validate data.yaml
metaseed convert data.yaml data.json
```

## Python

The Python API uses constructor-style entity creation with keyword arguments. Metaseed generates models dynamically from YAML specifications, which allows it to support multiple metadata standards with the same codebase.

```python
from metaseed import miappe

m = miappe()
inv = m.Investigation(unique_id="INV001", title="Drought study")
study = m.Study(unique_id="STU001", title="Field trial")
inv.studies.append(study)
```

See [Profiles](../profiles/isa.md) for ISA and other available profiles.

## Web UI

The web interface provides a visual editor for creating and editing metadata. Forms are generated dynamically from the schema specifications and validate input in real-time.

```bash
metaseed ui
```

This opens a browser at `http://127.0.0.1:8080`.
