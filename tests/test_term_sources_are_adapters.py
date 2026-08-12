"""OLS is one term source, and nothing may assume it is the only one.

The rule is easy to state and was quietly broken everywhere: term lookup goes
through :func:`metaseed.services.terms.get_term_source`, which holds whichever
adapters are configured. Before this gate, the picker route and the MCP search
tool built OLS4 HTTP queries themselves, so a vocabulary held locally — a
consortium's own list, a Crop Ontology snapshot OLS does not host — could not
appear in a dropdown no matter what was configured.

Two things are checked: that no module reaches for the OLS service directly,
and that the lookup entry points ask the router. A rule kept by review alone
erodes; this is the gate for this one.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("src/metaseed")

#: Modules allowed to name the OLS service, with the reason.
MAY_USE_OLS_DIRECTLY: dict[str, str] = {
    "services/ontology.py": "is the OLS adapter",
    "services/terms.py": "composes it into the default router",
    "services/__init__.py": "re-exports it as public API",
}

#: Modules allowed to speak OLS4's HTTP API. Everything else asks the router.
MAY_CALL_OLS_HTTP: dict[str, str] = {
    "services/ontology.py": "is the OLS adapter",
    "agent/mcp/tools/ontology.py": (
        "holds the OLS catalogue tools — listing the ontologies a service "
        "hosts is a question about OLS, not about a term"
    ),
}

#: Entry points that resolve a term for a person or an agent. Each must reach
#: the configured sources — directly, or through ``check_term``, which does.
#: Each of these was OLS-only before.
MUST_ROUTE = {
    "ui/routes/api.py": ["search_ontology_terms"],
    "agent/mcp/tools/ontology.py": [
        "search_ontology",
        "get_ontology_term",
        "suggest_ontology_term",
    ],
    "services/term_check.py": ["check_term"],
    "validators/cv.py": ["validate_cv_terms"],
    "facade/helper.py": ["validate_ontology_term"],
}

#: Either of these means the call reaches whatever adapters are configured.
ROUTES_VIA = ("get_term_source", "check_term")


def _modules() -> list[tuple[str, ast.AST]]:
    found = []
    for path in sorted(SRC.rglob("*.py")):
        found.append((str(path.relative_to(SRC)), ast.parse(path.read_text())))
    return found


def _type_checking_lines(tree: ast.AST) -> set[int]:
    """Lines inside ``if TYPE_CHECKING:``.

    An import there exists for an annotation and is erased at runtime, so
    naming ``OntologyService`` as a parameter type is not depending on it.
    """
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            named = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
                isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
            )
            if named:
                for child in node.body:
                    for inner in ast.walk(child):
                        if hasattr(inner, "lineno"):
                            lines.add(inner.lineno)
    return lines


def _function_source(tree: ast.AST, source: str, name: str) -> str:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name == name
        ):
            return ast.get_source_segment(source, node) or ""
    return ""


def test_no_module_reaches_for_the_ols_service() -> None:
    """Importing ``get_ontology_service`` hard-wires OLS as the only source."""
    offenders: list[str] = []
    for module, tree in _modules():
        if module in MAY_USE_OLS_DIRECTLY:
            continue
        typing_only = _type_checking_lines(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.lineno in typing_only:
                continue
            if (node.module or "") != "metaseed.services.ontology":
                continue
            names = {alias.name for alias in node.names}
            if names & {"get_ontology_service", "OntologyService"}:
                offenders.append(
                    f"{module}:{node.lineno}: imports {', '.join(sorted(names))}"
                )

    assert not offenders, (
        "these depend on OLS being the term source; ask "
        "metaseed.services.terms.get_term_source() instead:\n  "
        + "\n  ".join(offenders)
    )


def test_only_the_adapter_speaks_ols_http() -> None:
    """A module building OLS4 queries is an adapter, wherever it lives."""
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        module = str(path.relative_to(SRC))
        if module in MAY_CALL_OLS_HTTP:
            continue
        source = path.read_text()
        if "_make_request" in source or "www.ebi.ac.uk/ols" in source:
            offenders.append(module)

    assert not offenders, (
        "these query OLS4 themselves rather than asking a term source:\n  "
        + "\n  ".join(offenders)
    )


def test_every_lookup_entry_point_asks_the_router() -> None:
    """The functions a person's search or an agent's lookup lands in."""
    offenders: list[str] = []
    for module, names in MUST_ROUTE.items():
        path = SRC / module
        source = path.read_text()
        tree = ast.parse(source)
        for name in names:
            body = _function_source(tree, source, name)
            assert body, f"{module}: {name} no longer exists — update this gate"
            if not any(token in body for token in ROUTES_VIA):
                offenders.append(f"{module}: {name}")

    assert not offenders, (
        "these resolve terms without asking the configured sources:\n  "
        + "\n  ".join(offenders)
    )
