# Profile Comparison

Metaseed provides tools for comparing profile specifications. This is useful for understanding differences between metadata standards and identifying common elements.

## Web Interface

Access the comparison UI at `/merge/` when running the web interface:

```bash
metaseed ui
# Then visit http://127.0.0.1:8080/merge/
```

### Using the Compare Tool

1. **Select Base Profile**: Choose the reference profile and version from the first dropdown
2. **Select Compare Profile**: Choose the profile to compare against
3. **Click Compare**: View the differences in the ERD visualization

The first profile selected is treated as the **base/reference**. Differences are shown relative to this base:

- **Added** (green): Elements in the compare profile but not in the base
- **Removed** (red): Elements in the base profile but not in compare
- **Modified** (amber): Elements in both but with different attributes
- **Unchanged** (gray): Elements identical in both profiles

### ERD Visualization

The comparison displays an interactive entity-relationship diagram:

**Entity Colors:**

| Color | Meaning |
|-------|---------|
| Gray | Entity exists in both profiles (unchanged) |
| Green | Entity only in compare profile (added) |
| Red | Entity only in base profile (removed) |
| Amber | Entity in both but fields differ (modified) |

**Edge Colors:**

| Color | Meaning |
|-------|---------|
| Gray | Relationship exists in both profiles |
| Green | Relationship only in one profile |

**Field Indicators:**

| Symbol | Meaning |
|--------|---------|
| `+` | Field added (in compare, not in base) |
| `-` | Field removed (in base, not in compare) |
| `~` | Field modified (different attributes) |
| `!` | Field conflict (incompatible differences) |
| `*` | Required field |

### Export Reports

After comparing, export the results:

- **MD**: Markdown report with tables
- **CSV**: Spreadsheet-compatible format
- **HTML**: Styled HTML report

## Python API

### Comparing Profiles

```python
from metaseed.specs.merge import compare

# Compare ISA with JERM (ISA is the base)
result = compare([
    ("isa", "1.0"),
    ("jerm", "1.0"),
])

# Access statistics
print(f"Total entities: {result.statistics.total_entities}")
print(f"Common entities: {result.statistics.common_entities}")
print(f"Conflicting fields: {result.statistics.conflicting_fields}")

# Iterate through entity differences
for entity_diff in result.entity_diffs:
    print(f"{entity_diff.entity_name}: {entity_diff.diff_type.value}")

    for field_diff in entity_diff.field_diffs:
        if field_diff.diff_type.value != "unchanged":
            print(f"  {field_diff.field_name}: {field_diff.diff_type.value}")
```

### Generating Reports

```python
from metaseed.specs.merge import compare, MarkdownReportGenerator

result = compare([("isa", "1.0"), ("jerm", "1.0")])

# Generate Markdown report
report = MarkdownReportGenerator(result).generate()
print(report)

# Or CSV/HTML
from metaseed.specs.merge import CSVReportGenerator, HTMLReportGenerator

csv_report = CSVReportGenerator(result).generate()
html_report = HTMLReportGenerator(result).generate()
```

### Visualization Data

Generate vis.js compatible graph data:

```python
from metaseed.specs.merge import compare, DiffVisualizer

result = compare([("isa", "1.0"), ("jerm", "1.0")])

visualizer = DiffVisualizer()
graph_data = visualizer.build_diff_graph(result)

# graph_data contains:
# - nodes: Entity nodes with diff colors and field data
# - edges: Relationships with colors based on profile presence
# - legend: Color legend for diff types
# - statistics: Summary statistics
```

## Available Profiles

| Profile | Description |
|---------|-------------|
| `isa/1.0` | Investigation-Study-Assay framework |
| `miappe/1.1`, `miappe/1.2` | Plant phenotyping metadata |
| `jerm/1.0` | Just Enough Results Model (FAIRDOM-SEEK) |
| `darwin-core/1.0` | Biodiversity data standard |
| `dissco/0.4` | Digital Specimen standard |

## Diff Types

| Type | Description |
|------|-------------|
| `unchanged` | Identical in all compared profiles |
| `added` | Present in compare profile, absent in base |
| `removed` | Present in base profile, absent in compare |
| `modified` | Present in both but with different attributes |
| `conflict` | Incompatible differences (e.g., different field types) |

## Data Models

### ComparisonResult

Contains the full comparison between profiles:

- `profiles`: List of profile identifiers compared
- `entity_diffs`: List of `EntityDiff` objects
- `statistics`: `ComparisonStatistics` with counts
- `metadata_diffs`: Differences in profile metadata
- `validation_rule_diffs`: Differences in validation rules

### EntityDiff

Represents differences for a single entity:

- `entity_name`: Name of the entity
- `diff_type`: `DiffType` enum value
- `profiles`: Dict mapping profile ID to presence (bool)
- `field_diffs`: List of `FieldDiff` objects
- `has_conflicts`: Whether any fields have conflicts

### FieldDiff

Represents differences for a single field:

- `field_name`: Name of the field
- `diff_type`: `DiffType` enum value
- `profiles`: Dict mapping profile ID to `FieldSpec` or None
- `attributes_changed`: List of attribute names that differ
- `is_conflict`: Whether this is a conflict

### ComparisonStatistics

Summary counts:

- `total_entities`: Total unique entities across all profiles
- `common_entities`: Entities present in all profiles
- `unique_entities`: Entities in only one profile
- `modified_entities`: Entities with differences
- `total_fields`: Total unique fields
- `common_fields`: Fields identical across profiles
- `conflicting_fields`: Fields with conflicts

## Profile Merging

Metaseed also supports merging multiple profiles into a single combined profile.

### CLI Usage

```bash
# Basic merge with default strategy (first_wins)
metaseed merge miappe/1.1 isa/1.0 -o combined.yaml

# Merge with most restrictive strategy
metaseed merge miappe/1.1 cropxr-phenotyping/0.0.5 -s most_restrictive -o strict.yaml

# Merge with custom name and version
metaseed merge miappe/1.1 isa/1.0 -n miappe-extended -v 2.0 -o extended.yaml

# Prefer a specific profile for conflicts
metaseed merge miappe/1.1 isa/1.0 -s prefer_miappe/1.1 -o miappe-based.yaml
```

### Python API

```python
from metaseed.specs.merge import merge

# Basic merge
result = merge(
    profiles=[("miappe", "1.1"), ("isa", "1.0")],
    strategy="first_wins",
    output_name="combined",
    output_version="1.0",
)

# Export to YAML
yaml_output = result.to_yaml()

# Export to dict
dict_output = result.to_dict()

# Check for warnings
for warning in result.warnings:
    print(f"{warning.entity_name}.{warning.field_name}: {warning.message}")
```

### Merge Strategies

| Strategy | Behavior |
|----------|----------|
| `first_wins` | Use first profile's value for conflicts |
| `last_wins` | Use last profile's value for conflicts |
| `most_restrictive` | `required=True` wins, tighter constraints |
| `least_restrictive` | `required=False` wins, looser constraints |
| `prefer_<profile>` | Always prefer specific profile (e.g., `prefer_miappe/1.1`) |

### MergeResult

Contains the merged profile and metadata:

- `merged_profile`: The resulting `ProfileSpec`
- `source_profiles`: List of profile identifiers merged
- `strategy_used`: Name of the merge strategy applied
- `resolutions_applied`: List of conflict resolutions
- `warnings`: List of warnings generated
- `has_unresolved_conflicts`: Whether conflicts remain

### ConflictResolution

Manual resolution for a specific conflict:

- `entity_name`: Entity containing the conflict
- `field_name`: Field with the conflict
- `attribute`: Attribute in conflict (e.g., "required", "type")
- `resolved_value`: Value to use for resolution
- `source_profile`: Profile the value was taken from (or None if custom)

### MergeWarning

Warning generated during merge:

- `entity_name`: Entity where warning occurred
- `field_name`: Field where warning occurred
- `message`: Warning message
- `resolution_applied`: Description of automatic resolution

## Strategy Functions

```python
from metaseed.specs.merge import list_strategies, get_strategy

# List all available strategies
strategies = list_strategies()
# Returns: ['first_wins', 'last_wins', 'most_restrictive', 'least_restrictive', 'prefer_<profile>']

# Get a specific strategy instance
strategy = get_strategy("most_restrictive")
```

## Manual Conflict Resolution

Override automatic conflict resolution with manual resolutions:

```python
from metaseed.specs.merge import merge, ConflictResolution

# Define manual resolution
resolution = ConflictResolution(
    entity_name="Study",
    field_name="title",
    attribute="required",
    resolved_value=True,
    source_profile="miappe/1.1",
)

# Apply during merge
result = merge(
    profiles=[("miappe", "1.1"), ("isa", "1.0")],
    strategy="first_wins",
    manual_resolutions=[resolution],
)

# Check applied resolutions
for res in result.resolutions_applied:
    print(f"Resolved {res.entity_name}.{res.field_name}: {res.resolved_value}")
```
