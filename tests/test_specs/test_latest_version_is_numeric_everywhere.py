""" "Latest version" means numerically latest, in every place that says it.

`version_sort_key` exists because sorting versions as text made 1.9 look newer
than 1.10 — releasing a tenth minor version made *latest* step backwards. Two
more places still sorted as text: the CLI's example picker and the spec
filesystem's display-name lookup.
"""

from __future__ import annotations

from metaseed.specs.versioning import version_sort_key


def test_the_shared_key_orders_ten_after_nine() -> None:
    assert sorted(["1.9", "1.10", "1.2"], key=version_sort_key)[-1] == "1.10"


def test_the_example_picker_uses_it() -> None:
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "metaseed"
        / "cli"
        / "commands"
        / "example.py"
    ).read_text()

    assert "version_sort_key" in source, "the CLI picks the latest example by text sort"


async def test_the_display_name_lookup_picks_the_numeric_latest() -> None:
    """Behavioural, not a scan: the module already names `version_sort_key`
    elsewhere, so searching the source passed while this call sorted as text."""
    from metaseed.specs.schema import ProfileSpec
    from metaseed.ui.spec_filesystem import FilesystemSpecProvider

    provider = FilesystemSpecProvider()
    provider._loader.list_versions = lambda profile: ["1.9", "1.10"]  # type: ignore[method-assign]
    provider._loader.load_profile = lambda version, profile: ProfileSpec(  # type: ignore[method-assign]
        name=profile,
        version=version,
        display_name="Ten" if version == "1.10" else "Nine",
    )

    assert await provider.get_display_name("probe") == "Ten"
