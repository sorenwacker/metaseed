"""Tests to prevent JSON serialization regressions.

These tests scan the codebase for unsafe patterns that could cause
TypeError when serializing to JSON.
"""

import re
from pathlib import Path

import pytest

# Directories containing serialization code that outputs to JSON/YAML
SERIALIZATION_PATHS = [
    "src/metaseed/api/serialization.py",
    "src/metaseed/facade/store.py",
    "src/metaseed/repositories/filesystem_dataset.py",
    "src/metaseed/repositories/memory.py",
]


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


class TestSerializationSafety:
    """Tests to catch unsafe model_dump() patterns."""

    def test_serialization_files_use_json_mode(self) -> None:
        """Serialization files must use mode='json' with model_dump(exclude_none=True).

        The pattern .model_dump(exclude_none=True) is used for JSON/YAML output.
        Without mode="json", dates and URLs are returned as Python objects
        that cannot be serialized.

        Note: Plain .model_dump() calls are often for internal use (comparisons,
        index lookups) and are not flagged by this test.
        """
        root = get_project_root()
        violations = []

        # Pattern: model_dump(exclude_none=True) without mode="json"
        # This is the typical serialization pattern that outputs to JSON/YAML
        unsafe_pattern = re.compile(r"\.model_dump\(\s*exclude_none\s*=\s*True\s*\)")

        for rel_path in SERIALIZATION_PATHS:
            file_path = root / rel_path
            if not file_path.exists():
                continue

            content = file_path.read_text()
            lines = content.split("\n")

            for line_num, line in enumerate(lines, 1):
                # Skip comments
                if line.strip().startswith("#"):
                    continue

                # Find unsafe pattern
                if unsafe_pattern.search(line):
                    violations.append(f"{rel_path}:{line_num}: {line.strip()}")

        if violations:
            msg = (
                "Found model_dump(exclude_none=True) without mode='json'.\n"
                "This causes TypeError when serializing dates/URLs to JSON.\n\n"
                "Violations:\n" + "\n".join(f"  - {v}" for v in violations) + "\n\n"
                "Fix: Use model_dump(mode='json', exclude_none=True) instead."
            )
            pytest.fail(msg)

    def test_to_json_dict_helper_exists(self) -> None:
        """The safe serialization helper must exist."""
        from metaseed.core.serialization import to_json_dict

        assert callable(to_json_dict)

    def test_to_json_dict_returns_json_serializable(self) -> None:
        """to_json_dict must return JSON-serializable data."""
        import json
        from datetime import date

        from pydantic import AnyUrl, BaseModel

        class TestModel(BaseModel):
            date_field: date
            url_field: AnyUrl

        instance = TestModel(
            date_field=date(2024, 1, 15),
            url_field="https://example.org",
        )

        from metaseed.core.serialization import to_json_dict

        data = to_json_dict(instance)

        # Must not raise TypeError
        result = json.dumps(data)
        assert "2024-01-15" in result
        assert "https://example.org" in result

    def test_to_json_dict_handles_none(self) -> None:
        """to_json_dict handles None input gracefully."""
        from metaseed.core.serialization import to_json_dict

        assert to_json_dict(None) == {}
