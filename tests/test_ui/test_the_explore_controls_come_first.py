"""The explorer's controls sit above everything that varies in length.

0.51.0 moved the Explore button and the Show/Hide toggles above the profile's
description and its validation rules, because a paragraph and dozens of rules
pushed what a person came to press off the screen. The change shipped without a
gate and was lost in the hub's copy of the page; this is the gate.
"""

from metaseed.ui.app import TEMPLATES_DIR


def test_the_explore_button_and_filters_precede_the_profile_and_its_rules() -> None:
    template = (TEMPLATES_DIR / "explore" / "index.html").read_text()
    controls = template.index('id="compare-btn"')
    filters = template.index('id="filter-section"')
    for section in ('id="profile-section"', 'id="rules-section"'):
        assert controls < template.index(section), section
        assert filters < template.index(section), section
