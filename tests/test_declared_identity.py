"""#143: declared identifier/label resolution replaces positional guessing.

Each listed entity previously mis-resolved its identifier or label to a nested
model or a parent reference. With ``is_identifier``/``is_label`` markers declared
in the specs, ``EntityHelper.identifier_field`` and ``derive_label`` must resolve
to the sensible scalar field instead.
"""

from __future__ import annotations

import pytest

from metaseed.facade.core import ProfileFacade
from metaseed.repositories.helpers import derive_label

# (profile, version, entity, resolved_field, a decoy field that used to win)
_CASES = [
    ("isa", "1.0", "FactorValue", "value", "factor_name"),
    ("isa", "1.0", "Characteristic", "value", "category"),
    ("isa", "1.0", "ParameterValue", "value", "category"),
    ("isa", "1.0", "Protocol", "name", "study_id"),
    ("isa", "1.0", "Source", "name", "study_id"),
    ("isa", "1.0", "Sample", "name", "study_id"),
    ("isa", "1.0", "StudyFactor", "name", "study_id"),
    ("isa", "1.0", "DataFile", "filename", "assay_id"),
    ("ena", "1.0", "File", "filename", "run_ref"),
]


@pytest.mark.parametrize(("profile", "version", "entity", "resolved", "decoy"), _CASES)
def test_identifier_and_label_resolve_to_declared_field(
    profile: str, version: str, entity: str, resolved: str, decoy: str
) -> None:
    helper = getattr(ProfileFacade(profile, version), entity)

    # identifier_field is the declared scalar, not a nested model / reference.
    assert helper.identifier_field == resolved

    # derive_label picks the declared field's value even when the decoy field
    # (a nested ref or parent id) also carries a value.
    data = {resolved: "REAL", decoy: "DECOY"}
    assert derive_label(entity, data, spec=helper._spec) == "REAL"
