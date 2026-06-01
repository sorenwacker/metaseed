# Ontology Term Lookup

Metaseed provides integrated ontology term lookup using the OLS4 (Ontology Lookup Service) API. This enables users to search and select standardized ontology terms when editing metadata.

## Overview

Fields with `type: ontology_term` automatically get:

- **Autocomplete**: Type-ahead suggestions as you type
- **Modal search**: Full search interface via Tab key or search button
- **OLS4 integration**: Real-time queries to the EBI Ontology Lookup Service

## Field Configuration

### Basic Ontology Field

```yaml
fields:
  - name: organism
    type: ontology_term
    description: Scientific name of the organism
```

This creates an input that searches across all ontologies in OLS4.

### Scoped to Specific Ontology

Use `ontology_id` to restrict searches to a specific ontology:

```yaml
fields:
  - name: organism
    type: ontology_term
    ontology_id: ncbitaxon
    description: Organism from NCBI Taxonomy
```

Common ontology IDs:
- `ncbitaxon` - NCBI Taxonomy (organisms)
- `pato` - Phenotype and Trait Ontology
- `envo` - Environment Ontology
- `go` - Gene Ontology
- `obi` - Ontology for Biomedical Investigations
- `po` - Plant Ontology
- `uo` - Units of Measurement Ontology

## User Interface

### Autocomplete

When typing in an ontology term field:

1. Start typing (minimum 1 character)
2. Suggestions appear after 300ms debounce
3. Use arrow keys to navigate
4. Press Enter or click to select
5. Press Escape to dismiss

Each suggestion shows:
- Term ID (e.g., `PATO:0000001`)
- Label (e.g., "quality")
- Source ontology
- Description (truncated)

### Modal Search

For more detailed browsing:

1. Press **Tab** when the input is focused, or
2. Click the search button (magnifying glass icon)

The modal provides:
- Full-text search across term labels and descriptions
- Multi-select capability
- Chip display of selected terms
- Detailed term information

## API Endpoint

The lookup uses the `/api/ontology/search` endpoint:

```
GET /api/ontology/search?q=temperature&ontology=pato
```

**Parameters:**
- `q` (required): Search query
- `ontology` (optional): Ontology ID to filter results

**Response:**
```json
{
  "results": [
    {
      "value": "PATO:0000146",
      "label": "temperature",
      "description": "A physical quality...",
      "ontology": "pato"
    }
  ]
}
```

## Profile Configuration

Define available ontologies in your profile's `ontologies` section:

```yaml
spec_version: "0.2"
name: my-profile
version: "1.0"

ontologies:
  PATO:
    name: Phenotype and Trait Ontology
    uri: http://purl.obolibrary.org/obo/pato.owl
    ols_id: pato
  ENVO:
    name: Environment Ontology
    uri: http://purl.obolibrary.org/obo/envo.owl
    ols_id: envo

entities:
  Sample:
    fields:
      - name: quality
        type: ontology_term
        ontology_id: pato
      - name: environment
        type: ontology_term
        ontology_id: envo
```

The `ols_id` field maps to the OLS4 ontology identifier used for API queries.

## HTML/CSS Classes

For developers extending the UI:

| Class | Purpose |
|-------|---------|
| `lookup-input` | Enables autocomplete behavior |
| `ontology-lookup-btn` | Search button that opens modal |
| `autocomplete-dropdown` | Suggestion dropdown container |
| `ontology-autocomplete` | Ontology-specific dropdown styling |

Data attributes:
- `data-lookup-type="ontology"` - Identifies ontology lookup
- `data-ontology-id="pato"` - Scopes to specific ontology

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Tab | Open search modal (when no dropdown visible) |
| Tab | Select highlighted item (when dropdown visible) |
| Enter | Select highlighted item |
| Escape | Close dropdown or modal |
| Arrow Up/Down | Navigate suggestions |

## See Also

- [Schema Specification](../api/schema-specs.md) - Field type reference
- [REST API](../api/rest.md) - API endpoint documentation
