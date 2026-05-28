# Repository Submission Modules Architecture

## Overview

This document outlines the architecture for adding database submission modules to metaseed, enabling export to ISA-Tab format and submission to scientific data repositories (MetaboLights, ENA, NCBI, PRIDE).

## Current State

- **Profiles/Specs**: Define metadata schemas (ISA, ENA, MIAPPE, Darwin Core)
- **Repositories module**: Internal entity/dataset storage (not external submissions)
- **Export**: Excel and YAML only
- **ISA-Tab**: Previously removed (isatools dependency)

## Proposed Architecture

```
src/metaseed/
├── exporters/              # Format converters
│   ├── __init__.py
│   ├── base.py             # Abstract Exporter interface
│   ├── isatab/
│   │   ├── __init__.py
│   │   ├── writer.py       # ISA-Tab file writer
│   │   ├── investigation.py
│   │   ├── study.py
│   │   └── assay.py
│   ├── mztab.py            # mzTab format (PRIDE)
│   └── xml/
│       ├── __init__.py
│       ├── ena.py          # ENA XML schema
│       └── sra.py          # NCBI SRA XML schema
│
├── submitters/             # Database submission APIs
│   ├── __init__.py
│   ├── base.py             # Abstract Submitter interface
│   ├── metabolights.py     # MetaboLights REST API
│   ├── ena.py              # ENA Webin REST API
│   ├── ncbi.py             # NCBI Submission Portal API
│   └── pride.py            # PRIDE ProteomeXchange API
│
├── specs/                  # Existing metadata schemas
│   ├── isa/1.0/
│   ├── ena/1.0/
│   ├── metabolights/       # NEW - MetaboLights-specific
│   ├── pride/              # NEW - PRIDE-specific
│   └── ncbi-sra/           # NEW - NCBI SRA-specific
```

## Component Design

### 1. Exporters (Format Conversion)

Abstract base class for all exporters:

```python
# src/metaseed/exporters/base.py
from abc import ABC, abstractmethod
from pathlib import Path
from metaseed.models import EntityInstance

class Exporter(ABC):
    """Base class for format exporters."""

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Return format name (e.g., 'ISA-Tab', 'mzTab')."""
        pass

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """Return primary file extension."""
        pass

    @abstractmethod
    def export(self, entities: list[EntityInstance], output_dir: Path) -> list[Path]:
        """Export entities to format files."""
        pass

    @abstractmethod
    def validate(self, entities: list[EntityInstance]) -> list[str]:
        """Validate entities can be exported. Return list of errors."""
        pass
```

### 2. ISA-Tab Exporter

ISA-Tab format produces three file types:
- `i_*.txt` - Investigation file
- `s_*.txt` - Study file(s)
- `a_*.txt` - Assay file(s)

```python
# src/metaseed/exporters/isatab/writer.py
class ISATabExporter(Exporter):
    format_name = "ISA-Tab"
    file_extension = ".txt"

    def export(self, entities, output_dir):
        investigation = self._find_investigation(entities)
        files = []

        # Write investigation file
        files.append(self._write_investigation(investigation, output_dir))

        # Write study and assay files
        for study in investigation.studies:
            files.append(self._write_study(study, output_dir))
            for assay in study.assays:
                files.append(self._write_assay(assay, output_dir))

        return files
```

### 3. Submitters (Database APIs)

Abstract base class for database submissions:

```python
# src/metaseed/submitters/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

class SubmissionStatus(Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

@dataclass
class SubmissionResult:
    status: SubmissionStatus
    accession: str | None
    messages: list[str]
    url: str | None

class Submitter(ABC):
    """Base class for database submitters."""

    @property
    @abstractmethod
    def repository_name(self) -> str:
        """Return repository name."""
        pass

    @abstractmethod
    def authenticate(self, credentials: dict) -> bool:
        """Authenticate with repository."""
        pass

    @abstractmethod
    def validate(self, entities: list) -> list[str]:
        """Validate submission. Return errors."""
        pass

    @abstractmethod
    def submit(self, entities: list, dry_run: bool = False) -> SubmissionResult:
        """Submit to repository."""
        pass

    @abstractmethod
    def check_status(self, accession: str) -> SubmissionStatus:
        """Check submission status."""
        pass
```

### 4. Repository-Specific Implementations

#### MetaboLights

- Uses ISA-Tab format
- REST API at `https://www.ebi.ac.uk/metabolights/ws/`
- Requires MTBLS account

```python
# src/metaseed/submitters/metabolights.py
class MetaboLightsSubmitter(Submitter):
    repository_name = "MetaboLights"
    base_url = "https://www.ebi.ac.uk/metabolights/ws/"

    def __init__(self, exporter: ISATabExporter):
        self.exporter = exporter

    def submit(self, entities, dry_run=False):
        # 1. Export to ISA-Tab
        files = self.exporter.export(entities, temp_dir)
        # 2. Upload via API
        # 3. Return accession (MTBLS...)
```

#### ENA (European Nucleotide Archive)

- Uses XML submission format
- Webin REST API
- Requires ENA account

```python
# src/metaseed/submitters/ena.py
class ENASubmitter(Submitter):
    repository_name = "ENA"
    base_url = "https://wwwdev.ebi.ac.uk/ena/submit/webin-v2/"

    def submit(self, entities, dry_run=False):
        # 1. Convert to ENA XML
        # 2. Submit via Webin REST
        # 3. Return accessions (ERP..., ERS..., ERX..., ERR...)
```

#### NCBI (SRA/BioProject/BioSample)

- Uses XML submission format
- Submission Portal API
- Requires NCBI account

```python
# src/metaseed/submitters/ncbi.py
class NCBISubmitter(Submitter):
    repository_name = "NCBI"

    def submit(self, entities, dry_run=False):
        # 1. Convert to SRA XML
        # 2. Submit via Submission Portal
        # 3. Return accessions (PRJNA..., SAMN..., SRX..., SRR...)
```

#### PRIDE (ProteomeXchange)

- Uses mzTab or ISA-Tab format
- ProteomeXchange API
- Requires PRIDE account

```python
# src/metaseed/submitters/pride.py
class PRIDESubmitter(Submitter):
    repository_name = "PRIDE"

    def submit(self, entities, dry_run=False):
        # 1. Export to mzTab or ISA-Tab
        # 2. Submit via ProteomeXchange
        # 3. Return accession (PXD...)
```

## Profile Mappings

Each submitter needs a mapping from metaseed profiles to repository-specific fields:

| Metaseed Profile | Target Repository | Format |
|------------------|-------------------|--------|
| ISA | MetaboLights | ISA-Tab |
| ISA | PRIDE | ISA-Tab/mzTab |
| ENA | ENA | ENA XML |
| miappe | ENA (via mapping) | ENA XML |
| ncbi-sra (new) | NCBI | SRA XML |

## CLI Integration

```bash
# Export to ISA-Tab
metaseed export --format isatab --output ./isatab_files dataset.yaml

# Validate for submission
metaseed submit validate --repository metabolights dataset.yaml

# Submit (dry-run)
metaseed submit --repository metabolights --dry-run dataset.yaml

# Submit for real
metaseed submit --repository metabolights dataset.yaml
```

## UI Integration

Add submission panel to the UI:
- Repository selection dropdown
- Credential configuration
- Validation results display
- Submit button with dry-run option
- Status tracking

## FAIRDOM-SEEK Integration

SEEK uses the JERM (Just Enough Results Model) ontology. A `jerm` profile already exists with:
- Project, Institution, Person
- Investigation, Study, Assay
- DataFile, Model, SOP, Publication

### SEEK Submitter

```python
# src/metaseed/submitters/seek.py
class SEEKSubmitter(Submitter):
    repository_name = "FAIRDOM-SEEK"

    def __init__(self, base_url: str):
        self.base_url = base_url  # e.g., "https://fairdomhub.org"

    def submit(self, entities, dry_run=False):
        # 1. Authenticate via SEEK API
        # 2. Create/update entities via JSON API
        # 3. Return SEEK IDs
```

### Custom Sample Types and Assay Types

SEEK supports custom sample types with user-defined attributes. Two approaches:

1. **Static profiles** (recommended for now):
   - Create domain-specific profiles (e.g., `seek-plant-phenotyping`)
   - Predefined sample types with known attributes

2. **Dynamic schemas** (future enhancement):
   - Meta-schema allowing sample type definitions within profile
   - More complex but matches SEEK's flexibility

### SEEK API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /projects` | Create project |
| `POST /investigations` | Create investigation |
| `POST /studies` | Create study |
| `POST /assays` | Create assay |
| `POST /data_files` | Upload data file |
| `POST /samples` | Create sample |
| `GET /sample_types` | List available sample types |

## Implementation Priority

1. **Phase 1: ISA-Tab Export**
   - Implement ISA-Tab writer
   - Add CLI export command
   - Add UI export button

2. **Phase 2: MetaboLights**
   - Implement MetaboLights submitter
   - Add validation against MetaboLights requirements
   - Test with sandbox API

3. **Phase 3: ENA**
   - Implement ENA XML exporter
   - Implement ENA Webin submitter
   - Map MIAPPE → ENA fields

4. **Phase 4: NCBI/PRIDE**
   - Add remaining submitters
   - Create ncbi-sra profile
   - Add mzTab exporter for PRIDE

## Dependencies

```toml
# pyproject.toml additions
[project.optional-dependencies]
submitters = [
    "httpx>=0.25",        # Async HTTP client
    "xmltodict>=0.13",    # XML handling
]
```

No isatools dependency - implement ISA-Tab writing directly for better control and fewer dependencies.
