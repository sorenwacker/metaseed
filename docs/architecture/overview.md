# Architecture Overview

Metaseed follows a schema-driven architecture where YAML specifications define the metadata structure, and Pydantic models are generated dynamically at runtime.

## System Components

```mermaid
graph TB
    subgraph Interfaces
        CLI[CLI - Typer]
        Web[Web - HTMX]
        API[REST API - FastAPI]
    end

    subgraph Core["Core Layer"]
        Factory[Model Factory]
        Validators
        Facade[ProfileFacade]
    end

    subgraph Data["Data Layer"]
        Specs[Schema Specs - YAML]
        Storage
    end

    Interfaces --> Core
    Core --> Data
```

## Component Responsibilities

### Schema Specs

YAML files defining MIAPPE metadata fields, types, cardinality, and ontology references. These serve as the single source of truth for validation rules.

### Model Factory

Generates Pydantic models from schema specifications at runtime. This approach allows:

- Version-specific model generation (MIAPPE 1.1, 1.2)
- Runtime validation without code duplication
- Easy schema updates without code changes

### Validators

Business logic for validating metadata beyond type checking:

- Cross-field validation
- Ontology term validation
- Referential integrity checks

### Storage

Persistence layer abstraction supporting multiple backends:

- File-based storage (JSON, YAML)
- Database backends (future)

### ProfileFacade

A fluent API layer providing intuitive access to entity helpers:

- **Entity Discovery**: `facade.entities` lists available entity types
- **Entity Helpers**: `facade.Investigation` provides field info and creation
- **Profile Support**: Separate facades for different profiles

## Available Profiles

| Profile | Versions | Description |
|---------|----------|-------------|
| **miappe** | 1.1 | Plant phenotyping metadata (MIAPPE standard) |
| **isa** | 1.0 | Life science experiments (ISA framework) |
| **isa-miappe-combined** | 1.0, 2.0 | Unified model combining ISA and MIAPPE |

Access profiles via convenience functions or `ProfileFacade`:

```python
from metaseed import miappe, isa
from metaseed.facade import ProfileFacade

m = miappe()                                    # MIAPPE v1.1
i = isa()                                       # ISA v1.0
combined = ProfileFacade("isa-miappe-combined", "2.0")  # Combined v2.0
```

See [ISA and MIAPPE Comparison](isa-miappe-comparison.md) for detailed profile documentation.

### Interfaces

- **CLI**: Command-line interface for batch operations and scripting
- **Web UI**: HTMX-based visual editor with dynamic forms
- **REST API**: HTTP endpoints for integration with other systems

## Design Principles

1. **Schema-first**: All metadata structure defined in YAML specs
2. **Ontology-backed**: References to established ontologies (PPEO, ISA, PROV-O)
3. **Validation-focused**: Multiple validation layers ensure data quality
4. **Interface-agnostic**: Core logic separated from interface implementations
