"""A test's outcome does not depend on which tests ran before it (#255).

Models are cached globally by ``profile:version:name`` so validation can
resolve a nested entity at deserialization time. Two tests that build the same
profile name from different specs therefore handed each other the wrong model,
and the second saw "Extra inputs are not permitted" for a field its own spec
defines -- ``tests/test_example_accessions.py`` did exactly that to
``tests/test_examples.py``.

The autouse fixture in ``conftest.py`` clears the registry between tests. These
two run in order and fail if it stops doing so: the first plants a model where
a later test would find it, the second is that later test.
"""

from __future__ import annotations

from pydantic import BaseModel

from metaseed.models.factory import get_global_context


class _NotTheRealInvestigation(BaseModel):
    """A model with none of ISA's fields, standing where ISA's would be."""

    model_config = {"extra": "forbid"}


def test_a_test_can_plant_a_model_under_a_real_profiles_key() -> None:
    get_global_context().register(
        "Investigation", _NotTheRealInvestigation, profile="isa", version="1.0"
    )
    assert (
        get_global_context().peek("isa", "1.0", "Investigation")
        is _NotTheRealInvestigation
    )


def test_the_next_test_gets_the_real_model_not_the_planted_one() -> None:
    planted = get_global_context().peek("isa", "1.0", "Investigation")
    assert planted is None, (
        "a model registered by the previous test is still cached: the registry "
        "is not being cleared between tests, and test order now decides outcomes"
    )
    from metaseed.models import get_model

    real = get_model("Investigation", "1.0", "isa")
    assert "title" in real.model_fields, "the real ISA Investigation has a title"
