"""The link/unlink invariant is decided in ONE module (ADR 005).

Three components hand-maintained the parent-child invariant, and the 260814
triage fixed three bugs that were all the same bug: a reference written on
create and forgotten on delete, and the LIST-vs-ENTITY shape decided
differently per component. The decisions live in facade/linking.py; a
repository or store that starts deciding shapes again turns this red.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "metaseed"

#: Where the shape discriminator may appear: its definition, and the one
#: module allowed to decide with it.
ALLOWED = {
    Path("facade") / "helper.py",
    Path("facade") / "linking.py",
}


def test_the_shape_rule_has_one_home() -> None:
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC)
        if relative in ALLOWED:
            continue
        if "single_entity_fields" in path.read_text():
            offenders.append(str(relative))
    assert not offenders, (
        f"the LIST-vs-ENTITY shape rule is decided outside facade/linking.py "
        f"in: {offenders} (ADR 005)"
    )


#: Where the field-selection rule may be decided: its definition, and the
#: helper that exposes the map it reads.
FIELD_SELECTION_ALLOWED = {
    Path("facade") / "helper.py",
    Path("facade") / "linking.py",
}


def _selects_a_field_by_child_type(node, key_var: str, value_var: str) -> bool:
    """Whether a loop body picks the KEY by matching the VALUE against a type.

    Iterating ``nested_fields.items()`` is ordinary — walking a parent's
    children does it. What belongs to linking.py is using that mapping the
    other way round: keying on the child type to choose the field. That reads
    as `if value == something`, as `map[value] = key`, or as `setdefault(value,
    key)`.
    """
    import ast

    for inner in ast.walk(node):
        if isinstance(inner, ast.Compare) and any(
            isinstance(side, ast.Name) and side.id == value_var
            for side in [inner.left, *inner.comparators]
        ):
            return True
        if (
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "setdefault"
            and inner.args
            and isinstance(inner.args[0], ast.Name)
            and inner.args[0].id == value_var
        ):
            return True
        if (
            isinstance(inner, ast.Subscript)
            and isinstance(inner.slice, ast.Name)
            and inner.slice.id == value_var
            and isinstance(inner.ctx, ast.Store)
        ):
            return True
    return key_var == ""  # unreachable; keeps the signature honest


def _target_names(target) -> tuple[str, str]:
    """The (key, value) names bound by ``for key, value in ...``."""
    import ast

    if isinstance(target, ast.Tuple) and len(target.elts) == 2:
        names = [e.id if isinstance(e, ast.Name) else "" for e in target.elts]
        return names[0], names[1]
    return "", ""


def _decides_which_field_references_a_child(source: str) -> bool:
    """Whether the source decides which parent field references a child type.

    linking.py states that rule once: the FIRST declared nested field whose
    target names the child's type. It was re-derived elsewhere, once by dict
    inversion — which takes the LAST match and so already disagreed.
    """
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:  # pragma: no cover - a file that cannot parse is not ours
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.DictComp):
            for generator in node.generators:
                if "nested_fields.items()" not in ast.unparse(generator.iter):
                    continue
                _, value_var = _target_names(generator.target)
                # {value: key for key, value in ...} — the inversion.
                if isinstance(node.key, ast.Name) and node.key.id == value_var:
                    return True
        if isinstance(node, (ast.For, ast.AsyncFor)):
            if "nested_fields.items()" not in ast.unparse(node.iter):
                continue
            key_var, value_var = _target_names(node.target)
            if not value_var:
                continue
            for statement in node.body:
                if _selects_a_field_by_child_type(statement, key_var, value_var):
                    return True
    return False


def test_the_field_selection_rule_has_one_home() -> None:
    """ADR 005's other decision — which parent field carries the reference.

    `linking.target_reference_field` states it once: the FIRST declared nested
    field whose target names the child's type. It was re-derived in four other
    places, one of them by dict inversion, which takes the last match and so
    already disagreed. The original gate scanned for one string
    (`single_entity_fields`) and could not see any of them.
    """
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC)
        if relative in FIELD_SELECTION_ALLOWED:
            continue
        if _decides_which_field_references_a_child(path.read_text()):
            offenders.append(str(relative))

    assert not offenders, (
        "which parent field references a child type is decided outside "
        f"facade/linking.py in: {offenders}. Call "
        "`linking.target_reference_field` instead (ADR 005)."
    )
