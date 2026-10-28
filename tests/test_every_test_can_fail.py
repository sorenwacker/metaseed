"""Every test must be able to fail.

A test that is always skipped, has an empty body, or checks nothing passes on
broken code, which is worse than no test: it reports cover that is not there.
"""

from __future__ import annotations

import ast
from pathlib import Path

TESTS = Path(__file__).parent

#: Calls that check without an ``assert`` statement.
_CHECKING_CALLS = frozenset({"raises", "warns", "fail", "deprecated_call"})

#: Tests whose check lives in a helper they call; each names that helper.
_CHECKED_BY_A_HELPER = {
    "test_cli/test_extract_input_errors.py::test_run_reports_an_unusable_mapping_file": "_input_error",
    "test_cli/test_extract_input_errors.py::test_run_reports_a_missing_mapping_file": "_input_error",
    "test_cli/test_extract_input_errors.py::test_records_that_are_not_json_are_reported": "_input_error",
    "test_isatab/test_every_term_source_is_declared.py::test_a_characteristic_embedded_in_its_sample_has_its_source_declared": "_check",
    "test_validators/test_uri_field_pattern_constraint.py::test_every_documented_constraint_accepts_a_satisfying_value": "model",
    "test_ena/test_export.py::test_ena_export_validates_against_official_sra_xsd": "validate",
}


def _tests() -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    found = []
    for path in sorted(TESTS.rglob("test_*.py")):
        rel = path.relative_to(TESTS).as_posix()
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                found.append((rel, node))
    return found


def _is_unconditional_skip(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return ast.unparse(target) == "pytest.mark.skip"


def _checks(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for inner in ast.walk(node):
        if isinstance(inner, (ast.Assert, ast.Raise)):
            return True
        if isinstance(inner, ast.Call):
            func = inner.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else getattr(func, "id", "")
            )
            # A mock's assert_called_with, assert_not_awaited, ...
            if name in _CHECKING_CALLS or name.startswith("assert_"):
                return True
    return False


def test_no_test_is_skipped_unconditionally() -> None:
    skipped = [
        f"{rel}::{node.name}"
        for rel, node in _tests()
        if any(_is_unconditional_skip(d) for d in node.decorator_list)
    ]
    assert not skipped, "delete or fix these instead of skipping them:\n" + "\n".join(
        skipped
    )


def test_every_test_checks_something() -> None:
    unchecked = [
        f"{rel}::{node.name}"
        for rel, node in _tests()
        if not isinstance(node, ast.ClassDef)
        and node.name.startswith("test")
        and f"{rel}::{node.name}" not in _CHECKED_BY_A_HELPER
        and not _checks(node)
    ]
    assert not unchecked, "these tests pass whatever the code does:\n" + "\n".join(
        unchecked
    )


def test_every_allowlisted_test_still_calls_its_helper() -> None:
    by_key = {
        f"{rel}::{n.name}": n for rel, n in _tests() if not isinstance(n, ast.ClassDef)
    }
    stale = []
    for key, helper in _CHECKED_BY_A_HELPER.items():
        node = by_key.get(key)
        if node is None or helper not in ast.unparse(node):
            stale.append(key)
    assert not stale, "remove these from the allowlist:\n" + "\n".join(stale)
