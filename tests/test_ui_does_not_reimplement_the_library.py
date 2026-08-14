"""The web application asks the library; it does not carry its own copy.

``ui/routes/examples.py`` held its own recursive walk of a nested document —
``_materialize_children`` — while the library had none, which is exactly why a
consumer could not load a shipped example that the application loaded fine
(#246). The walk now lives in ``ProfileFacade.load_nested`` and the route calls
it.

A duplicate of a library function inside the application is the failure this
guards: not that the copy is wrong on the day it is written, but that it stops
improving. Every improvement to loading — containment markers, references left
as references, provenance — would have to land twice, and the second landing is
the one nobody remembers.
"""

from __future__ import annotations

import ast
from pathlib import Path

UI = Path("src/metaseed/ui")

#: Loading a document is the facade's job. A UI module defining one of these is
#: walking an entity tree itself, whatever the body says.
#:
#: Deliberately narrow: metaseed's ``ui`` package is library code that the hub
#: imports, so it *defines* things like ``build_workbook_from_facade`` rather
#: than copying them. What must not appear here is a second implementation of
#: something the facade already owns.
LIBRARY_FUNCTIONS = frozenset(
    {
        "_materialize_children",
        "load_nested",
        "_load_children",
    }
)

#: Routes that load a dataset, and the library call each must make.
MUST_DELEGATE = {"routes/examples.py": "load_nested"}


def test_no_ui_module_reimplements_a_library_function() -> None:
    offenders: list[str] = []
    for path in sorted(UI.rglob("*.py")):
        tree = ast.parse(path.read_text())
        defined = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        for name in sorted(defined & LIBRARY_FUNCTIONS):
            offenders.append(f"{path.relative_to(UI)}: {name}")

    assert not offenders, (
        "these re-implement what the facade already does; call it instead:\n  "
        + "\n  ".join(offenders)
    )


def test_the_example_route_loads_through_the_facade() -> None:
    for module, call in MUST_DELEGATE.items():
        source = (UI / module).read_text()
        assert call in source, (
            f"{module} no longer asks the library to load the document"
        )


def test_require_spec_is_not_reimplemented_in_a_registrar() -> None:
    """access.require_spec exists so the guard lives once.

    Three registrars kept byte-identical local copies after the extraction;
    a wrapper delegating to access.require_spec is fine, a re-statement of
    the guard body is not.
    """
    import re
    from pathlib import Path

    spec_builder = (
        Path(__file__).parent.parent / "src" / "metaseed" / "ui" / "spec_builder"
    )
    offenders = []
    for path in sorted(spec_builder.glob("routes_*.py")):
        text = path.read_text()
        if re.search(
            r'raise HTTPException\(\s*status_code=400,\s*detail="No spec in progress"',
            text,
        ):
            offenders.append(path.name)
    assert not offenders, f"local require_spec bodies in: {offenders}"
