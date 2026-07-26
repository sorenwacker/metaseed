"""ReDoS regression tests for the hand-rolled MCP validate path.

`ExtractionContext._validate_field` used Python's backtracking `re.match` on a
spec-supplied `pattern`, so a catastrophic pattern (``^(a+)+$``) on a modest input
stalled the process for tens of seconds. The fix routes pattern matching through
Pydantic's linear (Rust) regex engine via `_pattern_matches`.
"""

from __future__ import annotations

import time

from metaseed.agent.core import ExtractionContext, _pattern_matches
from metaseed.specs.schema import Constraints, FieldSpec, FieldType

# A pattern that triggers exponential backtracking in Python's `re`.
_EVIL = r"^(a+)+$"
# Input that maximises backtracking (long run of 'a' then a non-match): ~68s in re.
_EVIL_INPUT = "a" * 40 + "!"


def test_catastrophic_pattern_returns_fast():
    start = time.monotonic()
    result = _pattern_matches(_EVIL, _EVIL_INPUT)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0, f"pattern match took {elapsed:.1f}s (ReDoS)"
    assert result is False  # the input does not match, and is reported quickly


def test_catastrophic_pattern_still_correct():
    assert _pattern_matches(_EVIL, "aaaa") is True  # matches
    assert _pattern_matches(_EVIL, "aaab") is False  # does not match


def test_normal_pattern_behaviour_preserved():
    assert _pattern_matches(r"^PXD[0-9]+$", "PXD000001") is True
    assert _pattern_matches(r"^PXD[0-9]+$", "BAD") is False


def test_uncompilable_pattern_skips_gracefully():
    # Rust regex has no lookbehind; treat as unenforceable rather than crash.
    assert _pattern_matches(r"(?<=a)b", "x") is True


def _ctx() -> ExtractionContext:
    return ExtractionContext.from_profile("miappe", "1.1")


def _field(pattern: str) -> FieldSpec:
    return FieldSpec(
        name="f", type=FieldType.STRING, constraints=Constraints(pattern=pattern)
    )


def test_validate_field_catastrophic_pattern_is_fast_and_rejects():
    ctx = _ctx()
    start = time.monotonic()
    errors = ctx._validate_field(_EVIL_INPUT, _field(_EVIL))
    elapsed = time.monotonic() - start
    assert elapsed < 2.0
    assert len(errors) == 1  # non-matching value reported


def test_validate_field_normal_pattern_preserved():
    ctx = _ctx()
    assert ctx._validate_field("PXD000001", _field(r"^PXD[0-9]+$")) == []
    assert len(ctx._validate_field("BAD", _field(r"^PXD[0-9]+$"))) == 1


def test_validate_field_enforces_list_cardinality():
    """min_items/max_items on a list field are enforced (previously never checked)."""
    from metaseed.specs.schema import Constraints, FieldSpec, FieldType

    ctx = _ctx()
    field = FieldSpec(
        name="items",
        type=FieldType.LIST,
        constraints=Constraints(min_items=2, max_items=3),
    )
    assert len(ctx._validate_field(["a"], field)) == 1  # too few
    assert len(ctx._validate_field(["a", "b", "c", "d"], field)) == 1  # too many
    assert ctx._validate_field(["a", "b"], field) == []  # within bounds


def test_validate_field_enforces_max_length_zero():
    """max_length=0 (empty-only) is enforced (a falsy-check previously skipped it)."""
    from metaseed.specs.schema import Constraints, FieldSpec, FieldType

    ctx = _ctx()
    field = FieldSpec(
        name="f", type=FieldType.STRING, constraints=Constraints(max_length=0)
    )
    assert len(ctx._validate_field("x", field)) == 1  # non-empty rejected
    assert ctx._validate_field("", field) == []  # empty allowed
