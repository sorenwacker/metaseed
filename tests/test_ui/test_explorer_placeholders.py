"""The Explorer's dropdowns do not list their own prompt as a choice.

Reported: opening *Base Profile (Reference)* showed "Profile" ticked at the top
of the list, above the profiles, as though it were one of them. The prompt was
an ordinary option with an empty value; the version dropdown did the same with
"Version". A prompt is shown in the closed control and left out of the list.
"""

from __future__ import annotations

import re
from pathlib import Path

EXPLORER = (
    Path(__file__).resolve().parents[2] / "src/metaseed/ui/templates/explore/index.html"
)

EMPTY_OPTION = re.compile(r'<option value=""([^>]*)>([^<]*)</option>')


def test_a_prompt_is_never_a_choice_in_the_list() -> None:
    prompts = [
        (attributes, text)
        for attributes, text in EMPTY_OPTION.findall(EXPLORER.read_text())
        if not text.startswith("None")
    ]

    assert prompts, "the dropdowns lost their prompts"
    assert [text for attributes, text in prompts if "hidden" not in attributes] == []
    assert {text for _, text in prompts} == {"Choose a profile", "Choose a version"}
