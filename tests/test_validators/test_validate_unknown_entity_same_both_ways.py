"""validate() answers an unknown entity the same way with or without cascade.

cascade=True returned an "Unknown entity type" error; cascade=False let the
SpecLoadError escape a function declared to return a list of errors.
"""

from __future__ import annotations

import pytest

from metaseed.validators.api import validate


@pytest.mark.parametrize("cascade", [True, False])
def test_an_unknown_entity_is_a_returned_error(cascade: bool) -> None:
    errors = validate({"unique_id": "X-1"}, "not_an_entity", cascade=cascade)

    assert [(e.field, e.rule) for e in errors] == [("not_an_entity", "error")]
    assert "Unknown entity type: not_an_entity" in errors[0].message
