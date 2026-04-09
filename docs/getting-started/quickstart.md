# Quick Start

## CLI

```bash
# List entities
metaseed entities

# Generate template
metaseed template investigation -o my_investigation.yaml

# Validate
metaseed validate my_investigation.yaml --entity investigation

# Convert formats
metaseed convert data.yaml data.json --entity investigation
```

## Python

### Facade API (Recommended)

```python
from metaseed import miappe, isa
from metaseed.facade import ProfileFacade

# MIAPPE
m = miappe()
inv = m.Investigation(unique_id="INV001", title="Drought study")
study = m.Study(unique_id="STU001", title="Field trial")
inv.studies.append(study)

# ISA
i = isa()
source = i.Source(unique_id="SRC001", name="Patient 1")
sample = i.Sample(unique_id="SAM001", name="Blood sample", derives_from=[source])

# Combined (ISA + MIAPPE)
combined = ProfileFacade("isa-miappe-combined", "2.0")
protocol = combined.Protocol(name="RNA Extraction")
material = combined.BiologicalMaterial(identifier="BM-001", organism="Zea mays")
```

### Direct Model Access

```python
from metaseed.models import get_model
from metaseed.validators import validate

Investigation = get_model("Investigation", version="1.1")
inv = Investigation(unique_id="INV001", title="My study")

errors = validate(inv)
```

## REST API

```bash
# Start server
uvicorn metaseed.api:app --reload

# Health check
curl http://localhost:8000/health

# List entities
curl http://localhost:8000/schemas/1.1

# Validate
curl -X POST http://localhost:8000/validate \
  -H "Content-Type: application/json" \
  -d '{"entity": "investigation", "version": "1.1", "data": {"unique_id": "INV001", "title": "Test"}}'
```

## Web UI

```bash
metaseed ui
# Open http://127.0.0.1:8080
```

Features: entity browser, dynamic forms, nested entity editing, validation.
