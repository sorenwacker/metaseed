# Metadata Extraction Agent

## Overview

An AI-powered agent that helps users fill in metadata by analyzing source files and mapping them to a selected metadata profile. The agent is exposed via MCP (Model Context Protocol) server, allowing use with Claude Desktop or other MCP-compatible clients.

## Goals

1. **Reduce manual data entry** - automatically extract metadata from existing files
2. **Profile-aware extraction** - understand what entities and fields the selected profile expects
3. **Conversational workflow** - MCP client (Claude Desktop) handles user interaction
4. **Reusable architecture** - core library usable via MCP, REST API, CLI, or embedded in other tools

## User Workflow

1. User connects Claude Desktop to the metaseed MCP server
2. User asks Claude to help extract metadata from their files
3. Claude uses MCP tools to:
   - List available profiles
   - Parse user's source files
   - Analyze column mappings
   - Extract entity instances
   - Validate extracted data
   - Export to YAML/JSON
4. Claude guides the user through confirming mappings and fixing validation errors
5. Final metadata is exported and ready for use

## Architecture

```
┌─────────────────────────────────────────┐
│         MCP Server (interface)          │
│  Tools: analyze_file, extract_entities  │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────┴───────────────────────┐
│         Core Library (logic)            │
│  ExtractionContext, EntityMapper        │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────┴───────────────────────┐
│         Parsers (file handling)         │
│  CSV, JSON, Excel                       │
└─────────────────────────────────────────┘
```

**Key principle**: Core library has no MCP dependencies. MCP server wraps the core library. This allows future REST API or Web UI to reuse the same core.

## Components

### 1. Extraction Core (`src/metaseed/agent/core.py`)

Central orchestration logic:

```python
class ExtractionContext:
    """Manages an extraction session."""

    profile: ProfileSpec
    sources: list[ParsedContent]
    mappings: dict[str, ColumnMapping]
    extracted: dict[str, list[dict]]

    @classmethod
    def from_profile(cls, profile_name: str, version: str) -> ExtractionContext:
        """Create context from profile name and version."""

    def add_source(self, path: Path) -> ParsedContent:
        """Parse and add a source file."""

    def suggest_mapping(self, source_index: int, entity_name: str) -> list[FieldMapping]:
        """Suggest column mappings for an entity."""

    def extract_entities(self, source_index: int, entity_name: str) -> ExtractionResult:
        """Extract entity instances from a source."""

    def validate_instance(self, data: dict, entity_name: str) -> list[ValidationError]:
        """Validate extracted data against entity spec."""

    def export_yaml(self, entity_name: str | None = None) -> str:
        """Export extracted entities to YAML."""

    def export_json(self, entity_name: str | None = None) -> str:
        """Export extracted entities to JSON."""
```

### 2. Column Mapping (`src/metaseed/agent/mapping.py`)

Maps source file columns to entity fields:

```python
class FieldMapping:
    """Mapping from a source column to an entity field."""
    field_name: str
    source_column: str | None
    confidence: float
    default_value: str | None

class ColumnMapping:
    """Complete mapping configuration for extracting an entity."""
    entity_name: str
    fields: list[FieldMapping]
    source_table: str | int | None

def suggest_mapping(
    source_columns: list[str],
    entity_spec: EntitySpec,
    threshold: float = 0.5,
) -> list[FieldMapping]:
    """Suggest column-to-field mappings based on name similarity."""
```

### 3. File Parser Registry (`src/metaseed/agent/parsers/`)

Pluggable parsers for different file formats:

```python
class ParserRegistry:
    """Registry of file format parsers."""

    def register(self, parser: FileParser) -> None:
        """Register a parser for a file type."""

    def parse(self, path: Path) -> ParsedContent:
        """Parse file using appropriate parser."""

class FileParser(Protocol):
    """Protocol for file parsers."""
    extensions: list[str]
    mime_types: list[str]

    def parse(self, path: Path) -> ParsedContent:
        """Parse file into structured content."""
```

Built-in parsers:
- `CSVParser` - CSV/TSV files with header detection and dialect sniffing
- `JSONParser` - JSON files (arrays or objects with array fields)
- `ExcelParser` - Excel workbooks (.xlsx, .xls) with multiple sheet support

### 4. MCP Server (`src/metaseed/agent/mcp/server.py`)

Exposes agent capabilities via Model Context Protocol:

#### Resources (read-only data)

| Resource URI | Description |
|--------------|-------------|
| `profile://list` | List all available profiles |
| `profile://{name}/{version}` | Profile schema overview |
| `profile://{name}/{version}/entity/{entity}` | Single entity definition |

#### Tools (actions)

**File Extraction Tools:**

| Tool | Description |
|------|-------------|
| `list_profiles` | List available profiles with versions |
| `get_profile_schema` | Get full profile schema with entities |
| `parse_source_file` | Parse a file and return structure |
| `analyze_mapping` | Suggest how file columns map to entity fields |
| `extract_entities` | Extract entity instances from file using mapping |
| `validate_extracted` | Validate extracted data against profile |
| `export_metadata` | Export extracted metadata to YAML/JSON |

**Dataset Management Tools:**

| Tool | Description |
|------|-------------|
| `list_datasets` | List all saved datasets |
| `load_dataset` | Load a dataset into the editor |
| `save_dataset` | Save current entities to a dataset |
| `create_dataset` | Create a new empty dataset with a profile |

**Entity Management Tools:**

| Tool | Description |
|------|-------------|
| `list_entities` | List all entities in the current dataset |
| `get_entity_tree` | Get hierarchical tree showing parent-child relationships |
| `get_entity` | Get a specific entity by node ID |
| `create_entity` | Create entity with optional `parent_id` (auto-fills parent references). On success returns `hints` (`expected_children`, `typical_next`, `cross_ref_consumers`); on validation errors returns `identifier_field`, `field_types`, `valid_fields`, `required_fields`, and a `hint` |
| `batch_create` | Create multiple entities in one operation with `[{entity_type, data, parent_id?}, ...]` |
| `link_entity` | Link existing entity as child of another |
| `update_entity` | Update an existing entity (auto-saves) |
| `bulk_update_entities` | Update multiple entities at once |
| `delete_entity` | Delete an entity (auto-saves) |

**Building Hierarchies:** Use `parent_id` when creating entities. The MCP server automatically:
1. Fills the child's reference field (e.g., `Study.investigation_id` from parent's `unique_id`)
2. Updates the parent's list field (e.g., `Investigation.studies` to include the child)
3. Saves the dataset

```
create_entity("Study", {"unique_id": "study-1", "title": "..."}, parent_id="<investigation_node_id>")
```
Or link after creation:
```
link_entity(child_id="<study_id>", parent_id="<investigation_id>")
```

**Batch Creation:** Create multiple entities in one call:
```
batch_create([
    {"entity_type": "Investigation", "data": {"unique_id": "inv-1", "title": "Test"}},
    {"entity_type": "Study", "data": {"unique_id": "st-1", "title": "Trial"}, "parent_id": "<inv_node_id>"}
])
```
Returns `{total, created, failed, results}` with detailed error info per entity.

**Schema Discovery:** Before creating entities, discover field requirements:
```
get_entity_fields("Investigation", "miappe", "1.2")  # Full field info
get_required_fields("Study", "miappe", "1.2")        # Just required field names
get_entity_template("Investigation", "miappe", "1.2") # Template with placeholders
```

**Validation Tools:**

| Tool | Description |
|------|-------------|
| `validate_dataset` | Validate all entities (same logic as UI - single source of truth) |
| `validate_relationships` | Flag relationship-completeness gaps the schema implies but does not enforce: empty list-references, entities of a referenced type that nothing points at, and containers with no child of a type they can hold. Derived from the profile's own `nested_fields`/`reference_fields` (profile-agnostic) |
| `validate_ontology_terms` | Check every filled `ontology_term` field against OLS (restricted to the field's declared ontologies) and report `valid` plus suggested terms. Fails open when OLS is unreachable |
| `get_field_spec` | Get field definitions, constraints, and ontology terms |

**Schema Discovery Tools:**

| Tool | Description |
|------|-------------|
| `get_profile_relationships` | Entity relationship map: per type, its `identifier`, child types (`children`), and `cross_references` (which entity/field each reference points at). Use before creating to build relational, not flat, datasets |
| `get_example_dataset` | One instance of every entity type with required fields filled and every reference wired to the matching example - a correct relational pattern to copy. Values are placeholders; built from the profile schema (any spec) |
| `get_entity_fields` | Get all fields for an entity type with `(entity_type, profile, version)` |
| `get_required_fields` | Get list of required field names for an entity type |
| `get_entity_template` | Get template with placeholder values by field type |

`get_entity_fields`, `get_required_fields`, and `get_entity_template` all return
the entity's `identifier_field`, plus a `note` for types that break the usual
`unique_id` convention (e.g. `Person` keys on `name`). On validation failure,
`create_entity` likewise reports `identifier_field`, `field_types`, and a
corrective `hint` when an id alias such as `unique_id` is sent to the wrong type.
Each error detail also carries the field's `description` and `constraints`
(pattern, range, enum), so a format error explains the expected shape.

The `validate_dataset` tool uses the same validation as the web UI, checking:
- Required fields
- Type constraints (from Pydantic models)
- Custom validation rules (from profile spec)
- Returns `rules_checked` array showing which rules were applied

#### Prompts (reusable templates)

| Prompt | Description |
|--------|-------------|
| `extraction_guide` | Step-by-step instructions for extraction |
| `field_mapping_help` | Help for adjusting column mappings |

## Data Flow

### 1. Parse Source File

```
User provides file path
       │
       ▼
┌──────────────────┐
│ ParserRegistry   │
│ selects parser   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Parser extracts  │
│ tables, headers, │
│ and rows         │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Return           │
│ ParsedContent    │
└──────────────────┘
```

### 2. Analyze Mapping

```
Source columns + Entity spec
       │
       ▼
┌──────────────────┐
│ Normalize names  │
│ (snake_case,     │
│  camelCase, etc) │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Compute          │
│ similarity       │
│ scores           │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Suggest mappings │
│ with confidence  │
└──────────────────┘
```

### 3. Extract Entities

```
Mapping + Source table
       │
       ▼
┌──────────────────┐
│ For each row:    │
│ - Apply mapping  │
│ - Convert types  │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Return instances │
│ and any errors   │
└──────────────────┘
```

## CLI Usage

Start the MCP server:

```bash
# For Claude Desktop (stdio transport)
metaseed mcp

# For debugging (HTTP transport)
metaseed mcp --transport http --port 8000
```

### Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "metaseed": {
      "command": "metaseed",
      "args": ["mcp"]
    }
  }
}
```

## Example Usage with Claude Desktop

**User**: "I have a CSV file with experiment data. Help me extract MIAPPE metadata."

**Claude** (using MCP tools):
1. Calls `list_profiles` → shows MIAPPE available
2. Calls `parse_source_file` with the CSV → sees columns
3. Calls `get_profile_schema` for MIAPPE → understands entities
4. Calls `analyze_mapping` → suggests column mappings
5. Asks user to confirm/adjust mappings
6. Calls `extract_entities` → extracts instances
7. Calls `validate_extracted` → checks for errors
8. Calls `export_metadata` → saves to file

## File Structure

```
src/metaseed/agent/
├── __init__.py              # Public API exports
├── core.py                  # ExtractionContext, extraction logic
├── mapping.py               # Column-to-field mapping
├── questions.py             # Question types (for future interactive use)
├── parsers/
│   ├── __init__.py
│   ├── registry.py          # ParserRegistry, ParsedContent, ParsedTable
│   ├── csv.py               # CSV/TSV parser
│   ├── json.py              # JSON parser
│   └── excel.py             # Excel parser
├── llm/                     # LLM abstraction (for future direct LLM use)
│   ├── __init__.py
│   ├── base.py
│   └── anthropic.py
└── mcp/
    ├── __init__.py
    └── server.py            # MCP server implementation
```

## Dependencies

Required:
- `mcp>=1.0.0` - MCP server SDK
- `pydantic>=2.0` - Data validation
- `openpyxl>=3.1` - Excel parsing
- `pyyaml>=6.0` - YAML export

## Testing

Run agent tests:

```bash
uv run pytest tests/test_agent/ -v
```

Tests cover:
- File parsing (CSV, JSON, Excel)
- Column mapping suggestions
- Entity extraction
- MCP server tools and resources

## Claude Code Integration

The MCP server can be used with Claude Code for AI-assisted metadata extraction.

### Setup via CLI (recommended)

Add metaseed to your user config (available in all projects):

```bash
claude mcp add --scope user --transport stdio metaseed -- \
  uv --directory /path/to/metaseed run metaseed mcp
```

Or add to a specific project only:

```bash
claude mcp add --scope project --transport stdio metaseed -- \
  uv --directory /path/to/metaseed run metaseed mcp
```

### Manual Setup

**User scope** - add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "metaseed": {
      "command": "uv",
      "args": ["--directory", "/path/to/metaseed", "run", "metaseed", "mcp"]
    }
  }
}
```

**Project scope** - add `.mcp.json` to project root:

```json
{
  "mcpServers": {
    "metaseed": {
      "command": "uv",
      "args": ["--directory", "/path/to/metaseed", "run", "metaseed", "mcp"]
    }
  }
}
```

### Usage

After restarting Claude Code, ask:

- "List available metadata profiles"
- "Parse data.csv and show me the columns"
- "Suggest MIAPPE mappings for this CSV"
- "Extract Investigation entities from my file"
- "Validate the extracted data"
- "Export as YAML"

### Web UI Integration

The metaseed web app includes an MCP toggle button in the header:

1. Start the app: `make dev` (runs at http://127.0.0.1:8765)
2. Click the **MCP** button to start/stop the server
3. Green dot = running at `http://127.0.0.1:8001`
4. External MCP clients can connect via HTTP transport

**State Sharing:** The UI and MCP server share the same state. Changes made via MCP are reflected in the UI after refreshing the browser.

**Claude Desktop HTTP Config** (for use with UI):

```json
{
  "mcpServers": {
    "metaseed": {
      "url": "http://127.0.0.1:8001/mcp"
    }
  }
}
```

### Creating Datasets via MCP

When creating hierarchical entities, use `parent_id` to link child entities to parents:

```python
# 1. Create the Investigation first
create_entity("Investigation", {"unique_id": "inv-001", "title": "My Study"})

# 2. Create Study with parent_id - investigation_id is auto-filled
create_entity("Study", {"unique_id": "study-001", "title": "Trial 1"}, parent_id="<inv_node_id>")
```

The MCP server automatically:
- Fills the child's reference field (e.g., `Study.investigation_id`) from the parent's identifier
- Updates the parent's list field (e.g., `Investigation.studies`) to include the child
- Saves the dataset after each entity creation

Ask Claude to create a complete dataset:

```
Create a new MIAPPE dataset called "wheat-experiment" with:

Investigation:
- Unique ID: "wheat-drought-2024"
- Title: "Wheat Drought Stress Response Study"

Study (as child of Investigation):
- Unique ID: "field-trial-2024"
- Title: "Field Trial 2024"

Then validate the dataset and show me the entity tree.
```

After MCP creates entities, refresh your browser to see them in the UI graph.

### Testing MCP with Claude Code

1. Start the web UI: `make dev`
2. Click the **MCP** button to start the MCP server (green dot = running)
3. Connect Claude Code to the MCP server (see setup above)
4. Test with commands like:
   - "List available metadata profiles"
   - "Create a MIAPPE dataset called test-dataset"
   - "Show me the entity tree"

**After code changes:**
- Click MCP button off then on to restart the server with new code
- Or run `uv pip install -e .` and restart the MCP server

## Future Enhancements

1. **REST API** - HTTP endpoints for web integration
2. **Direct LLM integration** - Use LLM for intelligent field mapping
3. **Additional parsers** - PDF, XML, text pattern extraction
4. **Batch processing** - Process multiple files at once
5. **Persistent sessions** - Save and resume extraction sessions
