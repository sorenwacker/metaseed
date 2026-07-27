"""MCP tools receive their session; they never go looking for one.

This is a gate, not a description. The pattern it forbids has now been
reintroduced three times, always the same way: a ``from metaseed.agent.mcp.server
import get_mcp_state`` placed *inside a function body*, where an import-graph
linter cannot see it. The check is therefore an AST walk at any nesting depth,
not an import check.

The rule matters because a tool that resolves its own session can only resolve a
process-wide one, and a process-wide session is another caller's data the moment
a host serves more than one.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

TOOLS_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "metaseed" / "agent" / "mcp" / "tools"
)

# Choosing its own context is exactly what a tool must not do.
_FORBIDDEN_CONTEXT_NAMES = {
    "resolve_default_context",
    "set_default_context",
    "default_context",
}

# A module with no session-dependent tool. Named rather than inferred, so adding
# one forces a deliberate answer instead of silently defaulting to "stateless".
_STATELESS = {"extraction.py"}


def _tools_modules() -> list[Path]:
    return sorted(p for p in TOOLS_DIR.glob("*.py") if p.name != "__init__.py")


def _violations(tree: ast.Module) -> list[str]:
    """Every place a module reaches for a session instead of being given one."""
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "metaseed.agent.mcp.server":
                names = ", ".join(alias.name for alias in node.names)
                found.append(f"line {node.lineno}: imports {names} from the server")
            elif module == "metaseed.agent.mcp.context":
                for alias in node.names:
                    if alias.name in _FORBIDDEN_CONTEXT_NAMES:
                        found.append(
                            f"line {node.lineno}: chooses its own context ({alias.name})"
                        )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "metaseed.agent.mcp.server":
                    found.append(f"line {node.lineno}: imports the server module")
    return found


@pytest.mark.parametrize("path", _tools_modules(), ids=lambda p: p.name)
def test_a_tools_module_does_not_reach_for_a_session(path: Path) -> None:
    violations = _violations(ast.parse(path.read_text()))

    assert not violations, f"{path.name} reaches for ambient state:\n  " + "\n  ".join(
        violations
    )


@pytest.mark.parametrize("path", _tools_modules(), ids=lambda p: p.name)
def test_every_registrar_is_handed_a_resolver(path: Path) -> None:
    """A registrar without ``resolve_context`` has no way to serve a caller."""
    tree = ast.parse(path.read_text())
    registrars = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("register_")
    ]
    assert registrars, f"{path.name} registers no tools"

    for registrar in registrars:
        params = {arg.arg for arg in registrar.args.args}
        if path.name in _STATELESS:
            assert "resolve_context" not in params, (
                f"{path.name} is listed as stateless but takes a resolver; "
                "remove it from the allowlist"
            )
        else:
            assert "resolve_context" in params, (
                f"{registrar.name} in {path.name} is not handed a resolver, so it "
                "can only serve a process-wide session"
            )


def test_the_gate_catches_a_nested_import() -> None:
    """The check must see the dodge that keeps recurring: an import hidden in a
    function body, where an import-graph linter never looks."""
    source = """
def some_tool():
    from metaseed.agent.mcp.server import get_mcp_state

    return get_mcp_state()
"""

    assert _violations(ast.parse(source)), "a function-body import slipped past"


def test_the_gate_allows_being_handed_a_context() -> None:
    source = """
from metaseed.agent.mcp.context import MCPContext, ResolveContext

def register_x_tools(mcp, resolve_context: ResolveContext) -> None:
    pass
"""

    assert _violations(ast.parse(source)) == []
