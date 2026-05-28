# ADR 001: ProfileFacade as Single Source of Truth for Entity Graph

**Date:** 2026-05-21
**Status:** Accepted
**Context:** Relationship linking logic scattered across multiple files

## Decision

Make `ProfileFacade` the single source of truth for entity storage, relationship resolution, and tree/graph generation.

## Context

Prior to this change, entity relationship management was distributed across multiple components:

| Component | Responsibility |
|-----------|---------------|
| `AppState` | TreeNode storage, `nodes_by_id`, `entity_tree` |
| `dataset_manager.py` | 3-pass linking during load (parent_id, nested arrays, reference fields) |
| `TreeNode` | Parent-child relationships via `parent_id` and `children` list |
| `graph.py` | vis.js graph generation |

This created several problems:

1. **Duplication** - Linking logic duplicated in sync/async DatasetManagers
2. **UI coupling** - Entity graph only accessible through UI's AppState
3. **JupyterLab blocked** - Cannot use entity graph in notebooks
4. **MCP complexity** - MCP tools must interact via AppState

## Considered Alternatives

### Alternative 1: Keep status quo, add facade wrapper

Create facade methods that delegate to AppState.

**Rejected because:**
- Increases complexity rather than reducing it
- Still requires AppState for any entity operations
- JupyterLab use case still blocked

### Alternative 2: Move everything to a new EntityGraph class

Create dedicated `EntityGraph` class separate from ProfileFacade.

**Rejected because:**
- ProfileFacade already has entity helpers and schema knowledge
- Would create yet another layer of indirection
- ProfileFacade is already the natural home for "profile + entities"

### Alternative 3: ProfileFacade as entity storage (chosen)

Extend ProfileFacade with:
- `_instances: dict[str, EntityNode]` - Entity storage
- `_index: dict[str, str]` - Identifier lookup (alias/unique_id -> node_id)
- `add_entity()`, `get_entity()`, `get_tree()`, `to_graph()`, `to_dict()`, `load_from_dict()`

## Consequences

### Positive

1. **Single source of truth** - All entity operations go through facade
2. **JupyterLab enabled** - `facade.add_entity()`, `facade.get_tree()` work standalone
3. **MCP simplified** - MCP tools can use facade directly
4. **Reduced duplication** - One implementation of linking logic in `load_from_dict()`
5. **Testable** - Facade can be unit tested without UI

### Negative

1. **AppState complexity** - AppState becomes a thin wrapper with caching
2. **TreeNode compatibility** - Must maintain TreeNode wrappers for existing UI code
3. **Migration** - Existing code using AppState.nodes_by_id still works but goes through cache

### Neutral

1. **No API change** - AppState still provides `nodes_by_id`, `entity_tree`, `add_node()`
2. **Serialization unchanged** - Same JSON format (`_type`, `_parent_unique_id`)

## Implementation

```
ProfileFacade
    +-- _entities: dict[str, EntityHelper]     # Schema helpers (existing)
    +-- _instances: dict[str, EntityNode]      # NEW: Entity instances
    +-- _index: dict[str, str]                 # NEW: alias -> node_id
    +-- add_entity() -> EntityNode             # NEW: Auto-links via reference fields
    +-- get_tree() -> list[dict]               # NEW: For UI/visualization
    +-- to_graph() -> dict                     # NEW: vis.js format
    +-- to_dict() -> list[dict]                # NEW: Serialization
    +-- load_from_dict() -> int                # NEW: Deserialization

AppState
    +-- facade: ProfileFacade                  # Delegates to facade
    +-- _tree_cache: list[TreeNode]            # Cache for backward compat
    +-- _nodes_cache: dict[str, TreeNode]      # Cache for backward compat
    +-- add_node() -> TreeNode                 # Delegates to facade.add_entity()
    +-- get_tree_data() -> list[dict]          # Delegates to facade.get_tree()
```

## Usage

### JupyterLab/CLI (new capability)

```python
from metaseed.facade import ProfileFacade

facade = ProfileFacade("miappe", "1.1")
facade.add_entity("Investigation", {"unique_id": "INV-001", "title": "My Study"})
facade.add_entity("Study", {"unique_id": "S-001", ...}, parent_id=inv_node.id)
print(facade.get_tree())  # Hierarchical view
```

### UI (unchanged)

```python
state.add_node("Investigation", instance)  # Still works, delegates to facade
state.nodes_by_id["abc"].children          # Still works, via TreeNode cache
```

## References

- `src/metaseed/facade.py` - ProfileFacade with EntityNode storage
- `src/metaseed/ui/state.py` - AppState with delegation to facade
- `src/metaseed/ui/dataset_manager.py` - Simplified loading via facade
- `src/metaseed/ui/services/graph.py` - Delegates to facade.to_graph()
