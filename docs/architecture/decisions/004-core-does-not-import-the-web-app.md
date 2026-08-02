# ADR 004: Core Packages Do Not Import the Web App

**Date:** 2026-08-02
**Status:** Accepted
**Context:** Issue #71 (part of #61, Modularity)

## Decision

`metaseed.ui` is a host, not a library layer. No module outside `metaseed.ui` imports `metaseed.ui`, at module level or inside a function body, except two declared seams:

| Seam | Why it exists |
|------|---------------|
| `metaseed.agent.mcp.ui_session` | The MCP host edits the same local editing session as the web UI. |
| The `ui` command in `metaseed.cli.app` | The CLI launches the web app; that is what the command is for. |

Everything else — `metaseed.specs`, `metaseed.models`, `metaseed.facade`, `metaseed.validators`, `metaseed.dcat`, `metaseed.repositories`, `metaseed.api.client`, `metaseed.cli`, the rest of `metaseed.agent` — depends only downward.

## Context

A consumer embedding metaseed's tools should not pay for FastAPI. Two edges broke that:

1. `metaseed/cli/migrate.py` imported `get_datasets_dir` from `metaseed.ui.datasets` at module level. `metaseed/ui/__init__.py` eagerly imported `metaseed.ui.app`, so importing a dataset-migration CLI command constructed the entire web application (`fastapi`, `starlette`, `metaseed.ui.app` all in `sys.modules`).
2. `metaseed/repositories/memory.py` annotated `MemoryEntityRepository` with `AppState` and `TreeNode` from `metaseed.ui.state`. The import was `TYPE_CHECKING`-only, so it cost nothing at runtime, but the data layer still named the UI as its type.

A third group — roughly 25 imports under `metaseed/agent/mcp/` — is not the same defect. Those reach for `AppState`, `EntityService`, `DatasetManager`, `DatasetManagerFactory` and the `metaseed.ui.datasets` helpers because an MCP tool and a web route edit *one* session: a tool call and a browser click must land in the same dataset. That dependency is real. Hidden inside function bodies it was invisible to an import-graph linter and indistinguishable from the two defects above.

## Considered Alternatives

### Alternative 1: Move the session layer (`AppState`, `EntityService`, `DatasetManager`, dataset helpers) out of `metaseed.ui`

The honest long-term shape: this layer is framework-free and has two hosts.

**Rejected for now because:** `metaseed.ui.state` alone has 85 references across `src/` and `tests/`, the test suite patches module attributes by path (`metaseed.ui.datasets.…`), and metaseed-hub imports these names through its own boundary module. The move is a separate, larger change; doing it inside this one would have meant rewriting tests that must stay untouched to keep proving the behaviour.

### Alternative 2: Leave the MCP imports inside function bodies

**Rejected because:** a coupling a linter cannot see is a coupling that grows. The `cli/migrate.py` edge was found only by importing modules one by one in a fresh interpreter.

### Alternative 3: Hoist all ~25 MCP imports to module level, each naming its own `metaseed.ui.*` module

Explicit, but it spreads the seam over eight files and makes the guard's exception list eight entries long.

## Consequences

- `get_datasets_dir()` lives in `metaseed.paths`, next to `get_user_data_dir()` and `get_user_specs_dir()`. It resolves through `metaseed.repositories.filesystem_dataset.default_datasets_dir()`, so `METASEED_DATASETS_DIR` and the repository now agree on one directory; before, the migration CLI ignored the override the repository honoured.
- `metaseed.repositories.base` defines `EntityTreeState` and `EntityTreeNode` protocols describing the state `MemoryEntityRepository` reads. `AppState` and `TreeNode` satisfy them structurally; the data layer no longer names the UI.
- `metaseed/ui/__init__.py` resolves `create_app` and `run_ui` on first attribute access (PEP 562). Importing a leaf module such as `metaseed.ui.state` no longer constructs the FastAPI application, so the MCP host can hold a session without a web server. The ASGI application object is no longer re-exported from the package: on `metaseed.ui` the name `app` is the submodule, and a lazily resolved export under the same name would depend on who imported first. `metaseed.ui.app:app` is unchanged and remains the ASGI target.
- `metaseed.agent.mcp.ui_session` re-exports the session names the MCP host uses. Its imports are module level: the dependency is declared once, in one file, and shows up in an import graph. `metaseed.ui.datasets` is re-exported as a module (`ui_datasets`) rather than as individual functions, so calls still resolve through the defining module exactly as the function-level imports they replace did.
- `tests/test_modularity.py` is the gate. It walks the AST of every module under `src/metaseed` outside `metaseed/ui`, catching function-level and `TYPE_CHECKING` imports, and names file and line for every offender. It also imports each core package in a fresh interpreter and fails if `fastapi`, `starlette` or `metaseed.ui.app` reaches `sys.modules` — a transitive leak an AST scan cannot see.

`metaseed.agent.mcp.server` still loads `starlette`: `mcp.server.fastmcp` imports it. That is the MCP SDK's dependency, not a metaseed edge, so the guard checks the MCP host for `fastapi` and `metaseed.ui.app` only.
