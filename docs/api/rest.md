# REST API Reference

Metaseed provides a REST API built with [FastAPI](https://fastapi.tiangolo.com/).

## Starting the Server

```bash
# Development server with auto-reload
uv run uvicorn metaseed.api:app --reload

# Production server
uv run uvicorn metaseed.api:app --host 0.0.0.0 --port 8000
```

## API Documentation

When the server is running, interactive documentation is available at:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

## Core API Endpoints

### Health Check

```
GET /health
```

Returns the API health status.

**Response:**

```json
{
  "status": "ok"
}
```

---

### List Schema Versions

```
GET /schemas
```

Lists all available MIAPPE schema versions.

**Response:**

```json
{
  "versions": ["1.1", "1.2"]
}
```

---

### List Entities for Version

```
GET /schemas/{version}
```

Lists all entities available in a specific schema version.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `version` | path | Schema version (e.g., `1.1`) |

**Response:**

```json
{
  "version": "1.1",
  "entities": ["Investigation", "Study", "ObservationUnit", "Sample"]
}
```

**Errors:**

- `404`: Version not found

---

### Get Entity Schema

```
GET /schemas/{version}/{entity}
```

Returns the JSON Schema for a specific entity.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `version` | path | Schema version (e.g., `1.1`) |
| `entity` | path | Entity name (e.g., `Investigation`) |

**Response:**

Returns a standard JSON Schema object with properties, required fields, and type definitions.

**Errors:**

- `404`: Entity or version not found

---

### Validate Entity Data

```
POST /validate
```

Validates data against an entity schema.

**Request Body:**

```json
{
  "entity": "Investigation",
  "version": "1.1",
  "data": {
    "investigation_unique_id": "inv001",
    "investigation_title": "My Investigation"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `entity` | string | yes | Entity type to validate against |
| `version` | string | no | Schema version (default: `1.1`) |
| `data` | object | yes | Data to validate |

**Response:**

```json
{
  "valid": true,
  "errors": []
}
```

When validation fails:

```json
{
  "valid": false,
  "errors": [
    {
      "field": "investigation_title",
      "message": "Field required",
      "rule": "required"
    }
  ]
}
```

**Errors:**

- `404`: Entity not found

---

## UI API Endpoints

These endpoints support the web UI and are available when running the UI server.

### Entity Lookup

```
GET /api/lookup/{entity_type}
```

Searches entities for autocomplete functionality.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `entity_type` | path | Entity type (e.g., `ObservationUnit`) |
| `q` | query | Search query (optional) |

**Response:**

```json
{
  "results": [
    {"value": "ou001", "label": "Observation Unit 1"},
    {"value": "ou002", "label": "Observation Unit 2"}
  ]
}
```

---

### Reference Fields

```
GET /api/reference-fields/{entity_type}
```

Returns reference field definitions for an entity type, showing which fields reference other entities.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `entity_type` | path | Entity type |

**Response:**

```json
{
  "study_id": {"target_type": "Study", "required": true},
  "sample_ids": {"target_type": "Sample", "required": false}
}
```

---

### Graph Data

```
GET /api/graph
```

Returns node and edge data for entity relationship visualization.

**Response:**

```json
{
  "nodes": [
    {"id": "inv001", "label": "Investigation 1", "group": "Investigation"}
  ],
  "edges": [
    {"from": "study001", "to": "inv001", "label": "belongs_to"}
  ]
}
```

---

### Compare Profiles

```
POST /api/compare
```

Compares multiple profile specifications to identify differences.

**Request Body:**

```json
["miappe/1.1", "isa/1.0"]
```

An array of profile identifiers in `profile/version` format. At least 1 profile required.

**Response:**

```json
{
  "profiles": ["miappe/1.1", "isa/1.0"],
  "statistics": {
    "total_entities": 15,
    "common_entities": 8,
    "unique_entities": 7,
    "modified_entities": 3,
    "total_fields": 120,
    "common_fields": 45,
    "modified_fields": 12,
    "conflicting_fields": 2
  },
  "entity_diffs": [
    {
      "entity_name": "Investigation",
      "diff_type": "modified",
      "profiles": ["miappe/1.1", "isa/1.0"],
      "field_diffs": [...],
      "has_conflicts": false
    }
  ]
}
```

**Errors:**

- `400`: Invalid profile format or insufficient profiles
- `500`: Profile load error

---

### Merge Profiles

```
POST /api/merge
```

Merges multiple profile specifications into a single profile.

**Request Body:**

```json
{
  "profiles": ["miappe/1.1", "isa/1.0"],
  "strategy": "first_wins",
  "output_name": "merged",
  "output_version": "1.0"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `profiles` | array | yes | Profile identifiers (minimum 2) |
| `strategy` | string | no | Merge strategy (default: `first_wins`) |
| `output_name` | string | no | Name for merged profile (default: `merged`) |
| `output_version` | string | no | Version for merged profile (default: `1.0`) |

**Merge Strategies:**

- `first_wins`: First profile takes precedence on conflicts
- `last_wins`: Last profile takes precedence on conflicts
- `most_restrictive`: Choose stricter constraints
- `least_restrictive`: Choose looser constraints
- `prefer_<profile>`: Prefer a specific profile (e.g., `prefer_miappe`)

**Response:**

```json
{
  "merged_profile": {...},
  "yaml": "version: 1.0\nname: merged\n...",
  "strategy_used": "first_wins",
  "source_profiles": ["miappe/1.1", "isa/1.0"],
  "warnings": [],
  "has_unresolved_conflicts": false,
  "unresolved_conflicts": [],
  "resolutions_applied": 5
}
```

**Errors:**

- `400`: Invalid profile format or fewer than 2 profiles
- `500`: Profile load error

---

## Error Responses

All errors follow a standard format:

```json
{
  "detail": "Error message describing the problem"
}
```

## Authentication

Authentication is not currently implemented. The API runs without authentication.

## Rate Limiting

Rate limiting is not currently implemented.
