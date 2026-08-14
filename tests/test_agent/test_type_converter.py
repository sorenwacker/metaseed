"""`TypeConverter.convert` promises None on conversion failure — for booleans too.

`_to_boolean` never failed: any unrecognized string ('N/A', 'unknown', a typo)
became False and was stored as a real value, so the conversion-failure report
in `_extract_row` could never fire for boolean fields. Silent wrong values on
messy sources are worse than a reported failure.
"""

from __future__ import annotations

import pytest

from metaseed.agent.core import TypeConverter


class TestBooleanConversion:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (True, True),
            (False, False),
            ("true", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("false", False),
            ("FALSE", False),
            ("0", False),
            ("no", False),
            (" true ", True),
        ],
    )
    def test_recognised_spellings_convert(self, value, expected) -> None:
        assert TypeConverter.convert(value, "boolean") is expected

    @pytest.mark.parametrize("value", ["N/A", "unknown", "FALSE_", "2", "maybe"])
    def test_unrecognised_values_fail_the_conversion(self, value) -> None:
        assert TypeConverter.convert(value, "boolean") is None
